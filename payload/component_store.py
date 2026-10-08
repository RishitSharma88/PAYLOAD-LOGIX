"""CSV -> NumPy array tool for the Payload SLM.

The SLM must NEVER parse CSV text itself. It calls:
  load_component_array(category, manufacturer=None)
  filter_component_array(category, max_mass_kg=None, ...)
  get_manufacturers(category)
  get_components(category, manufacturer=None)

Arrays are built ONCE from components_master_clean.csv and cached in
memory (see _PARSE_COUNT / parse_count()). Numeric columns are NumPy
arrays; every row keeps its deterministic component_id + provenance so
results trace back to the NASA-derived source. Mass is normalized to kg
on load (gram-scale radio values / 1000); power in W; volumes in cm3.
Source CSV is never modified.
"""
import csv
import os

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(BASE, "payload_logix_data", "processed",
                       "components_master_clean.csv")

# Protocol category -> SOA category + id prefix (same scheme as CAG layer).
CATS = {"RADIO": ("Radios", "RADIO"),
        "REACTION_WHEEL": ("High Heritage Miniature Reaction Wheels", "HHMRW"),
        "PMAD": ("Power Management And Distribution System Products", "PMAD")}

_PARSE_COUNT = 0
_STORE = None

# Mounted experimental datasets: name -> array-dict (same shape as
# ComponentStore.data entries). NASA master data is never mixed in here.
DATASETS = {}


def _build_arrays(ids, names, mfrs, mass, power, vol, dimvol,
                  soa_category, source):
    return {
        "ids": list(ids), "names": list(names),
        "manufacturers": [m.strip() for m in mfrs],
        "mass_kg": np.asarray(mass, dtype=float),
        "power_w": np.asarray(power, dtype=float),
        "volume_cm3": np.asarray(vol, dtype=float),
        "dimvol_cm3": np.asarray(dimvol, dtype=float),
        "soa_category": soa_category, "source": source,
    }


def _fnum(v):
    v = (v or "").strip()
    if v in ("", "nan", "None"):
        return np.nan
    try:
        return float(v)
    except ValueError:
        return np.nan


class ComponentStore:
    def __init__(self):
        global _PARSE_COUNT
        _PARSE_COUNT += 1
        self.data = {}
        by_cat = {}
        with open(MASTER) as f:
            for row in csv.DictReader(f):
                by_cat.setdefault(row["category"], []).append(row)
        for proto_cat, (soa_cat, prefix) in CATS.items():
            rows = sorted(by_cat.get(soa_cat, []),
                          key=lambda r: (r.get("component_name") or ""))
            ids, names, mfrs, mass, power, vol, dimvol = (
                [], [], [], [], [], [], [])
            for i, r in enumerate(rows):
                ids.append("%s_%03d" % (prefix, i + 1))
                names.append(r.get("component_name") or "")
                mfrs.append((r.get("manufacturer") or "").strip())
                m = _fnum(r.get("mass_kg"))
                if proto_cat == "RADIO" and not np.isnan(m):
                    m = m / 1000.0  # gram-scale pipeline quirk -> kg
                mass.append(m)
                power.append(_fnum(r.get("power_w")))
                vol.append(_fnum(r.get("volume_cm3")))
                dimvol.append(_fnum(r.get("dimension_volume_cm3")))
            self.data[proto_cat] = _build_arrays(
                ids, names, mfrs, mass, power, vol, dimvol,
                soa_cat, MASTER)

    def categories(self):
        return list(self.data.keys())


def get_store():
    global _STORE
    if _STORE is None:
        _STORE = ComponentStore()
    return _STORE


def parse_count():
    return _PARSE_COUNT


NUMERIC_KEYS = ("mass_kg", "power_w", "volume_cm3", "dimvol_cm3")
LIST_KEYS = ("ids", "names", "manufacturers")


def _subset(d, keep):
    out = {}
    for k, v in d.items():
        if k in LIST_KEYS:
            out[k] = [v[i] for i in keep]
        elif k in NUMERIC_KEYS:
            out[k] = v[keep]
        else:
            out[k] = v
    return out


def load_component_array(category, manufacturer=None):
    """Return cached arrays, optionally restricted to a manufacturer."""
    d = get_store().data[category]
    if manufacturer:
        keep = [i for i, m in enumerate(d["manufacturers"])
                if m.lower() == manufacturer.lower()]
        return _subset(d, keep)
    return d


def filter_component_array(category, max_mass_kg=None, max_power_w=None,
                           max_volume_cm3=None, manufacturer=None):
    """Deterministic constraint filter. NaN never satisfies (missing data
    cannot pass a bound). Returns list of record dicts with provenance."""
    d = load_component_array(category, manufacturer)
    n = len(d["ids"])
    mask = np.ones(n, dtype=bool)
    if max_mass_kg is not None:
        mask &= ~np.isnan(d["mass_kg"]) & (d["mass_kg"] <= max_mass_kg)
    if max_power_w is not None:
        mask &= (~np.isnan(d["power_w"]) & (d["power_w"] >= 0) &
                 (d["power_w"] <= max_power_w))
    if max_volume_cm3 is not None:
        # A bound is satisfied by either the native volume or the
        # dimension-derived volume (radios only carry the latter).
        vok = ~np.isnan(d["volume_cm3"]) & (d["volume_cm3"] <= max_volume_cm3)
        dok = ~np.isnan(d["dimvol_cm3"]) & (d["dimvol_cm3"] <= max_volume_cm3)
        mask &= (vok | dok)
    recs = []
    for i in np.nonzero(mask)[0]:
        recs.append({"component_id": d["ids"][i], "name": d["names"][i],
                     "manufacturer": d["manufacturers"][i],
                     "mass_kg": None if np.isnan(d["mass_kg"][i])
                     else float(d["mass_kg"][i]),
                     "power_w": None if np.isnan(d["power_w"][i])
                     else float(d["power_w"][i]),
                     "volume_cm3": None if np.isnan(d["volume_cm3"][i])
                     else float(d["volume_cm3"][i]),
                     "dimvol_cm3": None if np.isnan(d["dimvol_cm3"][i])
                     else float(d["dimvol_cm3"][i]),
                     "category": category,
                     "provenance": {"source_csv": d["source"],
                                    "soa_category": d["soa_category"]}})
    return recs


