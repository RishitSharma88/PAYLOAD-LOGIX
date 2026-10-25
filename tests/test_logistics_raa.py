"""Focused Logistics/RAA tests; uses isolated SQLite and Redis db 8."""
import os
import time
import tempfile
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PL_REDIS_URL"] = "redis://localhost:6379/8"
os.environ["PL_RISK_MODEL"] = "0"

from proto import payload_logix_pb2 as pb
from agents.state_store import AgentStateStore
from agents.logistics_agent import LogisticsAgent
from agents.raa_agent import RaaAgent
from agents.risk_agent import RiskAgent
import agents.raa_agent as raa_module
from logistics.islands import build_dependency_dict, build_islands
from raa.schedule import Schedule


class MemoryStore:
    """Isolated Redis-state-store contract double for offline tests."""
    def __init__(self):
        self.ok = True
        self.states = {}
        self.health = {}
        self.actions = {}

    def set_state(self, agent, line, updated):
        self.states[agent] = {"state": line, "updated": updated}

    def set_health(self, data, agent="payload"):
        self.health[agent] = dict(data)
        return True

    def get_state(self, agent):
        return self.states.get(agent)

    def get_health(self, agent="payload"):
        return self.health.get(agent)

    def last_action_ts(self, key):
        return self.actions.get(key)

    def mark_action(self, key, ts=None):
        self.actions[key] = time.time() if ts is None else ts
        return self.actions[key]

    def clear_actions(self):
        self.actions.clear()

    def recheck(self):
        return True


class RiskSink:
    def __init__(self):
        self.messages = []

    def receive_from_logistics(self, data):
        self.messages.append(data)


def test_matching_deadlines_only_form_islands():
    dep = build_dependency_dict([
        {"component_id": "A", "raa_deadline_unix_sec": 100,
         "depends_on": ["B"]},
        {"component_id": "B", "raa_deadline_unix_sec": 100},
        {"component_id": "C", "raa_deadline_unix_sec": 200,
         "depends_on": ["A"]},
    ])
    result = build_islands(dep)
    assert result["by_id"]["A"] == result["by_id"]["B"]
    assert result["by_id"]["C"] != result["by_id"]["A"]


def test_logistics_waiting_and_original_deadline():
    sink = RiskSink()
    a = LogisticsAgent(os.path.join(tempfile.mkdtemp(), "l.db"),
                       redis_url="redis://localhost:6379/8", risk=sink)
    a.store = MemoryStore()
    a.db.conn.execute("DELETE FROM component_logistics")
    a.db.conn.execute("DELETE FROM dependency_links")
    a.db.conn.commit()
    a.db.upsert_component("A", "RADIO", "Maker", 100, None, "waiting")
    a.rebuild()
    row = a.db.get_components()[0]
    assert row["status"] == "waiting"
    assert row["delivery_time_unix_sec"] is None
    a.register_delivery("A", 101)
    row = a.db.get_components()[0]
    assert row["raa_deadline_unix_sec"] == 100
    assert row["status"] == "violated"
    assert a.last_health["deadline_violations"][0]["late_by_s"] == 1
    a.notify_risk()
    report = pb.LogisticsResponse(); report.ParseFromString(sink.messages[0])
    assert report.header.receiver == pb.RISK and not report.success
    assert a.store.health["logistics"]["deadline_violations"]


def test_logistics_dependency_and_l1_l2_recovery():
    a = LogisticsAgent(os.path.join(tempfile.mkdtemp(), "l.db"),
                       redis_url="redis://localhost:6379/8")
    a.db.reset()
    for cid, deadline in (("A", 100), ("B", 100), ("C", 200)):
        a.db.upsert_component(cid, "RADIO", "", deadline, None, "waiting")
    a.register_dependency("A", "B")
    a.register_dependency("C", "A")
    result = a.rebuild()
    assert result["islands"]["by_id"]["A"] == result["islands"]["by_id"]["B"]
    assert result["islands"]["by_id"]["C"] != result["islands"]["by_id"]["A"]
    l1 = pb.RiskToLogistics(header=pb.Header(sender=pb.RISK,
                              receiver=pb.LOGISTICS), code=pb.L1)
    assert a.handle_risk(l1.SerializeToString())["resynced"]
    a.db.conn.execute("DELETE FROM component_logistics")
    a.db.conn.execute("DELETE FROM dependency_links")
    a.db.conn.commit()
    l2 = pb.RiskToLogistics(header=pb.Header(sender=pb.RISK,
                              receiver=pb.LOGISTICS), code=pb.L2)
    assert a.handle_risk(l2.SerializeToString())["restored"]
    assert len(a.db.get_components()) == 3 and len(a.db.get_links()) == 2


