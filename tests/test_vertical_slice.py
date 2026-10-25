"""Validation tests for the PAYLOAD-LOGIX vertical slice.

Run: venv/bin/python tests/test_vertical_slice.py
Covers: valid request, invalid request (clarify), invalid protocol value,
P1 fallback, P2 restore. CAG demos live in demo_cag.py.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto import payload_logix_pb2 as pb
from orchestrator import protocol
from orchestrator.slm import Orchestrator

PASS = []


def check(name, cond, extra=""):
    assert cond, "FAIL: %s %s" % (name, extra)
    PASS.append(name)
    print("PASS: %s %s" % (name, extra))


def test_valid_request(o):
    o.payload.reset()
    t = o.run("I want to add a radio with mass 0.2 kg, power 2 W and "
              "volume 120 cm3 to the payload.")
    c = t["command_dict"]
    check("valid: receiver PAYLOAD", c["receiver"] == "PAYLOAD")
    check("valid: intent ADD", c["intent"] == "ADD")
    check("valid: category RADIO", c["category"] == "RADIO")
    check("valid: units kg/W/cm3",
          c["mass_kg"] == 0.2 and c["power_w"] == 2.0
          and c["volume_cm3"] == 120.0)
    check("valid: agent success", t["response_dict"]["success"] is True)
    check("valid: blueprint has radio",
          any(x["category"] == "RADIO"
              for x in o.payload.blueprint["components"]))
    check("valid: final mentions component",
          t["response_dict"]["component_id"] in t["final"])


def test_invalid_request_clarify(o):
    t = o.run("Add something to the payload.")
    check("invalid: clarification asked", "clarify" in t["command_dict"],
          json.dumps(t["command_dict"])[:120])


def test_invalid_protocol_value():
    for bad in ({"receiver": "PAYLOAD", "intent": "DELETE",
                 "category": "RADIO", "quantity": 1},
                {"receiver": "PAYLOAD", "intent": "ADD",
                 "category": "ANTENNA", "quantity": 1},
                {"receiver": "RISK", "intent": "ADD",
                 "category": "RADIO", "quantity": 1}):
        try:
            protocol.command_from_dict(bad)
            raise SystemExit("FAIL: accepted %r" % bad)
        except ValueError:
            pass
    check("invalid protocol values rejected", True)
    # ... and the agent itself rejects a malformed command on the wire.
    o2 = Orchestrator()
    cmd = pb.PayloadCommand(
        header=protocol.new_header(pb.SLM, pb.PAYLOAD),
        intent=pb.PAYLOAD_INTENT_UNSPECIFIED, category=pb.RADIO, quantity=1)
    raw = o2.payload.handle_command(cmd.SerializeToString())
    resp = pb.PayloadResponse()
    resp.ParseFromString(raw)
    check("agent rejects unspecified intent",
          resp.success is False
          and resp.error_code == pb.INVALID_INTENT)


def test_p1_fallback(o):
    o.payload.reset()
    o.run("Add a radio with mass 0.2 kg, power 2 W and volume 120 cm3.")
    first = o.payload.cache["selected"]["RADIO"]
    ranked = o.payload.cache["ranked"]["RADIO"]
    assert len(ranked) > 1, "need >1 cached candidate for P1 test"
    ev = pb.RiskToPayload(
        header=protocol.new_header(pb.RISK, pb.PAYLOAD),
        code=pb.P1, category=pb.RADIO, component_id=first,
        detail="deadline invalid for selected component")
    nxt = o.payload.handle_risk(ev.SerializeToString())
    check("P1: switched to next cached candidate",
          nxt != first and nxt in ranked, "%s -> %s" % (first, nxt))
    check("P1: blueprint follows",
          any(c["component_id"] == nxt
              for c in o.payload.blueprint["components"]))


def test_p2_restore(o):
    o.payload.reset()
    o.run("Add a radio with mass 0.2 kg, power 2 W and volume 120 cm3.")
    good = json.loads(json.dumps(o.payload.blueprint))
    o.payload.blueprint["components"].append(
        {"component_id": "CORRUPT", "category": "RADIO"})
    ev = pb.RiskToPayload(header=protocol.new_header(pb.RISK, pb.PAYLOAD),
                          code=pb.P2, detail="packet mismatch")
    o.payload.handle_risk(ev.SerializeToString())
    check("P2: last valid state restored", o.payload.blueprint == good)


if __name__ == "__main__":
    o = Orchestrator()
    test_valid_request(o)
    test_invalid_request_clarify(o)
    test_invalid_protocol_value()
    test_p1_fallback(o)
    test_p2_restore(o)
    print("\nALL %d CHECKS PASSED" % len(PASS))
