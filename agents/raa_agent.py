"""Resource Allocation Agent (RAA): deterministic scheduling spoke.

Reuses (no duplication): agents/master_state.py + agents/state_store.py
(Redis mirror, keys pl:state:raa / pl:updated:raa / pl:raa:health),
RaaCommand/RaaResponse/RiskToRaa protobuf messages (fields unchanged),
payload_db.py snapshot-recovery conventions, and payload_agent.py state
transition style.

Data structures (spec): doubly linked list + hash map for scheduling
(raa/schedule.py); SQLite persistence of schedule events, dependency-island
gaps and free slots (raa/db.py). Durations are derived dynamically from the
SLM-provided deadlines (no task-duration CSV exists — user decision).
"""
import json
import time
import uuid

from proto import payload_logix_pb2 as pb
from agents import master_state
from agents.state_store import AgentStateStore
from raa import schedule as sched
from raa.db import RaaDB

PROTOCOL_VERSION = "1.0"

CATNAME = {pb.RADIO: "RADIO", pb.REACTION_WHEEL: "REACTION_WHEEL",
           pb.PMAD: "PMAD", pb.SATELLITE: "SATELLITE"}


def _now():
    return int(time.time())


class RaaAgent:
    def __init__(self, db_path=None, redis_url=None, logistics=None,
                 risk=None):
        self.db = RaaDB(path=db_path) if db_path else RaaDB()
        try:
            self.prompt = master_state.load_prompt("raa")
        except OSError:
            self.prompt = ""
        self.store = AgentStateStore(url=redis_url)
        self.logistics = logistics
        self.risk = risk
        self.schedule = sched.Schedule()
        # reload persisted events (persistence survives restarts)
        self.schedule.restore(self.db.get_events(status="scheduled"))
        saved = self.db.get_state()["last_valid"]
        self.schedule_start = int(saved.get("schedule_start_unix_sec") or
                                  _now())
        self.outgoing = []

    # -- master state -----------------------------------------------------------
    def _update_state(self, line):
        try:
            info = master_state.set_state("raa", line)
            self.store.set_state("raa", info["state"], info["updated"])
        except Exception:
            pass

    def _log(self, **record):
        record.setdefault("ts", round(time.time(), 3))
        record.setdefault("sender", "RAA")
        record.setdefault("protocol_version", PROTOCOL_VERSION)
        self.outgoing.append(record)
        try:
            import sys
            sys.stdout.write("RAA-MSG> %s\n" % json.dumps(record,
                             sort_keys=True, default=str))
            sys.stdout.flush()
        except Exception:
            pass
        return record

    def _publish(self):
        order = self.schedule.order()
        health = {"events": len(order),
                  "next_deadline": order[0]["deadline_unix_sec"] if order
                  else 0,
                  "gaps": len(self.db.get_island_gaps()),
                  "free_slots": len(self.db.get_free_slots())}
        self.store.set_health(health, agent="raa")
        return health

    # -- SLM/JSON ingestion (existing RaaCommand protobuf) --------------------------
    def handle_command(self, data):
        self._update_state("VALIDATING command")
        cmd = pb.RaaCommand()
        try:
            cmd.ParseFromString(data)
        except Exception:
            self._update_state("FAILED last operation")
            raise
        if cmd.header.sender != pb.SLM or cmd.header.receiver != pb.RAA:
            self._update_state("FAILED last operation")
            return self._respond(cmd, False, pb.INVALID_SENDER, 0)
        if cmd.intent not in (pb.SCHEDULE, pb.RESCHEDULE, pb.CANCEL):
            self._update_state("FAILED last operation")
            return self._respond(cmd, False, pb.INVALID_INTENT, 0)
        cat = CATNAME.get(cmd.category, "")
        deadline = cmd.deadline_unix_sec
        if cmd.intent != pb.CANCEL and deadline <= 0:
            self._update_state("FAILED last operation")
            return self._respond(cmd, False, pb.MISSING_FIELD, 0)

        if cmd.intent == pb.SCHEDULE or cmd.intent == pb.RESCHEDULE:
            return self._upsert_event(cmd, cat, deadline)
        return self._cancel_event(cmd, cat)

    def _upsert_event(self, cmd, cat, deadline):
        self._update_state("SCHEDULING event" if cmd.intent == pb.SCHEDULE
                           else "RESCHEDULING event")
        # ordering reconsideration is chronological; order_index breaks ties
        old = self.schedule.find("%s@%s" % (cmd.component_id, cat))
        changed = old is None or (old.deadline_unix_sec != int(deadline) or
                                  old.order_index != int(cmd.order_index))
        # A byte-for-byte retry is a scheduling no-op.  Besides avoiding a
        # duplicate Logistics message, retaining the existing node preserves
        # stable order among equal-deadline events.
        if changed:
            node = self.schedule.upsert(cmd.component_id, cat, deadline,
                                        schedule_start=self.schedule_start,
                                        order_index=cmd.order_index)
        else:
            node = old
        # A repeated protobuf command is a retry, not a second Logistics
        # message. Changed schedules are forwarded with their real intent.
        forward = changed
        ev_id = node.event_id
        self._persist_schedule()
        rec = self._log(message_type="RaaResponse", action="scheduled",
                        category=cat, component_id=cmd.component_id,
                        deadline_unix_sec=deadline,
                        duration_s=node.duration_s)
        # tell Logistics (sender RAA) via existing LogisticsCommand fields
        if self.logistics is not None and forward:
            msg = pb.LogisticsCommand(
                header=pb.Header(
                    protocol_version=PROTOCOL_VERSION,
                    message_id="msg-%s" % uuid.uuid4().hex[:8],
                    request_id="req-raa-%s" % uuid.uuid4().hex[:6],
                    sender=pb.RAA, receiver=pb.LOGISTICS,
                    timestamp_unix_sec=_now()),
                intent=(pb.SCHEDULE if cmd.intent == pb.SCHEDULE
                        else pb.RESCHEDULE), category=cmd.category,
                component_id=cmd.component_id, quantity=0,
                deadline_unix_sec=deadline)
            try:
                self.logistics.ingest_raa(msg.SerializeToString())
                delivered = True
            except Exception as e:
                delivered = False
                rec["error"] = str(e)
            rec["delivered"] = delivered
        self._update_state("IDLE awaiting commands")
        return self._respond(cmd, True, pb.ERROR_NONE, node.order_index)

    def handle_json(self, command):
        """Accept the SLM's already-interpreted JSON scheduling command.

        Qwen remains responsible for natural-language-to-JSON conversion in
        the orchestrator.  This boundary only validates and maps that JSON
        into the existing protobuf; it neither reads nor creates a duration
        CSV.
        """
        if isinstance(command, str):
            command = json.loads(command)
        intents = {"SCHEDULE": pb.SCHEDULE, "RESCHEDULE": pb.RESCHEDULE,
                   "CANCEL": pb.CANCEL}
        categories = {"RADIO": pb.RADIO,
                      "REACTION_WHEEL": pb.REACTION_WHEEL,
                      "PMAD": pb.PMAD, "SATELLITE": pb.SATELLITE}
        intent = intents.get(command.get("intent"))
        category = categories.get(command.get("category"))
        if intent is None or category is None:
            raise ValueError("invalid RAA JSON intent or category")
        msg = pb.RaaCommand(
            header=pb.Header(protocol_version=PROTOCOL_VERSION,
                             message_id="msg-%s" % uuid.uuid4().hex[:8],
                             request_id=command.get("request_id") or
                             "req-%s" % uuid.uuid4().hex[:8],
                             sender=pb.SLM, receiver=pb.RAA,
                             timestamp_unix_sec=_now()),
            intent=intent, category=category,
            component_id=command.get("component_id") or "",
            deadline_unix_sec=int(command.get("deadline_unix_sec") or 0),
            priority=int(command.get("priority") or 0),
            order_index=int(command.get("order_index") or 0))
        return self.handle_command(msg.SerializeToString())

    def _cancel_event(self, cmd, cat):
        self._update_state("CANCELLING event")
        node = self.schedule.cancel(cmd.component_id, cat)
        if node is None:
            self._update_state("FAILED last operation")
            return self._respond(cmd, False, pb.UNKNOWN_COMPONENT, 0)
        self.db.add_free_slot(node.deadline_unix_sec, _now())
        self.db.mark_event(node.event_id, "cancelled")
        self._persist_schedule()
        self._log(message_type="RaaResponse", action="cancelled",
                  category=cat, component_id=cmd.component_id,
                  deadline_unix_sec=node.deadline_unix_sec)
        if self.logistics is not None:
            msg = pb.LogisticsCommand(
                header=pb.Header(
                    protocol_version=PROTOCOL_VERSION,
                    message_id="msg-%s" % uuid.uuid4().hex[:8],
                    request_id=cmd.header.request_id, sender=pb.RAA,
                    receiver=pb.LOGISTICS, timestamp_unix_sec=_now()),
                intent=pb.CANCEL, category=cmd.category,
                component_id=cmd.component_id, deadline_unix_sec=
                node.deadline_unix_sec)
            try:
                self.logistics.ingest_raa(msg.SerializeToString())
            except Exception as e:
                self.outgoing[-1]["error"] = str(e)
        self._update_state("IDLE awaiting commands")
        return self._respond(cmd, True, pb.ERROR_NONE, 0)

    def _persist_schedule(self):
        for e in self.schedule.order():
            self.db.upsert_event(e["event_id"], e["component_id"],
                                 e["category"], e["deadline_unix_sec"],
                                 e["duration_s"], e["order_index"])
        self.db.snapshot_valid({"events": self.schedule.order(),
                                "schedule_start_unix_sec":
                                self.schedule_start})
        self._publish()

    # -- Logistics evidence -------------------------------------------------------
    def ingest_logistics(self, data):
        """Evidence from Logistics (LogisticsResponse-shaped, sender
        LOGISTICS receiver RAA). A failed report marks a dependency-island
        gap for that component — enumerated only, never filled."""
        self._update_state("INGESTING gaps")
        msg = pb.LogisticsResponse()
        msg.ParseFromString(data)
        if msg.header.sender != pb.LOGISTICS or \
                msg.header.receiver != pb.RAA:
            raise ValueError("gap evidence must be LOGISTICS -> RAA")
        recorded = 0
        if not msg.success and msg.component_id:
            self.db.upsert_island_gaps([{
                "island_id": "ISLAND_%d" % msg.deadline_unix_sec,
                "component_id": msg.component_id,
                "reason": "reported by Logistics: %s" %
                          (msg.error_detail or "unspecified")}])
            recorded = 1
        self._publish()
        self._update_state("IDLE awaiting commands")
        return {"recorded": recorded}

    def record_island_gaps(self, gaps):
        """Persist real dependency-island gaps reported by Logistics."""
        if not gaps:
            return 0
        self.db.upsert_island_gaps(gaps)
        self._publish()
        return len(gaps)

    # -- Risk events ---------------------------------------------------------------
    def handle_risk(self, data):
        """RiskToRaa: R1 = reorder to an earlier slot; R2 = restore."""
        ev = pb.RiskToRaa()
        ev.ParseFromString(data)
        if ev.header.sender != pb.RISK or ev.header.receiver != pb.RAA:
            raise ValueError("RiskToRaa must be RISK -> RAA")
        if ev.code == pb.R1:
            return self._reorder_earlier(ev.detail)
        if ev.code == pb.R2:
            self._update_state("RESTORING snapshot")
            snap = self.db.get_state()["last_valid"].get("events", [])
            self.schedule.restore(snap)
            self.db.replace_scheduled_events(snap)
            self._update_state("RECOVERED snapshot")
            return {"code": "R2", "restored": len(snap)}
        raise ValueError("unknown RiskRaaCode")

    def _reorder_earlier(self, detail):
        """R1: move the named event into the earliest slot consistent with
        its dependency context (local splices; NO full rebuild). The event
        identity is carried in detail as 'component_id@category'."""
        self._update_state("REORDERING events")
        target = None
        for node in self.schedule.dll.iter_from():
            if node.event_id in detail:
                target = node
                break
        if target is None:
            self._update_state("FAILED last operation")
            return {"code": "R1", "moved": False,
                    "reason": "event not found"}
        head = self.schedule.dll.head
        if target is head:
            self._update_state("IDLE awaiting commands")
            return {"code": "R1", "moved": False, "reason": "already first"}
        # The list's invariant is chronological deadline order.  An R1
        # notice carries no replacement deadline, so it can only trigger a
        # local reconsideration/recalculation; moving it ahead of an earlier
        # deadline would fabricate an invalid schedule.
        self.schedule._recompute_durations(self.schedule_start)
        self._persist_schedule()
        self._log(message_type="RaaResponse", action="reordered earlier",
                  component_id=target.component_id,
                  deadline_unix_sec=target.deadline_unix_sec)
        self._update_state("IDLE awaiting commands")
        return {"code": "R1", "moved": False, "reason": "deadline order"}

    # -- response helper -----------------------------------------------------------
    def _respond(self, cmd, success, code, order_index):
        resp = pb.RaaResponse(
            header=pb.Header(
                protocol_version=PROTOCOL_VERSION,
                message_id="msg-%s" % uuid.uuid4().hex[:8],
                request_id=cmd.header.request_id, sender=pb.RAA,
                receiver=pb.SLM, timestamp_unix_sec=_now()),
            success=success, error_code=code, error_detail="",
            order_index=order_index)
        return resp.SerializeToString()