def test_schedule_order_lookup_reschedule():
    s = Schedule()
    a = s.upsert("A", "RADIO", 300)
    b = s.upsert("B", "RADIO", 100)
    assert [x["component_id"] for x in s.order()] == ["B", "A"]
    assert s.find(a.event_id) is a
    s.upsert("A", "RADIO", 50)
    assert [x["component_id"] for x in s.order()] == ["A", "B"]


def _raa_cmd(intent, cid, deadline):
    return pb.RaaCommand(
        header=pb.Header(protocol_version="1.0", message_id="m",
                         request_id="r", sender=pb.SLM, receiver=pb.RAA,
                         timestamp_unix_sec=int(time.time())),
        intent=intent, category=pb.RADIO, component_id=cid,
        deadline_unix_sec=deadline).SerializeToString()


def test_raa_persistence_and_r2():
    path = os.path.join(tempfile.mkdtemp(), "r.db")
    a = RaaAgent(path, redis_url="redis://localhost:6379/8")
    a.db.reset()
    a.handle_command(_raa_cmd(pb.SCHEDULE, "A", 300))
    a.handle_command(_raa_cmd(pb.SCHEDULE, "B", 100))
    assert [x["component_id"] for x in a.schedule.order()] == ["B", "A"]
    b = RaaAgent(path, redis_url="redis://localhost:6379/8")
    assert [x["component_id"] for x in b.schedule.order()] == ["B", "A"]
    ev = pb.RiskToRaa(header=pb.Header(sender=pb.RISK, receiver=pb.RAA),
                      code=pb.R2)
    assert b.handle_risk(ev.SerializeToString())["restored"] == 2


def test_raa_json_forwarding_cancel_and_r1():
    l = LogisticsAgent(os.path.join(tempfile.mkdtemp(), "l.db"),
                       redis_url="redis://localhost:6379/8")
    a = RaaAgent(os.path.join(tempfile.mkdtemp(), "r.db"),
                 redis_url="redis://localhost:6379/8", logistics=l)
    a.db.reset()
    a.handle_json({"intent": "SCHEDULE", "category": "RADIO",
                   "component_id": "A", "deadline_unix_sec": 300})
    a.handle_json({"intent": "RESCHEDULE", "category": "RADIO",
                   "component_id": "A", "deadline_unix_sec": 200})
    assert l.db.get_components()[0]["raa_deadline_unix_sec"] == 200
    a.handle_command(_raa_cmd(pb.CANCEL, "A", 0))
    assert a.db.get_events(status="cancelled")[0]["event_id"] == "A@RADIO"
    assert a.db.get_free_slots()
    # R1 carries no deadline, so chronological ordering is preserved.
    a.handle_command(_raa_cmd(pb.SCHEDULE, "B", 400))
    ev = pb.RiskToRaa(header=pb.Header(sender=pb.RISK, receiver=pb.RAA),
                      code=pb.R1, detail="B@RADIO")
    assert a.handle_risk(ev.SerializeToString())["code"] == "R1"


def test_redis_health_and_protocol():
    a = RaaAgent(os.path.join(tempfile.mkdtemp(), "r.db"),
                 redis_url="redis://localhost:6379/8")
    store = MemoryStore()
    a.store = store
    a.db.reset()
    resp = pb.RaaResponse()
    resp.ParseFromString(a.handle_command(_raa_cmd(pb.SCHEDULE, "A", 100)))
    assert resp.success and resp.header.sender == pb.RAA
    assert store.states["raa"]["state"] == "IDLE awaiting commands"
    assert store.health["raa"]["events"] == 1


