"""Synthetic CSV -> array -> SLM selection pipeline tests.

Run: venv/bin/python tests/test_synthetic_pipeline.py
Covers: /convert loading, caching, manufacturers, per-axis filtering,
combined query, no-fabrication, SLM-from-list-only, empty case.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payload import component_store as store
from payload import slm as pintel

CSV = "tests/data/test_radios.csv"
PASS = []


def json_s(s):
    import json
    return json.dumps({k: s[k] for k in
                       ("rows", "categories", "manufacturers")})


def check(name, cond, extra=""):
    assert cond, "FAIL: %s %s" % (name, extra)
    PASS.append(name)
    print("PASS: %s %s" % (name, extra))


# 1. /convert loads
s = store.convert_csv(CSV)
check("1: convert loads", s["rows"] == 6 and s["categories"] == ["RADIO"]
      and len(s["manufacturers"]) == 3, json_s(s))

# 2. parsed once, then cached
n0 = store.parse_count()
store.convert_csv(CSV)
check("2: cached, no reparse", store.parse_count() == n0)
d = store.get_loaded_dataset(s["dataset"])
check("2b: numpy arrays", isinstance(d["mass_kg"], np.ndarray))

# 3. exactly 3 manufacturers
check("3: manufacturers", store.loaded_manufacturers(s["dataset"]) == [
    "Manufacturer A", "Manufacturer B", "Manufacturer C"])

# 4-6. per-axis filtering
by_mass = store.filter_loaded_components(s["dataset"], max_mass_kg=0.4)
check("4: mass filter", {r["component_id"] for r in by_mass} == {
    "RADIO_A2", "RADIO_B1", "RADIO_B2", "RADIO_C1", "RADIO_C2"})
by_power = store.filter_loaded_components(s["dataset"], max_power_w=2)
check("5: power filter", {r["component_id"] for r in by_power} == {
    "RADIO_A1", "RADIO_B1", "RADIO_B2", "RADIO_C2"})
by_vol = store.filter_loaded_components(s["dataset"], max_volume_cm3=100)
check("6: volume filter (dims x*y*z)", {r["component_id"] for r in by_vol} == {
    "RADIO_A1", "RADIO_A2", "RADIO_C1", "RADIO_C2"})

# 7. combined -> only C2
hit = store.filter_loaded_components(
    s["dataset"], max_mass_kg=0.4, max_power_w=2, max_volume_cm3=100)
check("7: combined gives RADIO_C2",
      [(r["component_id"], r["manufacturer"]) for r in hit] == [
          ("RADIO_C2", "Manufacturer C")])

# 8. manufacturer is CSV data
check("8: from CSV, not fabricated",
      hit[0]["manufacturer"] == "Manufacturer C"
      and hit[0]["provenance"]["source_csv"].endswith("test_radios.csv"))

# 9. SLM selects only from the tool list
res = pintel.select_from_dataset(
    s["dataset"], {"max_mass_kg": 0.4, "max_power_w": 2,
                   "max_volume_cm3": 100})
check("9: SLM selects Manufacturer C (RADIO_C2)",
      res["component_id"] == "RADIO_C2"
      and res["manufacturer"] == "Manufacturer C", str(res))

# 9b. multi-candidate: SLM reasons over the tool list, stays in-list
res_multi = pintel.select_from_dataset(
    s["dataset"], {"max_mass_kg": 0.6, "max_power_w": 3,
                   "max_volume_cm3": 200})
cands_multi = store.filter_loaded_components(
    s["dataset"], max_mass_kg=0.6, max_power_w=3, max_volume_cm3=200)
check("9b: SLM pick within tool list",
      res_multi["component_id"] in {c["component_id"] for c in cands_multi}
      and len(cands_multi) > 1,
      "%s from %d" % (res_multi["component_id"], len(cands_multi)))
res0 = pintel.select_from_dataset(s["dataset"], {"max_mass_kg": 0.05})
check("10: no-valid-candidate",
      res0["component_id"] is None and res0["candidates_considered"] == 0)

print("\nALL %d CHECKS PASSED" % len(PASS))
