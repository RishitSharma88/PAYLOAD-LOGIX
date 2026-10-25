"""Tests for the REAL Payload Agent (SQLite + arrays + CatBoost + Qwen3).

Run: venv/bin/python tests/test_payload_agent.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto import payload_logix_pb2 as pb
from orchestrator import protocol
from payload import component_store as store
from payload import validate as eng
from payload import ranker
from payload.db import PayloadDB
from payload import slm as pintel
from agents.payload_agent import PayloadAgent

TMPDB = "/tmp/payload_test.db"
PASS = []


def check(name, cond, extra=""):
    assert cond, "FAIL: %s %s" % (name, extra)
    PASS.append(name)
    print("PASS: %s %s" % (name, extra))


def fresh_db():
    if os.path.exists(TMPDB):
        os.remove(TMPDB)
    return PayloadDB(path=TMPDB)


# 1-2. conversion + caching
a = store.load_component_array("RADIO")
check("1: numpy arrays", isinstance(a["mass_kg"], np.ndarray)
      and len(a["ids"]) == 117)
n0 = store.parse_count()
store.load_component_array("PMAD"); store.load_component_array("RADIO")
check("2: csv cached (no reparse)", store.parse_count() == n0, n0)

# 3-4. category + manufacturer filtering
r = store.filter_component_array("REACTION_WHEEL")
check("3: category filter", len(r) == 66
      and all(x["category"] == "REACTION_WHEEL" for x in r))
mfrs = store.get_manufacturers("RADIO")
sub = store.filter_component_array("RADIO", manufacturer=mfrs[0])
check("4: manufacturer filter", len(sub) > 0 and all(
    x["manufacturer"] == mfrs[0] for x in sub), mfrs[0])

# 5. deterministic filtering (NaN never passes)
f = store.filter_component_array("RADIO", max_mass_kg=0.5, max_power_w=3)
check("5: bounds hold",
      all(x["mass_kg"] <= 0.5 and x["power_w"] <= 3 for x in f)
      and len(f) > 0, len(f))

# 6-7. sqlite thresholds + requirements
db = fresh_db()
db.set_thresholds(mass=25, power=100, volume=50000)
t = db.get_thresholds()
check("6: thresholds stored",
      (t["mass_threshold_kg"], t["power_threshold_w"],
       t["volume_threshold_cm3"]) == (25, 100, 50000))
db.set_requirement("RADIO", quantity=1, max_mass_kg=0.5, max_power_w=3)
rq = db.get_requirements(category="RADIO")[0]
check("7: requirements stored",
      rq["max_mass_kg"] == 0.5 and rq["max_power_w"] == 3)

# 8-9. catboost ranking + top-K to Qwen
top = ranker.rank_candidates("RADIO", f,
                             {"max_mass_kg": 0.5, "max_power_w": 3}, top_k=3)
check("8: catboost ranks top-K",
      len(top) == 3
      and top[0]["_score"] >= top[1]["_score"] >= top[2]["_score"])
sel = pintel.reason_selection("RADIO", {"max_mass_kg": 0.5}, top)
check("9: qwen picks from top-K (no fabrication)",
      sel["component_id"] in {c["component_id"] for c in top},
      json.dumps(sel)[:120])

# 10-11. valid/invalid configurations (python decides, qwen explains)
good = eng.check_component(top[0], max_mass_kg=0.5, max_power_w=3)
check("10: valid config", good["satisfied"])
bad = eng.check_component({"mass_kg": 5.0, "power_w": 1.0}, max_mass_kg=0.5)
check("11: invalid config flagged",
      not bad["satisfied"] and bad["violations"])
expl = pintel.explain_validation(bad, "radio candidate")
check("11b: qwen explains (text only)", isinstance(expl, str) and len(expl) > 0)

# 12-13. P1/P2 on the real agent
agent = PayloadAgent(db_path=TMPDB)
agent.db.reset()
cmd = protocol.command_from_dict(
    {"receiver": "PAYLOAD", "intent": "ADD", "category": "RADIO",
     "quantity": 1, "mass_kg": 0.5, "power_w": 3.0})
raw = agent.handle_command(cmd.SerializeToString())
resp = pb.PayloadResponse()
resp.ParseFromString(raw)
check("12a: real ADD success", resp.success, resp.error_detail[:100])
first = resp.component_id
state = agent.db.get_state()
assert len(state["cached_rankings"]["RADIO"]) > 1
ev = pb.RiskToPayload(header=protocol.new_header(pb.RISK, pb.PAYLOAD),
                      code=pb.P1, category=pb.RADIO, component_id=first,
                      detail="deadline invalid")
nxt = agent.handle_risk(ev.SerializeToString())
check("12b: P1 next-best cached", nxt != first, "%s->%s" % (first, nxt))
agent.db.conn.execute("DELETE FROM blueprint_components")
agent.db.conn.commit()
ev2 = pb.RiskToPayload(header=protocol.new_header(pb.RISK, pb.PAYLOAD),
                       code=pb.P2, detail="packet mismatch")
agent.handle_risk(ev2.SerializeToString())
check("13: P2 sqlite restore",
      any(c["component_id"] == nxt for c in agent.db.get_components()))

# 14. manufacturers are dataset-real
got = agent.manufacturers_for("RADIO", max_mass_kg=0.5, max_power_w=3)
check("14: manufacturers real (subset, non-empty)",
      len(got) > 0 and set(got) <= set(mfrs), str(got[:4]))

# 15. full e2e through the 7B orchestrator + real agent
from orchestrator.slm import Orchestrator
agent.db.reset()
o = Orchestrator(payload_agent=agent)
t1 = o.run("Keep the satellite below 25 kg, 100 W and 50000 cm3.")
check("15a: satellite thresholds via NL",
      t1["command_dict"].get("category") == "SATELLITE"
      and t1["response_dict"]["success"] is True,
      json.dumps(t1["command_dict"])[:150])
t2 = o.run("Add a radio with mass below 0.5 kg and power below 3 W.")
check("15b: radio ADD e2e",
      t2["response_dict"]["success"] is True
      and any(c["category"] == "RADIO" for c in agent.db.get_components()),
      t2["response_dict"]["component_id"])
bp = agent.db.get_components()
sat = eng.check_satellite(
    bp, mass_threshold_kg=25, power_threshold_w=100,
    volume_threshold_cm3=50000)
check("15c: blueprint within thresholds", sat["satisfied"],
      json.dumps(sat["totals"]))
print("FINAL NL:", t2["final"][:200])

# 16. constructor: multi-category configuration within limits
# (RADIO+PMAD: both carry volume data; wheels carry none, so a set
# volume threshold strictly excludes them -- documented limitation.)
agent.db.reset()
agent.db.set_thresholds(mass=25, power=100, volume=50000)
cfg = agent.construct([
    {"category": "RADIO", "max_mass_kg": 0.5, "max_power_w": 3},
    {"category": "PMAD", "max_mass_kg": 2.0, "max_power_w": 500,
     "max_volume_cm3": 2000}])
check("16: construct valid config", cfg["valid"] and len(cfg["configuration"]) == 2,
      json.dumps([c["component_id"] for c in cfg["configuration"]]))
check("16b: construct persisted",
      len(agent.db.get_components()) == 2)

print("\nALL %d CHECKS PASSED" % len(PASS))