def test_e2e_slm_raa_logistics_risk_violation_and_retries():
    """One deterministic, isolated SLM -> RAA -> Logistics -> Risk flow.

    The external manufacturer is represented by ``register_delivery``: the
    timestamp supplied here is evidence, not a generated delivery estimate.
    Redis is unavailable in this sandbox, so a state-store contract double
    owns all temporary keys; no project Redis database or SQLite file is
    touched.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore()
        original_now = raa_module._now
        raa_module._now = lambda: 1000
        l = LogisticsAgent(os.path.join(tmp, "logistics.db"),
                           redis_url="redis://localhost:6379/8")
        r = RaaAgent(os.path.join(tmp, "raa.db"),
                     redis_url="redis://localhost:6379/8", logistics=l)
        l.store = store
        r.store = store
        # Avoid mutating shared config state files while still exercising the
        # Redis state transitions used by the real agents.
        l._update_state = lambda line: store.set_state(
            "logistics", line, int(time.time()))
        r._update_state = lambda line: store.set_state(
            "raa", line, int(time.time()))
        try:
            first = {"intent": "SCHEDULE", "category": "RADIO",
                     "component_id": "RADIO_A", "deadline_unix_sec": 1600,
                     "request_id": "e2e-a"}
            r.handle_json(first)
            r.handle_json({"intent": "SCHEDULE", "category": "RADIO",
                           "component_id": "RADIO_B",
                           "deadline_unix_sec": 1600,
                           "request_id": "e2e-b"})
            # Retry exactly the same SLM JSON: upsert retains one node and
            # RAA does not emit another Logistics scheduling message.
            before_forward = len(l.outgoing)
            r.handle_json(first)
            assert len(r.schedule) == 2 and len(l.outgoing) == before_forward
            order = r.schedule.order()
            assert order[0]["component_id"] == "RADIO_A"
            assert order[0]["duration_s"] == 600

            l.register_dependency("RADIO_A", "RADIO_B")
            islands = l.rebuild()["islands"]
            assert islands["by_id"]["RADIO_A"] == islands["by_id"]["RADIO_B"]
            # Mocked manufacturer evidence: one second after original RAA
            # deadline. Logistics must preserve 1600 rather than extend it.
            assert l.register_delivery("RADIO_A", 1601) == "violated"
            component = {x["component_id"]: x for x in l.db.get_components()}["RADIO_A"]
            assert component["raa_deadline_unix_sec"] == 1600
            assert l.last_health["deadline_violations"][0]["late_by_s"] == 1

            risk = RiskAgent(logistics=l, redis_url="redis://localhost:6379/8",
                             use_model=False, log_sink=lambda record: None,
                             stale_after_s=9999, dedup_window_s=60)
            risk.store = store
            risk._update_state = lambda line: store.set_state(
                "risk", line, int(time.time()))
            store.set_state("payload", "IDLE awaiting commands", int(time.time()))
            # Two matching polls are required before Risk sends L1.
            assert risk.poll_once()["acted"] is False
            acted = risk.poll_once()
            assert acted["acted"] is True
            assert risk.sent[-1]["code"] == "L1"
            assert risk.sent[-1]["receiver"] == "LOGISTICS"
            assert l.db.get_state()["last_valid"]["components"]
            assert l.db.get_links()
            assert len(r.db.get_events(status="scheduled")) == 2
            assert store.get_health("raa")["events"] == 2
            assert store.get_health("logistics")["deadline_violations"]
            # Same evidence remains deduplicated after L1 recovery.
            sent = len(risk.sent)
            risk.poll_once()
            assert len(risk.sent) == sent
        finally:
            raa_module._now = original_now


if __name__ == "__main__":
    tests = [v for k, v in globals().items()
             if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print("PASS:", test.__name__)
    print("ALL %d CHECKS PASSED" % len(tests))
