"""Payload intelligence: local Qwen3-1.7B reasoning layer (weights frozen).

Qwen reasons over SMALL candidate sets returned by deterministic tools.
It never scans CSVs, never performs final arithmetic, never invents
components or manufacturers. All numbers it sees come from Python tools.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE, "models", "qwen3-1.7b-mlx-4bit")

# Payload SLM workflow contract for converted-dataset selection.
# The SLM never sees raw CSV text and never does authoritative math.
WORKFLOW_PROMPT = (
    "You have access to a converted engineering component dataset "
    "through deterministic tools. Do not invent components or "
    "manufacturers. When asked to select a component: "
    "1. Interpret the user's constraints. "
    "2. Use the available component filtering tool. "
    "3. Consider only candidates returned by the tool. "
    "4. Never invent a candidate. "
    "5. Select a candidate that satisfies all requested constraints. "
    "6. Return the selected component ID and manufacturer. "
    "7. If multiple candidates satisfy the constraints, prefer the "
    "first-ranked one. "
    "8. If no candidate satisfies the constraints, explicitly report "
    "that no valid candidate exists."
)

_model = None
_tokenizer = None


def _load():
    global _model, _tokenizer
    if _model is None:
        from mlx_lm import load
        _model, _tokenizer = load(MODEL_PATH)
    return _model, _tokenizer


def _gen(system, user, max_tokens=256, thinking=False):
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler
    model, tok = _load()
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    prompt = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                     enable_thinking=thinking)
    return generate(model, tok, prompt=prompt, max_tokens=max_tokens,
                    sampler=make_sampler(temp=0.1), verbose=False)


def _extract_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON in payload-SLM output: %r" % text[:200])
    return json.loads(text[i:j + 1])


def reason_selection(category, requirements, candidates):
    """Pick one candidate from a SMALL pre-ranked list. Returns
    {'component_id': ..., 'rationale': ...}. Falls back to rank #1
    if the model output is unusable (deterministic safety net)."""
    if not candidates:
        raise ValueError("no candidates to reason over")
    if len(candidates) == 1:
        c = candidates[0]
        return {"component_id": c["component_id"],
                "rationale": "only candidate satisfying the constraints"}
    lines = []
    for c in candidates:
        lines.append("%s | %s (%s) | mass=%s kg power=%s W volume=%s cm3 "
                     "| score=%.3f" % (
                         c["component_id"], c["name"], c["manufacturer"],
                         c["mass_kg"], c["power_w"], c["volume_cm3"],
                         c.get("_score", 0.0)))
    out = _gen(
        "You are the PAYLOAD-LOGIX Payload intelligence. Choose exactly "
        "one component id from the ranked candidate list. The list is "
        "already filtered and ranked; prefer the first unless a stated "
        "requirement favors another. Output ONLY JSON: "
        '{"component_id":"ID","rationale":"one sentence"}.',
        "Category %s, requirements %s.\nCandidates:\n%s" %
        (category, json.dumps(requirements), "\n".join(lines)),
        max_tokens=512)
    try:
        d = _extract_json(out)
        valid = {c["component_id"] for c in candidates}
        pick = d.get("component_id")
        if pick not in valid:
            # Tolerate key variants; the id must still be from the list.
            for v in d.values():
                if v in valid:
                    pick = v
                    break
        if pick not in valid:
            raise ValueError("unknown id")
        return {"component_id": pick,
                "rationale": str(d.get("rationale", ""))[:300]}
    except ValueError:
        return {"component_id": candidates[0]["component_id"],
                "rationale": "model output unusable; kept rank-1 candidate"}

def explain_validation(check, subject):
    """Turn a deterministic validation dict into one explanatory paragraph."""
    if check.get("satisfied"):
        return "%s is VALID: all checked bounds hold (margins=%s)." % (
            subject, json.dumps(check.get("margins", {})))
    out = _gen(
        "You are the PAYLOAD-LOGIX Payload intelligence. Explain in one "
        "paragraph why the configuration is INVALID, using ONLY the "
        "violations listed. Do not add new facts or numbers.",
        "Subject %s. Validation result: %s" % (subject, json.dumps(check)),
        max_tokens=512)
    return out.strip()


def select_from_dataset(dataset, requirements, category=None):
    """Full synthetic-dataset flow: deterministic filter over the mounted
    array, then Qwen reasons over the SMALL survivor list (WORKFLOW_PROMPT).
    requirements: {max_mass_kg, max_power_w, max_volume_cm3, manufacturer?}.
    Returns {'component_id', 'manufacturer', 'candidates_considered'} or
    {'component_id': None, ...} when nothing survives. The CSV is never
    placed in the prompt -- only the filtered candidates."""
    from payload import component_store as store
    cands = store.filter_loaded_components(
        dataset, category=category,
        manufacturer=requirements.get("manufacturer"),
        max_mass_kg=requirements.get("max_mass_kg"),
        max_power_w=requirements.get("max_power_w"),
        max_volume_cm3=requirements.get("max_volume_cm3"))
    if not cands:
        return {"component_id": None, "manufacturer": None,
                "candidates_considered": 0,
                "note": "no valid candidate exists"}
    if len(cands) == 1:
        c = cands[0]
        return {"component_id": c["component_id"],
                "manufacturer": c["manufacturer"],
                "candidates_considered": 1,
                "note": "single survivor selected deterministically"}
    lines = ["%s | %s | mass=%s kg power=%s W volume=%s cm3" % (
        c["component_id"], c["manufacturer"], c["mass_kg"],
        c["power_w"], c["volume_cm3"]) for c in cands]
    out = _gen(WORKFLOW_PROMPT + " Output ONLY JSON: "
               '{"component_id":"ID","manufacturer":"M"}.',
               "Requirements %s.\nTool-returned candidates:\n%s" %
               (json.dumps(requirements), "\n".join(lines)),
               max_tokens=512)
    try:
        d = _extract_json(out)
        valid = {c["component_id"]: c["manufacturer"] for c in cands}
        pick = d.get("component_id")
        if pick not in valid:
            for v in d.values():
                if v in valid:
                    pick = v
                    break
        if pick not in valid:
            raise ValueError("unknown id")
        return {"component_id": pick, "manufacturer": valid[pick],
                "candidates_considered": len(cands),
                "note": "slm selection from tool candidates"}
    except ValueError:
        return {"component_id": cands[0]["component_id"],
                "manufacturer": cands[0]["manufacturer"],
                "candidates_considered": len(cands),
                "note": "model output unusable; kept first candidate"}
