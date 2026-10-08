"""Deterministic threshold engine: the ONLY source of arithmetic truth.

Qwen interprets results; it never performs these calculations.
Component checks mirror the training label semantics: a bound applies
only when set; missing (None) values never satisfy a set bound.
"""
import math


def _ok(value, bound):
    if bound is None:
        return True, None
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False, "missing value cannot satisfy bound %s" % bound
    return (value <= bound,
            None if value <= bound else "%s > %s" % (value, bound))


def check_component(candidate, max_mass_kg=None, max_power_w=None,
                    max_volume_cm3=None):
    """candidate: dict with mass_kg/power_w/volume_cm3. Returns
    {'satisfied': bool, 'violations': [...], 'margins': {...}}."""
    out = {"satisfied": True, "violations": [], "margins": {}}
    for field, bound in (("mass_kg", max_mass_kg),
                         ("power_w", max_power_w),
                         ("volume_cm3", max_volume_cm3)):
        if bound is None:
            continue
        v = candidate.get(field)
        if v is None and field == "volume_cm3":
            v = candidate.get("dimvol_cm3")  # radios carry dims only
        good, why = _ok(v, bound)
        if good and v is not None and bound:
            out["margins"][field] = (bound - v) / bound
        elif good:
            out["margins"][field] = 0.0
        else:
            out["satisfied"] = False
            out["violations"].append("%s: %s" % (field, why))
    return out


def totals(components):
    """Sum mass/power/volume over blueprint entries. quantity-aware.
    Returns (sums dict, missing list). Missing values are skipped in the
    sum AND reported (never silently treated as zero)."""
    sums = {"mass_kg": 0.0, "power_w": 0.0, "volume_cm3": 0.0}
    missing = []
    for c in components:
        q = c.get("quantity") or 1
        for f in sums:
            v = c.get(f)
            if v is None:
                missing.append("%s.%s" % (c.get("component_id"), f))
            else:
                sums[f] += v * q
    return sums, missing


def check_satellite(components, mass_threshold_kg=None,
                    power_threshold_w=None, volume_threshold_cm3=None):
    """Satellite-level validation. Unset thresholds are not checked."""
    sums, missing = totals(components)
    out = {"satisfied": True, "violations": [], "totals": sums,
           "missing": missing}
    bounds = (("mass_kg", mass_threshold_kg),
              ("power_w", power_threshold_w),
              ("volume_cm3", volume_threshold_cm3))
    for field, bound in bounds:
        if bound is None:
            continue
        if sums[field] > bound:
            out["satisfied"] = False
            out["violations"].append(
                "total_%s %.4g > threshold %.4g" % (field, sums[field], bound))
    # Missing values only fail fields that are actually thresholded;
    # unthresholded gaps are reported, not fatal.
    checked = {f for f, b in bounds if b is not None}
    relevant = [m for m in missing
                if m.rsplit(".", 1)[-1] in checked]
    if relevant:
        out["satisfied"] = False
        out["violations"].append("missing values: %s" % ", ".join(relevant))
    return out
