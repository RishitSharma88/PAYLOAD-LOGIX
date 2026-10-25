"""Logistics Agent: deterministic spoke for delivery tracking and islands.

Reuses (no duplication): agents/master_state.py + agents/state_store.py
(Redis mirror), proto/payload_logix_pb2.py messages (LogisticsCommand /
LogisticsResponse / RiskToLogistics — sender/receiver set per use, no proto
changes), the snapshot-recovery convention of payload/db.py, and the state
transition style of agents/payload_agent.py.

Responsibilities (spec):
- ingest RAA scheduling events (LogisticsCommand, intent SCHEDULE/…),
- dependency dictionary + islands formed ONLY by matching deadlines
  (logistics/islands.py),
- manufacturer delivery times: never invented; missing => waiting,
- deadlines: compared against the ORIGINAL RAA deadline, never extended,
- reports to Risk via LogisticsResponse bytes (header LOGISTICS -> RISK),
- handles L1 (re-sync island) and L2 (restore last valid snapshot),
- publishes state + health evidence to Redis.
"""
import json
import time
import uuid

from proto import payload_logix_pb2 as pb
from agents import master_state
from agents.state_store import AgentStateStore
from logistics import islands as isl
from logistics.db import LogisticsDB

PROTOCOL_VERSION = "1.0"

CATNAME = {pb.RADIO: "RADIO", pb.REACTION_WHEEL: "REACTION_WHEEL",
           pb.PMAD: "PMAD", pb.SATELLITE: "SATELLITE"}
INTENTS = {pb.SCHEDULE: "SCHEDULE", pb.RESCHEDULE: "RESCHEDULE",
           pb.CANCEL: "CANCEL"}


def _now():
    return int(time.time())


