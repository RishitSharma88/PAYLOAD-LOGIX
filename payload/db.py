"""SQLite persistence for Payload Agent state (no Redis in this stage).

Tables: satellite_blueprint, blueprint_components, component_requirements,
constructor_state. Single default blueprint ('main'). The last valid
configuration is preserved so P2 recovery keeps working.
"""
import json
import os
import sqlite3
import time

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "state", "payload.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS satellite_blueprint (
  blueprint_id TEXT PRIMARY KEY,
  version INTEGER NOT NULL DEFAULT 1,
  mass_threshold_kg REAL,
  power_threshold_w REAL,
  volume_threshold_cm3 REAL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS blueprint_components (
  blueprint_id TEXT NOT NULL,
  component_id TEXT NOT NULL,
  category TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 1,
  manufacturer TEXT,
  mass_kg REAL,
  power_w REAL,
  volume_cm3 REAL,
  status TEXT NOT NULL DEFAULT 'active',
  PRIMARY KEY (blueprint_id, component_id)
);
CREATE TABLE IF NOT EXISTS component_requirements (
  blueprint_id TEXT NOT NULL,
  category TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 1,
  max_mass_kg REAL,
  max_power_w REAL,
  max_volume_cm3 REAL,
  manufacturer_constraint TEXT,
  PRIMARY KEY (blueprint_id, category)
);
CREATE TABLE IF NOT EXISTS constructor_state (
  blueprint_id TEXT PRIMARY KEY,
  last_valid_configuration TEXT NOT NULL DEFAULT '[]',
  cached_rankings TEXT NOT NULL DEFAULT '{}',
  updated_at INTEGER NOT NULL
);
"""


def _now():
    return int(time.time())


class PayloadDB:
    def __init__(self, path=DEFAULT_DB, blueprint_id="main"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.blueprint_id = blueprint_id
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO satellite_blueprint "
            "(blueprint_id, version, updated_at) VALUES (?,?,?)",
            (blueprint_id, 1, _now()))
        self.conn.execute(
            "INSERT OR IGNORE INTO constructor_state "
            "(blueprint_id, updated_at) VALUES (?,?)",
            (blueprint_id, _now()))
        self.conn.commit()

    # -- satellite thresholds -------------------------------------------
    def set_thresholds(self, mass=None, power=None, volume=None):
        self.conn.execute(
            "UPDATE satellite_blueprint SET mass_threshold_kg=COALESCE(?,mass_threshold_kg),"
            " power_threshold_w=COALESCE(?,power_threshold_w),"
            " volume_threshold_cm3=COALESCE(?,volume_threshold_cm3),"
            " version=version+1, updated_at=? WHERE blueprint_id=?",
            (mass, power, volume, _now(), self.blueprint_id))
        self.conn.commit()

    def get_thresholds(self):
        r = self.conn.execute(
            "SELECT * FROM satellite_blueprint WHERE blueprint_id=?",
            (self.blueprint_id,)).fetchone()
        return dict(r)

    # -- components -------------------------------------------------------
    def upsert_component(self, component_id, category, quantity=1,
                         manufacturer=None, mass_kg=None, power_w=None,
                         volume_cm3=None, status="active"):
        self.conn.execute(
            "INSERT INTO blueprint_components VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(blueprint_id, component_id) DO UPDATE SET "
            "category=excluded.category, quantity=excluded.quantity,"
            " manufacturer=excluded.manufacturer, mass_kg=excluded.mass_kg,"
            " power_w=excluded.power_w, volume_cm3=excluded.volume_cm3,"
            " status=excluded.status",
            (self.blueprint_id, component_id, category, quantity,
             manufacturer, mass_kg, power_w, volume_cm3, status))
        self.conn.commit()

    def remove_component(self, component_id):
        cur = self.conn.execute(
            "DELETE FROM blueprint_components WHERE blueprint_id=? "
            "AND component_id=?", (self.blueprint_id, component_id))
        self.conn.commit()
        return cur.rowcount > 0

    def remove_category(self, category, quantity):
        rows = self.conn.execute(
            "SELECT component_id FROM blueprint_components "
            "WHERE blueprint_id=? AND category=? ORDER BY component_id",
            (self.blueprint_id, category)).fetchall()
        doomed = [r["component_id"] for r in rows[:quantity]]
        for cid in doomed:
            self.remove_component(cid)
        return doomed

    def get_components(self, category=None):
        q = "SELECT * FROM blueprint_components WHERE blueprint_id=?"
        args = [self.blueprint_id]
        if category:
            q += " AND category=?"
            args.append(category)
        return [dict(r) for r in
                self.conn.execute(q + " ORDER BY component_id", args).fetchall()]

    # -- requirements ------------------------------------------------------
    def set_requirement(self, category, quantity=1, max_mass_kg=None,
                        max_power_w=None, max_volume_cm3=None,
                        manufacturer_constraint=None):
        self.conn.execute(
            "INSERT INTO component_requirements VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(blueprint_id, category) DO UPDATE SET "
            "quantity=excluded.quantity, max_mass_kg=excluded.max_mass_kg,"
            " max_power_w=excluded.max_power_w,"
            " max_volume_cm3=excluded.max_volume_cm3,"
            " manufacturer_constraint=excluded.manufacturer_constraint",
            (self.blueprint_id, category, quantity, max_mass_kg,
             max_power_w, max_volume_cm3, manufacturer_constraint))
        self.conn.commit()

    def get_requirements(self, category=None):
        q = "SELECT * FROM component_requirements WHERE blueprint_id=?"
        args = [self.blueprint_id]
        if category:
            q += " AND category=?"
            args.append(category)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    # -- constructor state (P1/P2) ------------------------------------------
    def snapshot_valid(self, configuration, rankings):
        self.conn.execute(
            "UPDATE constructor_state SET last_valid_configuration=?,"
            " cached_rankings=?, updated_at=? WHERE blueprint_id=?",
            (json.dumps(configuration), json.dumps(rankings),
             _now(), self.blueprint_id))
        self.conn.commit()

    def get_state(self):
        r = self.conn.execute(
            "SELECT * FROM constructor_state WHERE blueprint_id=?",
            (self.blueprint_id,)).fetchone()
        d = dict(r)
        d["last_valid_configuration"] = json.loads(d["last_valid_configuration"])
        d["cached_rankings"] = json.loads(d["cached_rankings"])
        return d

    def reset(self):
        for t in ("blueprint_components", "component_requirements"):
            self.conn.execute("DELETE FROM %s WHERE blueprint_id=?" % t,
                              (self.blueprint_id,))
        self.conn.execute(
            "UPDATE satellite_blueprint SET mass_threshold_kg=NULL,"
            " power_threshold_w=NULL, volume_threshold_cm3=NULL,"
            " version=1, updated_at=? WHERE blueprint_id=?",
            (_now(), self.blueprint_id))
        self.conn.execute(
            "UPDATE constructor_state SET last_valid_configuration='[]',"
            " cached_rankings='{}', updated_at=? WHERE blueprint_id=?",
            (_now(), self.blueprint_id))
        self.conn.commit()