def get_manufacturers(category):
    d = get_store().data[category]
    return sorted({m for m in d["manufacturers"] if m})


def get_components(category, manufacturer=None):
    return filter_component_array(category, manufacturer=manufacturer)


def get_manufacturers(category):
    d = get_store().data[category]
    return sorted({m for m in d["manufacturers"] if m})


def get_components(category, manufacturer=None):
    return filter_component_array(category, manufacturer=manufacturer)


# ---------------------------------------------------------------------------
# Mounted experimental datasets (e.g. tests/data/test_radios.csv).
# Same array-dict shape as NASA entries; parsed ONCE then cached.
# Expected columns: component_id, category, manufacturer, mass_kg,
# power_w, dimension_x_cm, dimension_y_cm, dimension_z_cm.
# volume_cm3 is derived deterministically as x*y*z (no SLM math).
# ---------------------------------------------------------------------------
def convert_csv(path, name=None):
    """Parse + cache a synthetic CSV. Returns a concise summary dict."""
    global _PARSE_COUNT
    name = name or os.path.basename(path)
    if name in DATASETS:
        d = DATASETS[name]
        return _dataset_summary(path, name, d, cached=True)
    _PARSE_COUNT += 1
    ids, names, mfrs, mass, power, vol, dimvol = (
        [], [], [], [], [], [], [])
    cats = set()
    with open(path) as f:
        for row in csv.DictReader(f):
            ids.append(row["component_id"])
            names.append(row["component_id"])
            mfrs.append((row.get("manufacturer") or "").strip())
            cats.add((row.get("category") or "").strip())
            mass.append(_fnum(row.get("mass_kg")))
            power.append(_fnum(row.get("power_w")))
            x = _fnum(row.get("dimension_x_cm"))
            y = _fnum(row.get("dimension_y_cm"))
            z = _fnum(row.get("dimension_z_cm"))
            v = x * y * z if not any(np.isnan([x, y, z])) else np.nan
            vol.append(v)
            dimvol.append(v)
    DATASETS[name] = _build_arrays(ids, names, mfrs, mass, power, vol,
                                   dimvol, sorted(cats), os.path.abspath(path))
    return _dataset_summary(path, name, DATASETS[name], cached=True)


def _dataset_summary(path, name, d, cached):
    return {"file": path, "dataset": name, "rows": len(d["ids"]),
            "categories": sorted({d["soa_category"]} if isinstance(
                d["soa_category"], str) else set(d["soa_category"])),
            "manufacturers": sorted({m for m in d["manufacturers"] if m}),
            "cached": cached}


def get_loaded_dataset(name):
    return DATASETS[name]


def loaded_names():
    return list(DATASETS)


def filter_loaded_components(name, category=None, manufacturer=None,
                             max_mass_kg=None, max_power_w=None,
                             max_volume_cm3=None):
    """Deterministic filter over a mounted dataset. Same NaN semantics
    as filter_component_array. Returns record dicts with provenance."""
    d = DATASETS[name]
    n = len(d["ids"])
    mask = np.ones(n, dtype=bool)
    if max_mass_kg is not None:
        mask &= ~np.isnan(d["mass_kg"]) & (d["mass_kg"] <= max_mass_kg)
    if max_power_w is not None:
        mask &= (~np.isnan(d["power_w"]) & (d["power_w"] >= 0) &
                 (d["power_w"] <= max_power_w))
    if max_volume_cm3 is not None:
        vok = ~np.isnan(d["volume_cm3"]) & (d["volume_cm3"] <= max_volume_cm3)
        dok = ~np.isnan(d["dimvol_cm3"]) & (d["dimvol_cm3"] <= max_volume_cm3)
        mask &= (vok | dok)
    recs = []
    for i in np.nonzero(mask)[0]:
        rec = {"component_id": d["ids"][i], "name": d["names"][i],
               "manufacturer": d["manufacturers"][i],
               "mass_kg": None if np.isnan(d["mass_kg"][i])
               else float(d["mass_kg"][i]),
               "power_w": None if np.isnan(d["power_w"][i])
               else float(d["power_w"][i]),
               "volume_cm3": None if np.isnan(d["volume_cm3"][i])
               else float(d["volume_cm3"][i]),
               "dimvol_cm3": None if np.isnan(d["dimvol_cm3"][i])
               else float(d["dimvol_cm3"][i]),
               "provenance": {"source_csv": d["source"]}}
        if category and d["soa_category"] != category \
                and category not in (d["soa_category"] if isinstance(
                    d["soa_category"], list) else [d["soa_category"]]):
            continue
        recs.append(rec)
    if manufacturer:
        recs = [r for r in recs
                if r["manufacturer"].lower() == manufacturer.lower()]
    return recs


def loaded_manufacturers(name):
    d = DATASETS[name]
    return sorted({m for m in d["manufacturers"] if m})