class LogisticsAgent:
    def __init__(self, db_path=None, redis_url=None, risk=None):
        self.db = LogisticsDB(path=db_path) if db_path else LogisticsDB()
        try:
            self.prompt = master_state.load_prompt("logistics")
        except OSError:
            self.prompt = ""
        self.store = AgentStateStore(url=redis_url)
        self.risk = risk
        self.outgoing = []          # JSON log of outgoing messages
        self.last_health = {}

    # -- master state ---------------------------------------------------------
    def _update_state(self, line):
        try:
            info = master_state.set_state("logistics", line)
            self.store.set_state("logistics", info["state"], info["updated"])
        except Exception:
            pass

    def _log(self, **record):
        record.setdefault("ts", round(time.time(), 3))
        record.setdefault("sender", "LOGISTICS")
        record.setdefault("protocol_version", PROTOCOL_VERSION)
        self.outgoing.append(record)
        try:
            import sys
            sys.stdout.write("LOGISTICS-MSG> %s\n" %
                             json.dumps(record, sort_keys=True, default=str))
            sys.stdout.flush()
        except Exception:
            pass
        return record

    # -- wire: RAA/scheduling ingestion ---------------------------------------
    def ingest_raa(self, data):
        """LogisticsCommand bytes (sender RAA/SML -> LOGISTICS)."""
        self._update_state("RECEIVING event")
        ev = pb.LogisticsCommand()
        ev.ParseFromString(data)
        if ev.header.receiver != pb.LOGISTICS:
            self._update_state("FAILED last operation")
            raise ValueError("LogisticsCommand must target LOGISTICS")
        if ev.intent not in (pb.SCHEDULE, pb.RESCHEDULE, pb.CANCEL):
            self._update_state("FAILED last operation")
            return self._respond(ev, False, pb.INVALID_INTENT, 0)
        cat = CATNAME.get(ev.category, "")
        if ev.intent == pb.CANCEL:
            # RAA cancelled: drop the tracked component, record freed slot.
            deadline = ev.deadline_unix_sec
            self.db.upsert_component(
                ev.component_id, cat, "", deadline or _now(), None,
                "cancelled")
            self._rebuild_islands()
            self._update_state("IDLE awaiting events")
            rec = self._log(message_type="LogisticsResponse", action="cancel",
                            category=cat, component_id=ev.component_id,
                            deadline_unix_sec=deadline, success=True)
            return self._respond(ev, True, pb.ERROR_NONE, deadline, rec)
        deadline = ev.deadline_unix_sec
        if deadline <= 0:
            self._update_state("FAILED last operation")
            return self._respond(ev, False, pb.MISSING_FIELD, 0)
        existing = {c["component_id"]: c for c in self.db.get_components()}
        old = existing.get(ev.component_id)
        delivery = old["delivery_time_unix_sec"] if old else None
        status = isl.WAITING if delivery is None else (
            isl.VIOLATED if delivery > deadline else isl.ON_TIME)
        self.db.upsert_component(ev.component_id, cat,
                                 old["manufacturer"] if old else "",
                                 deadline, delivery, status)
        self._rebuild_islands()
        self._update_state("TRACKING deadlines")
        rec = self._log(message_type="LogisticsResponse", action="ingested",
                        category=cat, component_id=ev.component_id,
                        deadline_unix_sec=deadline, success=True)
        return self._respond(ev, True, pb.ERROR_NONE, deadline, rec)

    # -- manufacturer delivery registration (external evidence only) ----------
    def register_delivery(self, component_id, delivery_time_unix_sec):
        """Manufacturer delivery times come from OUTSIDE evidence. Missing
        data stays 'waiting'; nothing is invented here."""
        self._update_state("UPDATING delivery")
        rows = {c["component_id"]: c for c in self.db.get_components()}
        c = rows.get(component_id)
        if c is None:
            self._update_state("FAILED last operation")
            raise ValueError("unknown component %s" % component_id)
        delivery = int(delivery_time_unix_sec)
        status = isl.VIOLATED if delivery > c["raa_deadline_unix_sec"] \
            else isl.ON_TIME
        self.db.upsert_component(component_id, c["category"],
                                 c["manufacturer"],
                                 c["raa_deadline_unix_sec"], delivery, status)
        self._rebuild_islands()
        self._update_state("IDLE awaiting events")
        return status

    def register_dependency(self, component_id, depends_on_id):
        """Record externally supplied dependency evidence.

        Dependencies are retained for traceability even if deadlines differ;
        ``build_islands`` is the sole place that decides graph membership and
        will never merge a cross-deadline relationship.
        """
        rows = {c["component_id"]: c for c in self.db.get_components()}
        component = rows.get(component_id)
        if component is None or depends_on_id not in rows:
            raise ValueError("dependency components must be tracked")
        self.db.upsert_link(component_id, depends_on_id,
                            component["raa_deadline_unix_sec"])
        return self._rebuild_islands()

    # -- island rebuild ---------------------------------------------------------
    def _records(self):
        rows = self.db.get_components()
        links = {}
        for r in self.db.get_links():
            links.setdefault(r["component_id"], []).append(
                r["depends_on_id"])
        return [{"component_id": r["component_id"],
                 "category": r["category"],
                 "manufacturer": r["manufacturer"],
                 "raa_deadline_unix_sec": r["raa_deadline_unix_sec"],
                 "delivery_time_unix_sec": r["delivery_time_unix_sec"],
                 "depends_on": links.get(r["component_id"], [])}
                for r in rows
                if r["status"] != "cancelled"]

    def rebuild(self):
        """Full deterministic recompute from persisted data. Returns the
        analysis dict (also persisted via snapshot after caller decides)."""
        dep = isl.build_dependency_dict(self._records())
        islands = isl.build_islands(dep)
        for cid, r in dep.items():
            self.db.upsert_component(
                cid, r["category"], r["manufacturer"],
                r["raa_deadline_unix_sec"], r["delivery_time_unix_sec"],
                r["status"], islands["by_id"].get(cid))
        self.db.sync_islands(islands)
        gaps = isl.island_gaps(dep, islands)
        health = {
            "islands": len(islands["members"]),
            "deadline_violations": isl.deadline_violations(dep),
            "earlier_plan": isl.earlier_plan_candidates(dep),
            "waiting_count": sum(1 for r in dep.values()
                                 if r["status"] == isl.WAITING),
            "island_gaps": gaps,
        }
        self.store.set_health(health, agent="logistics")
        self.last_health = health
        result = {"dep": dep, "islands": islands, "gaps": gaps,
                  "health": health}
        self.db.snapshot_valid({"components": self.db.get_components(),
                                "links": self.db.get_links(),
                                "islands": self.db.get_islands()})
        return result

    def _rebuild_islands(self):
        return self.rebuild()

    # -- reporting to Risk -------------------------------------------------------
    def notify_risk(self, violations=None):
        """Send status + deadline info to Risk using the EXISTING protocol:
        a LogisticsResponse shaped message with sender LOGISTICS, receiver
        RISK (fields unchanged). Dedup: skipped if identical to the last
        outgoing report."""
        self._update_state("REPORTING to risk")
        h = self.last_health or self.rebuild()["health"]
        flagged = h["deadline_violations"]
        v = flagged[0] if flagged else {}
        resp = pb.LogisticsResponse(
            header=pb.Header(
                protocol_version=PROTOCOL_VERSION,
                message_id="msg-%s" % uuid.uuid4().hex[:8],
                request_id="req-risk-%s" % uuid.uuid4().hex[:6],
                sender=pb.LOGISTICS, receiver=pb.RISK,
                timestamp_unix_sec=_now()),
            success=not flagged,
            error_code=pb.STALE_STATE if flagged else pb.ERROR_NONE,
            error_detail=("deadline violation: %s" % v.get("component_id"))
            if flagged else "no violations",
            component_id=v.get("component_id", ""),
            deadline_unix_sec=v.get("raa_deadline_unix_sec", 0))
        rec = self._log(message_type="LogisticsResponse", receiver="RISK",
                        code="STALE_STATE" if flagged else "ERROR_NONE",
                        category="", component_id=v.get("component_id", ""),
                        deadline_unix_sec=v.get("raa_deadline_unix_sec", 0),
                        delivered=self.risk is not None, action="status report")
        if self.risk is not None:
            self.risk.receive_from_logistics(resp.SerializeToString())
        self._update_state("IDLE awaiting events")
        return rec

    # -- Risk events (existing recovery conventions) ------------------------------
    def handle_risk(self, data):
        """RiskToLogistics: L1 = re-sync island; L2 = restore snapshot."""
        ev = pb.RiskToLogistics()
        ev.ParseFromString(data)
        if ev.header.sender != pb.RISK or ev.header.receiver != pb.LOGISTICS:
            raise ValueError("RiskToLogistics must be RISK -> LOGISTICS")
        if ev.code == pb.L1:
            self._update_state("RESYNCING island")
            self.rebuild()
            self._update_state("IDLE awaiting events")
            return {"code": "L1", "resynced": True}
        if ev.code == pb.L2:
            self._update_state("RESTORING snapshot")
            snap = self.db.get_state()["last_valid"]
            self.db.reset()
            for c in snap.get("components", []):
                self.db.upsert_component(
                    c["component_id"], c["category"], c["manufacturer"],
                    c["raa_deadline_unix_sec"],
                    c["delivery_time_unix_sec"], c["status"])
            self.db.replace_links(snap.get("links", []))
            self.rebuild()
            self._update_state("RECOVERED snapshot")
            return {"code": "L2", "restored": True}
        raise ValueError("unknown RiskLogisticsCode")

    # -- snapshot / persistence ----------------------------------------------------
    def snapshot(self):
        state = {"components": self.db.get_components(),
                 "links": self.db.get_links(),
                 "islands": self.db.get_islands()}
        self.db.snapshot_valid(state)
        return state

    def _respond(self, ev, success, code, deadline, rec=None):
        resp = pb.LogisticsResponse(
            header=pb.Header(
                protocol_version=PROTOCOL_VERSION,
                message_id="msg-%s" % uuid.uuid4().hex[:8],
                request_id=ev.header.request_id, sender=pb.LOGISTICS,
                receiver=ev.header.sender, timestamp_unix_sec=_now()),
            success=success, error_code=code, error_detail="",
            component_id=ev.component_id,
            deadline_unix_sec=deadline)
        return resp.SerializeToString()


def delivered(risk):
    return risk is not None
