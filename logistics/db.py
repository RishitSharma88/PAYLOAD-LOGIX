"""SQLite persistence for the Logistics Agent (mirror of payload/db.py
conventions; no new engine, same venv sqlite3).

Tables:
  component_logistics  -- per component: RAA deadline, manufacturer,
                          delivery time (None = waiting), status, island
  dependency_links     -- the dependency dictionary persisted
                          (component_id -> depends_on_id, deadlines)
  islands              -- island registry (island_id, deadline)
  logistics_state      -- last valid snapshot for L2 recovery (same
                          snapshot/recovery convention as payload
                          constructor_state)
"""
import json
import os
import sqlite3
import time

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "state", "logistics.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS component_logistics (
  component_id TEXT PRIMARY KEY,
  category TEXT,
  manufacturer TEXT,
  raa_deadline_unix_sec INTEGER NOT NULL,
  delivery_time_unix_sec INTEGER,
  status TEXT NOT NULL DEFAULT 'waiting',
  island_id TEXT,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS dependency_links (
  component_id TEXT NOT NULL,
  depends_on_id TEXT NOT NULL,
  deadline_unix_sec INTEGER NOT NULL,
  PRIMARY KEY (component_id, depends_on_id)
);
CREATE TABLE IF NOT EXISTS islands (
  island_id TEXT PRIMARY KEY,
  deadline_unix_sec INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS logistics_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  last_valid TEXT NOT NULL DEFAULT '{}',
  updated_at INTEGER NOT NULL
);
"""


def _now():
    return int(time.time())


class LogisticsDB:
    def __init__(self, path=None):
        path = path or DEFAULT_DB
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO logistics_state (id, last_valid, "
            "updated_at) VALUES (1, '{}', ?)", (_now(),))
        self.conn.commit()

    # -- component logistics ------------------------------------------------
    def upsert_component(self, component_id, category, manufacturer,
                         raa_deadline_unix_sec, delivery_time_unix_sec,
                         status, island_id=None):
        self.conn.execute(
            "INSERT INTO component_logistics VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(component_id) DO UPDATE SET "
            "category=excluded.category, manufacturer=excluded.manufacturer,"
            " raa_deadline_unix_sec=excluded.raa_deadline_unix_sec,"
            " delivery_time_unix_sec=excluded.delivery_time_unix_sec,"
            " status=excluded.status, island_id=excluded.island_id,"
            " updated_at=excluded.updated_at",
            (component_id, category, manufacturer,
             int(raa_deadline_unix_sec),
             None if delivery_time_unix_sec is None
             else int(delivery_time_unix_sec),
             status, island_id, _now()))
        self.conn.commit()

    def get_components(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM component_logistics ORDER BY component_id")]

    # -- dependency dictionary ----------------------------------------------
    def upsert_link(self, component_id, depends_on_id, deadline_unix_sec):
        self.conn.execute(
            "INSERT OR IGNORE INTO dependency_links VALUES (?,?,?)",
            (component_id, depends_on_id, int(deadline_unix_sec)))
        self.conn.commit()

    def get_links(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM dependency_links ORDER BY component_id")]

    def replace_links(self, links):
        self.conn.execute("DELETE FROM dependency_links")
        for link in links:
            self.conn.execute(
                "INSERT INTO dependency_links VALUES (?,?,?)",
                (link["component_id"], link["depends_on_id"],
                 int(link["deadline_unix_sec"])))
        self.conn.commit()

    # -- islands --------------------------------------------------------------
    def sync_islands(self, islands):
        """islands: result dict from logistics.islands.build_islands."""
        for island_id, deadline in islands["deadlines"].items():
            self.conn.execute(
                "INSERT INTO islands VALUES (?,?,?,?) "
                "ON CONFLICT(island_id) DO UPDATE SET "
                "deadline_unix_sec=excluded.deadline_unix_sec, "
                "updated_at=excluded.updated_at",
                (island_id, int(deadline), "open", _now()))
        self.conn.commit()

    def get_islands(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM islands ORDER BY island_id")]

    # -- L2 snapshot (existing recovery convention) ----------------------------
    def snapshot_valid(self, state_blob):
        self.conn.execute(
            "UPDATE logistics_state SET last_valid=?, updated_at=? "
            "WHERE id=1", (json.dumps(state_blob), _now()))
        self.conn.commit()

    def get_state(self):
        r = self.conn.execute(
            "SELECT * FROM logistics_state WHERE id=1").fetchone()
        d = dict(r)
        d["last_valid"] = json.loads(d["last_valid"])
        return d

    def reset(self):
        for t in ("component_logistics", "dependency_links", "islands"):
            self.conn.execute("DELETE FROM %s" % t)
        self.conn.execute(
            "UPDATE logistics_state SET last_valid='{}', updated_at=? "
            "WHERE id=1", (_now(),))
        self.conn.commit()
