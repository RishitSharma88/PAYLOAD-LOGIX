"""SQLite persistence for RAA (mirror of payload/db.py conventions).

Tables:
  schedule_events -- scheduled event rows (event_id, component_id,
                     category, deadline, derived duration, order_index)
  free_slots      -- gaps freed by cancels / gaps between events
  island_gaps     -- dependency-island gaps reported by Logistics
                     (never filled with invented data)
  raa_state       -- last valid schedule snapshot for R2 recovery
                     (same snapshot/recovery convention as payload)
"""
import json
import os
import sqlite3
import time

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "state", "raa.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedule_events (
  event_id TEXT PRIMARY KEY,
  component_id TEXT NOT NULL,
  category TEXT,
  deadline_unix_sec INTEGER NOT NULL,
  duration_s INTEGER NOT NULL DEFAULT 0,
  order_index INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'scheduled',
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS free_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  start_unix_sec INTEGER NOT NULL,
  end_unix_sec INTEGER NOT NULL,
  gap_s INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS island_gaps (
  island_id TEXT NOT NULL,
  component_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (island_id, component_id)
);
CREATE TABLE IF NOT EXISTS raa_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  last_valid TEXT NOT NULL DEFAULT '{}',
  updated_at INTEGER NOT NULL
);
"""


def _now():
    return int(time.time())


class RaaDB:
    def __init__(self, path=None):
        path = path or DEFAULT_DB
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO raa_state (id, last_valid, updated_at) "
            "VALUES (1, '{}', ?)", (_now(),))
        self.conn.commit()

    # -- events ----------------------------------------------------------------
    def upsert_event(self, event_id, component_id, category,
                     deadline_unix_sec, duration_s=0, order_index=0,
                     status="scheduled"):
        self.conn.execute(
            "INSERT INTO schedule_events VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(event_id) DO UPDATE SET "
            "component_id=excluded.component_id, category=excluded.category,"
            " deadline_unix_sec=excluded.deadline_unix_sec,"
            " duration_s=excluded.duration_s,"
            " order_index=excluded.order_index, status=excluded.status,"
            " updated_at=excluded.updated_at",
            (event_id, component_id, category, int(deadline_unix_sec),
             int(duration_s), int(order_index), status, _now()))
        self.conn.commit()

    def get_events(self, status=None):
        q = "SELECT * FROM schedule_events"
        args = []
        if status:
            q += " WHERE status=?"
            args.append(status)
        return [dict(r) for r in self.conn.execute(
            q + " ORDER BY deadline_unix_sec, order_index", args)]

    def mark_event(self, event_id, status):
        self.conn.execute(
            "UPDATE schedule_events SET status=?, updated_at=? "
            "WHERE event_id=?", (status, _now(), event_id))
        self.conn.commit()

    def replace_scheduled_events(self, events):
        """Replace only the active rows during R2 recovery.

        The snapshot itself deliberately remains intact until the caller has
        restored it successfully.
        """
        self.conn.execute("DELETE FROM schedule_events WHERE status='scheduled'")
        for event in events:
            self.conn.execute(
                "INSERT INTO schedule_events VALUES (?,?,?,?,?,?,?,?)",
                (event["event_id"], event["component_id"],
                 event.get("category", ""),
                 int(event["deadline_unix_sec"]),
                 int(event.get("duration_s", 0)),
                 int(event.get("order_index", 0)), "scheduled", _now()))
        self.conn.commit()

    # -- free slots ----------------------------------------------------------------
    def add_free_slot(self, start_unix_sec, end_unix_sec):
        self.conn.execute(
            "INSERT INTO free_slots (start_unix_sec, end_unix_sec, gap_s,"
            " created_at) VALUES (?,?,?,?)",
            (int(start_unix_sec), int(end_unix_sec),
             int(end_unix_sec - start_unix_sec), _now()))
        self.conn.commit()

    def get_free_slots(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM free_slots ORDER BY start_unix_sec")]

    # -- island gaps (from Logistics; enum of real gaps only) -------------------------
    def upsert_island_gaps(self, gaps):
        for g in gaps:
            self.conn.execute(
                "INSERT INTO island_gaps VALUES (?,?,?,?) "
                "ON CONFLICT(island_id, component_id) DO UPDATE SET "
                "reason=excluded.reason, updated_at=excluded.updated_at",
                (g["island_id"], g["component_id"], g["reason"], _now()))
        self.conn.commit()

    def get_island_gaps(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM island_gaps ORDER BY island_id, component_id")]

    # -- R2 snapshot ---------------------------------------------------------------
    def snapshot_valid(self, state_blob):
        self.conn.execute(
            "UPDATE raa_state SET last_valid=?, updated_at=? WHERE id=1",
            (json.dumps(state_blob), _now()))
        self.conn.commit()

    def get_state(self):
        r = self.conn.execute(
            "SELECT * FROM raa_state WHERE id=1").fetchone()
        d = dict(r)
        d["last_valid"] = json.loads(d["last_valid"])
        return d

    def reset(self):
        for t in ("schedule_events", "free_slots", "island_gaps"):
            self.conn.execute("DELETE FROM %s" % t)
        self.conn.execute(
            "UPDATE raa_state SET last_valid='{}', updated_at=? WHERE id=1",
            (_now(),))
        self.conn.commit()
