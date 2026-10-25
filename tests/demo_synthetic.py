"""Demo: synthetic CSV -> array -> filter -> SLM selection.

Run: venv/bin/python tests/demo_synthetic.py
Shows the full chain with debug detail (console stays concise).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payload import component_store as store
from payload import slm as pintel

print("== 1. CSV ==")
print(open("tests/data/test_radios.csv").read().strip())

print("\n== 2. /convert -> cached array ==")
s = store.convert_csv("tests/data/test_radios.csv")
print("rows=%d categories=%s manufacturers=%s cached=%s" % (
    s["rows"], s["categories"], s["manufacturers"], s["cached"]))
d = store.get_loaded_dataset(s["dataset"])
print("mass_kg array:", d["mass_kg"])
print("power_w array:", d["power_w"])
print("volume_cm3 array (x*y*z):", d["volume_cm3"])

print("\n== 3. deterministic filtering "
      "(mass<0.4, power<2, vol<100) ==")
cands = store.filter_loaded_components(
    s["dataset"], max_mass_kg=0.4, max_power_w=2, max_volume_cm3=100)
for c in cands:
    print(" - %s | %s | mass=%s power=%s vol=%s" % (
        c["component_id"], c["manufacturer"], c["mass_kg"],
        c["power_w"], c["volume_cm3"]))
if not cands:
    print(" - (none)")

print("\n== 4. SLM selection (candidates only, no CSV in prompt) ==")
res = pintel.select_from_dataset(
    s["dataset"], {"max_mass_kg": 0.4, "max_power_w": 2,
                   "max_volume_cm3": 100})
print("SLM> Selected %s (%s)." % (res["manufacturer"],
                                  res["component_id"]))
print("debug:", res)
