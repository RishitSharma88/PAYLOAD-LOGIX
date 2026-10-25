"""Master prompts/states + Risk Agent monitor tests.

Run: venv/bin/python tests/test_master_agents.py
Uses a separate SQLite DB and separate Redis DB (PL_REDIS_URL db 6) so the
live payload state is never touched. Model assessment disabled (PL_RISK_MODEL
=0) so the suite is deterministic and fast; the model config path is still
verified via payload.slm constants.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

os.environ["PL_REDIS_URL"] = "redis://localhost:6379/6"
os.environ["PL_RISK_MODEL"] = "0"
for k in ("PL_RISK_POLL_SEC", "PL_RISK_DEDUP_SEC", "PL_RISK_STALE_SEC"):
    os.environ.pop(k, None)

from proto import payload_logix_pb2 as pb              # noqa: E402
from agents import master_state                        # noqa: E402
from agents.state_store import AgentStateStore         # noqa: E402
from agents.payload_agent import PayloadAgent          # noqa: E402
from agents.risk_agent import RiskAgent                # noqa: E402
from payload import slm as pintel                      # noqa: E402

PASS = []


def check(name, cond, extra="", skip=False):
    if skip:
        print("SKIP: %s" % name)
        return
    assert cond, "FAIL: %s %s" % (name, extra)
    PASS.append(name)
    print("PASS: %s %s" % (name, extra))


def satellite_cmd():
    return pb.PayloadCommand(
        header=pb.Header(protocol_version="1.0", message_id="t-sat",
                         request_id="req-t-sat", sender=pb.SLM,
                         receiver=pb.PAYLOAD,
                         timestamp_unix_sec=int(time.time())),
        intent=pb.ADD, category=pb.SATELLITE,
        constraints=pb.Constraints(max_mass_kg=25.0, max_power_w=100.0,
                                   max_volume_cm3=50000.0)
    ).SerializeToString()


def ensure_redis():
    cli = "/opt/homebrew/opt/redis/bin/redis-cli"
    try:
        out = subprocess.run([cli, "ping"], capture_output=True, text=True,
                             timeout=5)
        if out.stdout.strip() == "PONG":
            return True
    except Exception:
        pass
    subprocess.run(["/opt/homebrew/opt/redis/bin/redis-server",
                    "--daemonize", "yes", "--port", "6379", "--save", "",
                    "--appendonly", "no"], timeout=15)
    try:
        out = subprocess.run([cli, "ping"], capture_output=True, text=True,
                             timeout=5)
        return out.stdout.strip() == "PONG"
    except Exception:
        return False


REDIS_UP = ensure_redis()
check("0: redis server reachable", REDIS_UP)

store = AgentStateStore()
if REDIS_UP:
    store._op(lambda r: r.flushdb())
for agent in ("payload", "risk"):
    master_state.set_state(agent, "IDLE awaiting commands" if
                           agent == "payload" else "STOPPED idle")

agent = PayloadAgent(db_path="/tmp/payload_master_test.db")
agent.db.reset()

# ---------------------------------------------------------------- prompts
p_prompt = master_state.load_prompt("payload")
r_prompt = master_state.load_prompt("risk")
check("1: payload master prompt loads",
      "Payload Agent" in p_prompt and "RESPONSIBILITIES" in p_prompt and
      "PROTOCOL" in p_prompt and "FAILURE HANDLING" in p_prompt)
check("2: risk master prompt loads",
      "Risk Agent" in r_prompt and "P1" in r_prompt and "L1" in r_prompt and
      "R1" in r_prompt and "dedup" in r_prompt)
agent_prompt = PayloadAgent(db_path="/tmp/payload_master_test.db").prompt
check("3: PayloadAgent carries master prompt",
      agent_prompt == p_prompt)

# ---------------------------------------------------------------- states
for agent_name in ("payload", "risk"):
    st = master_state.read_state(agent_name)
    check("4: %s state file format (<=3 words + updated)" % agent_name,
          len(st["state"].split()) <= 3 and isinstance(st["updated"], int),
          str(st))
try:
    master_state.set_state("payload", "TOO MANY WORDS HERE")
    raises = False
except ValueError:
    raises = True
check("5: >3-word state line rejected", raises)
master_state.set_state("payload", "IDLE awaiting commands")

# special: risk initial state
check("6: risk starts STOPPED idle",
      master_state.read_state("risk")["state"] == "STOPPED idle")

# ---------------------------------------------- payload state transitions
out = agent.handle_command(satellite_cmd())
resp = pb.PayloadResponse(); resp.ParseFromString(out)
check("7: satellite thresholds accepted", resp.success)
st = master_state.read_state("payload")
check("8: payload state IDLE after success",
      st["state"] == "IDLE awaiting commands", str(st))
mirrored = store.get_state("payload")
check("9: payload state mirrored to redis",
      mirrored and mirrored["state"] == st["state"] and
      mirrored["updated"] == st["updated"])
health = store.get_health()
check("10: health evidence written",
      health and health["success"] is True and health["error_code"] == 0
      and health["category"] == "SATELLITE", str(health))

agent.handle_command(b"\x00garbage")
st = master_state.read_state("payload")
health = store.get_health()
check("11: failure transition recorded",
      st["state"] == "FAILED last operation" and not health["success"] and
      health["error_code"] == int(pb.VALIDATION_ERROR))

# ---------------------------------------------------- risk init & polling
os.environ.pop("PL_RISK_POLL_SEC", None)
risk_default = RiskAgent(payload=agent, use_model=False)
check("12: default poll interval 10s",
      risk_default.poll_interval == 10.0, str(risk_default.poll_interval))
os.environ["PL_RISK_POLL_SEC"] = "0.05"
risk_env = RiskAgent(payload=agent, use_model=False)
check("13: PL_RISK_POLL_SEC configurable",
      risk_env.poll_interval == 0.05)
os.environ.pop("PL_RISK_POLL_SEC", None)

risk = RiskAgent(payload=agent, log_sink=lambda rec: None, use_model=False,
                 poll_interval=0.05, stale_after_s=999.0,
                 dedup_window_s=5.0)
check("14: risk loads its master prompt", risk.prompt == r_prompt)
check("15: stale window defaults sane when configured",
      risk.stale_after_s == 999.0)

store._op(lambda r: r.delete("pl:state:payload", "pl:updated:payload"))
out = risk.poll_once()
check("16: no payload state -> nothing acted",
      out["acted"] is False and out["reason"] == "no_payload_state")
# restore mirror for later tests
store.set_state("payload", "IDLE awaiting commands")
os.environ["PL_RISK_POLL_SEC"] = "0.05"  # restore default-env test frame

# degraded: unreachable redis
bad = RiskAgent(payload=agent, use_model=False, poll_interval=0.05,
                redis_url="redis://localhost:9/6",
                stale_after_s=999.0)
out = bad.poll_once()
check("17: redis down -> degraded, no crash",
      out["acted"] is False and out["reason"] == "redis_unavailable" and
      bad.poll_count == 1 and bad.sent == [])
bad.stop()

# ------------------------------------- FAILED_PERSISTENT -> P2 (two polls)
calls = []
_orig = agent.handle_risk


def counting(data):
    calls.append(data)
    return _orig(data)


agent.handle_risk = counting

store.set_health({"success": False, "error_code": int(pb.VALIDATION_ERROR),
                  "error_detail": "satellite thresholds violated",
                  "component_id": "", "category": "", "quantity": 0})
r = RiskAgent(payload=agent, log_sink=lambda rec: None, use_model=False,
              poll_interval=0.05, stale_after_s=999.0, dedup_window_s=5.0)
check("18: first poll only records evidence (no fire)",
      r.poll_once()["acted"] is False and not calls)
res = r.poll_once()
check("19: second poll fires P2 recovery",
      res["acted"] is True and calls and len(calls) == 1)
ev = pb.RiskToPayload(); ev.ParseFromString(calls[0])
check("20: P2 event is RISK->PAYLOAD",
      ev.header.sender == pb.RISK and ev.header.receiver == pb.PAYLOAD and
      ev.code == pb.P2)
check("21: risk state updated after recovery",
      master_state.read_state("risk")["state"] == "RECOVERING state")

# dedup: same evidence again -> no new message
poll = r.poll_once()
check("22: duplicate suppressed within window",
      calls and len(calls) == 1 and r.poll_count == 3)

record = r.sent[0]
required = ("ts", "sender", "receiver", "message_type", "code", "category",
            "component_id", "deadline_unix_sec", "delivered", "action")
check("23: outgoing JSON log has required fields",
      all(k in record for k in required), json.dumps(record, default=str)[:160])
check("24: JSON record values correct",
      record["sender"] == "RISK" and record["receiver"] == "PAYLOAD" and
      record["code"] == "P2" and record["message_type"] == "RiskToPayload"
      and record["delivered"] is True and record["deadline_unix_sec"] == 0)

# ---------------------------------------------- UNKNOWN => P1 advancement
# Real P1 flow: RADIO_001 ("Trident") was previously selected and is now
# reported invalid; P1 advances to the next cached candidate RADIO_003
# ("NI Ettus Research", 0.024 kg / 10.0 W / 338.64 cm3 -- passes 25/100/50000).
agent.db.upsert_component("RADIO_001", "RADIO", quantity=1,
                          manufacturer="Trident", mass_kg=0.69,
                          power_w=2.8, volume_cm3=370.84)
agent.db.snapshot_valid(agent.db.get_components(),
                        {"RADIO": ["RADIO_001", "RADIO_003"]})
store.clear_actions()
r2 = RiskAgent(payload=agent, log_sink=lambda rec: None, use_model=False,
               poll_interval=0.05, stale_after_s=999.0, dedup_window_s=5.0)
r2.poll_once()  # observe leftover evidence from previous scenario (poll 1)
store.set_health({"success": False, "error_code": int(pb.UNKNOWN_COMPONENT),
                  "error_detail": "no candidate fits constraints",
                  "component_id": "RADIO_001", "category": "RADIO",
                  "quantity": 1})
r2.poll_once()  # fresh fingerprint: poll 2 records only
r2.poll_once()  # confirmed -> P1
check("25: persistent UNKNOWN fires P1",
      calls and len(calls) == 2, "%d calls" % len(calls))
ev = pb.RiskToPayload(); ev.ParseFromString(calls[1])
check("26: P1 event for RADIO", ev.code == pb.P1 and ev.category == pb.RADIO
      and ev.component_id == "RADIO_001")
placed = [c["component_id"] for c in agent.get_blueprint()]
check("27: P1 advanced to next-best cached candidate",
      "RADIO_003" in placed and "RADIO_001" not in placed, str(placed))
rec = r2.sent[-1]
check("28: P1 JSON log carries category+component",
      rec["code"] == "P1" and rec["category"] == "RADIO" and
      rec["component_id"] == "RADIO_001")

# dedup across agents storage: same evidence again -> suppressed
before = len(calls)
r2.poll_once()
check("29: P1 dedup suppresses repeat",
      len(calls) == before)

# ----------------------------------------------------- STALE activity rule
master_state.set_state("payload", "PROCESSING commands",
                       ts=int(time.time()) - 999)
store.set_state("payload", "PROCESSING commands", ts=int(time.time()) - 999)
store.set_health({"success": True, "error_code": 0, "error_detail": "",
                  "component_id": "RADIO_003", "category": "RADIO",
                  "quantity": 1})
store.clear_actions()
r3 = RiskAgent(payload=agent, log_sink=lambda rec: None, use_model=False,
               poll_interval=0.05, stale_after_s=10.0, dedup_window_s=5.0)
check("30: stale activity not corrected on first poll",
      r3.poll_once()["acted"] is False)
out = r3.poll_once()
check("31: stale busy state -> P2 restore",
      out["acted"] is True and len(calls) == 3, "calls=%d" % len(calls))


def ev_parse(data):
    e = pb.RiskToPayload()
    e.ParseFromString(data)
    return e.code


check("32: stale event code P2", ev_parse(calls[-1]) == pb.P2)
check("33: payload state after stale correction",
      master_state.read_state("payload")["state"] == "RECOVERED last valid",
      master_state.read_state("payload"))
check("34: stale not re-fired after correction (dedup)",
      r3.poll_once()["acted"] is False)
r3.stop()

# idle fresh state never stale
master_state.set_state("payload", "IDLE awaiting commands")
r4 = RiskAgent(payload=agent, log_sink=lambda rec: None, use_model=False,
               poll_interval=0.05, stale_after_s=0.05, dedup_window_s=5.0)
outs = [r4.poll_once() for _ in range(3)]
check("35: idle state never triggers stale",
      all(o["acted"] is False for o in outs), str(len(r4.sent)))
r4.stop()

# --------------------------------------------------- thread start / stop
risk_t = RiskAgent(payload=agent, log_sink=lambda rec: None, use_model=False,
                   poll_interval=0.05, stale_after_s=999.0,
                   dedup_window_s=60.0)
t0 = time.time()
little = risk_t.start()
time.sleep(0.4)
polls = risk_t.poll_count
done = risk_t.stop(timeout=2.0)
elapsed = time.time() - t0
check("36: background thread polls autonomously",
      little.is_alive() is False and polls >= 3 and elapsed < 3.0,
      "polls=%d" % polls)
check("37: clean stop resets state",
      master_state.read_state("risk")["state"] == "STOPPED idle" and done)

# ----------------------------------------------------------- model config
check("38: shared Qwen3-1.7B model config for risk assessment",
      os.path.abspath(pintel.MODEL_PATH).endswith("qwen3-1.7b-mlx-4bit"))

risk_gaps = RiskAgent(payload=agent, log_sink=lambda rec: None,
                      use_model=False)
check("39: L1/R1 receiver gap reported, not invented",
      any("L1/R1" in g for g in risk_gaps.gaps) and
      any("L2/R2" in g for g in risk_gaps.gaps))
risk_gaps.stop()

# log sink actually receives JSON-serializable records
sink = []
r5 = RiskAgent(payload=agent, log_sink=lambda rec: sink.append(rec),
               use_model=False, poll_interval=0.05, stale_after_s=999.0,
               dedup_window_s=5.0)
store.set_health({"success": False, "error_code": int(pb.INTERNAL_ERROR),
                  "error_detail": "simulated persistent failure",
                  "component_id": "", "category": "", "quantity": 0})
store.clear_actions()
r5.poll_once()
r5.poll_once()
check("40: log sink captured JSON line",
      len(sink) == 1 and isinstance(sink[0], dict) and
      json.dumps(sink[0]) and sink[0]["code"] == "P2")
r5.stop()

print("\nALL %d CHECKS PASSED" % len(PASS))
