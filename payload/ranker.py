"""CatBoost Payload Ranking Model wrapper.

Uses the EXISTING trained model (payload_logix_data/models/catboost_payload_ranker.cbm).
NEVER retrained here. It ranks candidates; it is not the Constructor and
not an aerospace expert. Features are rebuilt exactly as in training:
query caps + candidate values + relative margins + completeness.
"""
import math
import os

import pandas as pd

from payload.component_store import CATS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE, "payload_logix_data", "models",
                           "catboost_payload_ranker.cbm")

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from catboost import CatBoostRanker
        _MODEL = CatBoostRanker()
        _MODEL.load_model(MODEL_PATH)
    return _MODEL


def _margin(query_val, cand_val):
    if query_val is None or cand_val is None or query_val == 0:
        return float("nan")
    if isinstance(cand_val, float) and math.isnan(cand_val):
        return float("nan")
    return (query_val - cand_val) / query_val


# Training query convention per category (mirrors build_ranking_dataset.py):
#   RADIO -> mass + dimvol caps (power excluded: dBm contamination)
#   REACTION_WHEEL -> mass + power caps
#   PMAD -> mass + power + volume caps
QUERY_CAPS = {
    "RADIO": ("max_mass_kg", None, None, "max_volume_cm3"),
    "REACTION_WHEEL": ("max_mass_kg", "max_power_w", None, None),
    "PMAD": ("max_mass_kg", "max_power_w", "max_volume_cm3", None),
}


def rank_candidates(category, candidates, requirements, top_k=5):
    """requirements: dict with max_mass_kg/max_power_w/max_volume_cm3 (+query_category).
    Returns candidates ordered best-first, each with _score. Empty in -> []."""
    if not candidates:
        return []
    m = _model()
    names = list(m.feature_names_)
    soa_cat = CATS[category][0]  # categoricals use SOA names in training
    qmass, qpower, qvol, qdim = QUERY_CAPS[category]
    qv = {k: requirements.get(k) for k in
          ("max_mass_kg", "max_power_w", "max_volume_cm3")}
    rows = []
    for c in candidates:
        cm = _margin(qv["max_mass_kg"], c.get("mass_kg"))
        cp = _margin(qv["max_power_w"], c.get("power_w"))
        cv = _margin(qv["max_volume_cm3"], c.get("volume_cm3"))
        cd = _margin(qv["max_volume_cm3"], c.get("dimvol_cm3"))
        # completeness: applicable caps with data (training semantics)
        applic = [qmass and qv["max_mass_kg"] is not None,
                  qpower and qv["max_power_w"] is not None,
                  qvol and qv["max_volume_cm3"] is not None,
                  qdim and qv["max_volume_cm3"] is not None]
        avail = [qmass and not _isnan(c.get("mass_kg")),
                 qpower and not _isnan(c.get("power_w")),
                 qvol and not _isnan(c.get("volume_cm3")),
                 qdim and not _isnan(c.get("dimvol_cm3"))]
        n_app = sum(1 for a in applic if a)
        completeness = (sum(1 for a, v in zip(applic, avail) if a and v) / n_app
                        if n_app else 0.0)
        rows.append({
            "q_mass_max": qv["max_mass_kg"] if qmass else float("nan"),
            "q_power_max": qv["max_power_w"] if qpower else float("nan"),
            "q_volume_max": qv["max_volume_cm3"] if qvol else float("nan"),
            "q_dimvol_max": qv["max_volume_cm3"] if qdim else float("nan"),
            "cand_mass": c.get("mass_kg"),
            "cand_power": c.get("power_w"),
            "cand_volume": c.get("volume_cm3"),
            "cand_dimvol": c.get("dimvol_cm3"),
            "margin_mass_kg": cm, "margin_power_w": cp,
            "margin_volume_cm3": cv, "margin_dimension_volume_cm3": cd,
            "category_match": 1, "completeness": completeness,
            "cand_synthetic": 0, "cand_category": soa_cat,
            "query_category": requirements.get("query_category", soa_cat),
        })
    X = pd.DataFrame(rows, columns=names)
    scores = m.predict(X)
    ranked = [dict(c, _score=float(s))
              for c, s in sorted(zip(candidates, scores),
                                 key=lambda t: -t[1])]
    return ranked[:top_k]


def _isnan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))
