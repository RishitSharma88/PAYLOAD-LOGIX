"""Real Payload Agent: deterministic spoke with local Qwen3-1.7B reasoning.

Division of labor (strict):
  Qwen3-1.7B  = interpretation + selection rationale over SMALL top-K sets
  Python      = filtering, arithmetic, threshold checks (source of truth)
  CatBoost    = candidate ranking (existing .cbm, never retrained)
  SQLite      = blueprint / requirements / constructor state (P1/P2)
  Protobuf    = wire contract (unchanged envelope, error codes, IDs)

Wire API mirrors the mock: handle_command(bytes)->bytes,
handle_risk(bytes)->result. agents/mock_payload_agent.py is left intact
so the original vertical-slice tests keep passing.
"""
import json
import time
import uuid

from proto import payload_logix_pb2 as pb
from payload.db import PayloadDB
from payload import component_store as store
from payload import validate as eng
from payload import ranker
from payload import slm as intelligence

PROTOCOL_VERSION = "1.0"
TOP_K = 5

CATNAME = {pb.RADIO: "RADIO", pb.REACTION_WHEEL: "REACTION_WHEEL",
           pb.PMAD: "PMAD", pb.SATELLITE: "SATELLITE"}


def _now():
    return int(time.time())


class PayloadAgent:
    def __init__(self, db_path=None):
        self.db = PayloadDB(path=db_path) if db_path else PayloadDB()

    # -- wire ------------------------------------------------------------
    def handle_command(self, data):
        cmd = pb.PayloadCommand()
        try:
            cmd.ParseFromString(data)
        except Exception as e:
            return self._resp(None, False, pb.VALIDATION_ERROR,
                              "unparseable PayloadCommand: %s" % e,
                              "", pb.CATEGORY_UNSPECIFIED, 0)
        code, detail = self._validate(cmd)
        if code != pb.ERROR_NONE:
            return self._resp(cmd, False, code, detail, "",
                              cmd.category, cmd.quantity)
        if cmd.category == pb.SATELLITE:
            return self._satellite(cmd)
        if cmd.intent == pb.ADD:
            return self._add(cmd)
        if cmd.intent == pb.REMOVE:
            return self._remove(cmd)
        return self._update(cmd)

    def _validate(self, cmd):
        if cmd.header.sender != pb.SLM:
            return pb.INVALID_SENDER, "sender must be SLM"
        if cmd.header.receiver != pb.PAYLOAD:
            return pb.INVALID_RECEIVER, "receiver must be PAYLOAD"
        if cmd.intent not in (pb.ADD, pb.REMOVE, pb.UPDATE):
            return pb.INVALID_INTENT, "intent must be ADD/REMOVE/UPDATE"
        if cmd.category not in CATNAME:
            return pb.INVALID_CATEGORY, "unknown category"
        if cmd.category == pb.SATELLITE:
            if not cmd.HasField("constraints"):
                return pb.MISSING_FIELD, \
                    "SATELLITE requires constraints thresholds"
            return pb.ERROR_NONE, ""
        if cmd.intent == pb.ADD and cmd.quantity <= 0:
            return pb.MISSING_FIELD, "ADD requires quantity > 0"
        if cmd.intent in (pb.REMOVE, pb.UPDATE) and not cmd.component_id \
                and cmd.quantity <= 0:
            return pb.MISSING_FIELD, \
                "REMOVE/UPDATE requires component_id or quantity"
        for name in ("mass_kg", "power_w", "volume_cm3"):
            if getattr(cmd, name) < 0:
                return pb.VALIDATION_ERROR, "%s must be >= 0" % name
        return pb.ERROR_NONE, ""

    def _resp(self, cmd, success, code, detail, pick, category, quantity):
        rid = cmd.header.request_id if cmd is not None else ""
        resp = pb.PayloadResponse(
            header=pb.Header(protocol_version=PROTOCOL_VERSION,
                             message_id="msg-%s" % uuid.uuid4().hex[:8],
                             request_id=rid, sender=pb.PAYLOAD,
                             receiver=pb.SLM, timestamp_unix_sec=_now()),
            success=success, error_code=code, error_detail=detail or "",
            component_id=pick or "", category=category,
            quantity=quantity)
        return resp.SerializeToString()

    # -- SATELLITE thresholds ---------------------------------------------
    def _satellite(self, cmd):
        c = cmd.constraints
        self.db.set_thresholds(
            mass=c.max_mass_kg if c.HasField("max_mass_kg") else None,
            power=c.max_power_w if c.HasField("max_power_w") else None,
            volume=c.max_volume_cm3 if c.HasField("max_volume_cm3") else None)
        t = self.db.get_thresholds()
        detail = json.dumps({"mass_threshold_kg": t["mass_threshold_kg"],
                             "power_threshold_w": t["power_threshold_w"],
                             "volume_threshold_cm3": t["volume_threshold_cm3"],
                             "version": t["version"]})
        return self._resp(cmd, True, pb.ERROR_NONE, detail, "",
                          pb.SATELLITE, 0)

    @staticmethod
    def _presence_filter(cands, th):
        """Drop candidates missing a thresholded field (missing data can
        never prove fit against a set satellite threshold)."""
        if th["mass_threshold_kg"] is not None:
            cands = [c for c in cands if c["mass_kg"] is not None]
        if th["power_threshold_w"] is not None:
            cands = [c for c in cands if c["power_w"] is not None]
        if th["volume_threshold_cm3"] is not None:
            cands = [c for c in cands
                     if c["volume_cm3"] is not None
                     or c["dimvol_cm3"] is not None]
        return cands

    # -- Blueprint worker: ADD --------------------------------------------
    def _caps(self, cmd):
        return {"max_mass_kg": cmd.mass_kg or None,
                "max_power_w": cmd.power_w or None,
                "max_volume_cm3": cmd.volume_cm3 or None}

    def _add(self, cmd):
        cat = CATNAME[cmd.category]
        caps = self._caps(cmd)
        self.db.set_requirement(cat, quantity=cmd.quantity, **caps)
        # Constructor: retrieve -> deterministic filter -> CatBoost rank.
        cands = store.filter_component_array(cat, **caps)
        if cmd.component_id:
            cands = [c for c in cands
                     if c["component_id"] == cmd.component_id]
        if not cands:
            return self._resp(cmd, False, pb.UNKNOWN_COMPONENT,
                              "no candidate fits constraints", "",
                              cmd.category, cmd.quantity)
        # Satellite gate needs data, not just bounds: drop candidates
        # missing a thresholded field (missing values never satisfy).
        th = self.db.get_thresholds()
        cands = self._presence_filter(cands, th)
        if not cands:
            return self._resp(cmd, False, pb.UNKNOWN_COMPONENT,
                              "no candidate carries the thresholded fields",
                              "", cmd.category, cmd.quantity)
        ranked = ranker.rank_candidates(cat, cands, caps, top_k=TOP_K)
        # Qwen reasons over the SMALL ranked set; Python validates.
        pick_info = intelligence.reason_selection(cat, caps, ranked)
        pick = self._first_valid(cat, ranked, caps,
                                 preferred=pick_info["component_id"])
        if pick is None:
            return self._resp(cmd, False, pb.VALIDATION_ERROR,
                              "ranked candidates fail deterministic "
                              "validation", "", cmd.category, cmd.quantity)
        spec = self._spec(cat, pick["component_id"])
        # Satellite-level gate: blueprint must stay within thresholds.
        trial = self.db.get_components() + [{
            "component_id": pick["component_id"], "category": cat,
            "quantity": cmd.quantity, "manufacturer": spec["manufacturer"],
            "mass_kg": spec["mass_kg"], "power_w": spec["power_w"],
            "volume_cm3": spec["volume_cm3"]}]
        sat = eng.check_satellite(
            trial, mass_threshold_kg=th["mass_threshold_kg"],
            power_threshold_w=th["power_threshold_w"],
            volume_threshold_cm3=th["volume_threshold_cm3"])
        if not sat["satisfied"]:
            return self._resp(cmd, False, pb.VALIDATION_ERROR,
                              "satellite thresholds violated: %s" %
                              "; ".join(sat["violations"]), "",
                              cmd.category, cmd.quantity)
        self.db.upsert_component(pick["component_id"], cat,
                                 quantity=cmd.quantity, **spec)
        self._snapshot(cat, ranked)
        detail = "selected %s: %s" % (pick["component_id"],
                                      pick_info["rationale"])
        return self._resp(cmd, True, pb.ERROR_NONE, detail,
                          pick["component_id"], cmd.category, cmd.quantity)

    @staticmethod
    def _first_valid(cat, ranked, caps, preferred=None):
        order = sorted(ranked,
                       key=lambda c: 0 if c["component_id"] == preferred else 1)
        for c in order:
            if eng.check_component(c, **caps)["satisfied"]:
                return c
        return None

    @staticmethod
    def _spec(cat, cid):
        """Catalog spec in protocol units. volume_cm3 is the EFFECTIVE
        volume (native volume, else dimension-derived) so satellite
        accounting works for categories like RADIO that only carry dims."""
        recs = store.filter_component_array(cat)
        for r in recs:
            if r["component_id"] == cid:
                vol = r["volume_cm3"]
                if vol is None:
                    vol = r["dimvol_cm3"]
                return {"manufacturer": r["manufacturer"],
                        "mass_kg": r["mass_kg"], "power_w": r["power_w"],
                        "volume_cm3": vol}
        raise ValueError("unknown component %s" % cid)

    def _snapshot(self, cat, ranked):
        state = self.db.get_state()
        rankings = state["cached_rankings"]
        rankings[cat] = [c["component_id"] for c in ranked]
        self.db.snapshot_valid(self.db.get_components(), rankings)

    # -- REMOVE / UPDATE ----------------------------------------------------
    def _remove(self, cmd):
        cat = CATNAME[cmd.category]
        if cmd.component_id:
            ok = self.db.remove_component(cmd.component_id)
            if not ok:
                return self._resp(cmd, False, pb.UNKNOWN_COMPONENT,
                                  "nothing to remove", "", cmd.category, 0)
        else:
            doomed = self.db.remove_category(cat, cmd.quantity)
            if not doomed:
                return self._resp(cmd, False, pb.UNKNOWN_COMPONENT,
                                  "nothing to remove", "", cmd.category, 0)
        state = self.db.get_state()
        self.db.snapshot_valid(self.db.get_components(),
                               state["cached_rankings"])
        return self._resp(cmd, True, pb.ERROR_NONE, "removed",
                          cmd.component_id, cmd.category, cmd.quantity)

    def _update(self, cmd):
        cat = CATNAME[cmd.category]
        comps = self.db.get_components(category=cat)
        target = None
        for c in comps:
            if c["component_id"] == cmd.component_id:
                target = c
                break
        if target is None and comps and not cmd.component_id:
            target = comps[0]
        if target is None:
            return self._resp(cmd, False, pb.UNKNOWN_COMPONENT,
                              "nothing to update", "", cmd.category, 0)
        fields = {}
        if cmd.quantity > 0:
            fields["quantity"] = cmd.quantity
        for f in ("mass_kg", "power_w", "volume_cm3"):
            if getattr(cmd, f) > 0:
                fields[f] = getattr(cmd, f)
        self.db.upsert_component(
            target["component_id"], cat,
            quantity=fields.get("quantity", target["quantity"]),
            manufacturer=target["manufacturer"],
            mass_kg=fields.get("mass_kg", target["mass_kg"]),
            power_w=fields.get("power_w", target["power_w"]),
            volume_cm3=fields.get("volume_cm3", target["volume_cm3"]))
        state = self.db.get_state()
        self.db.snapshot_valid(self.db.get_components(),
                               state["cached_rankings"])
        return self._resp(cmd, True, pb.ERROR_NONE, "updated",
                          target["component_id"], cmd.category,
                          fields.get("quantity", target["quantity"]))

    # -- constructor: multi-category configuration --------------------------
    def construct(self, requirements, quantity_default=1):
        """requirements: [{category, max_mass_kg, max_power_w,
        max_volume_cm3, quantity}]. Runs retrieve->filter->rank->reason->
        validate per category, then a final satellite check. Writes to the
        blueprint only if EVERYTHING validates (atomic).
        Returns {'valid': bool, 'configuration': [...], 'violations': [...] }.
        """
        staged, violations, rankings = [], [], {}
        for req in requirements:
            cat = req["category"]
            caps = {k: req.get(k) for k in
                    ("max_mass_kg", "max_power_w", "max_volume_cm3")}
            cands = store.filter_component_array(cat, **{k: v for k, v in
                                                          caps.items()
                                                          if v is not None})
            if not cands:
                violations.append("%s: no candidates" % cat)
                continue
            cands = self._presence_filter(
                cands, self.db.get_thresholds())
            if not cands:
                violations.append(
                    "%s: no candidates carry thresholded fields" % cat)
                continue
            ranked = ranker.rank_candidates(cat, cands, caps, top_k=TOP_K)
            pick = self._first_valid(
                cat, ranked, {k: v for k, v in caps.items() if v is not None},
                preferred=intelligence.reason_selection(
                    cat, caps, ranked)["component_id"])
            if pick is None:
                violations.append("%s: ranked fail validation" % cat)
                continue
            spec = self._spec(cat, pick["component_id"])
            staged.append({"component_id": pick["component_id"],
                           "category": cat,
                           "quantity": req.get("quantity", quantity_default),
                           "manufacturer": spec["manufacturer"],
                           "mass_kg": spec["mass_kg"],
                           "power_w": spec["power_w"],
                           "volume_cm3": spec["volume_cm3"]})
            rankings[cat] = [c["component_id"] for c in ranked]
        if violations:
            return {"valid": False, "configuration": staged,
                    "violations": violations}
        th = self.db.get_thresholds()
        sat = eng.check_satellite(
            staged, mass_threshold_kg=th["mass_threshold_kg"],
            power_threshold_w=th["power_threshold_w"],
            volume_threshold_cm3=th["volume_threshold_cm3"])
        if not sat["satisfied"]:
            return {"valid": False, "configuration": staged,
                    "violations": sat["violations"]}
        for c in staged:
            self.db.set_requirement(c["category"], quantity=c["quantity"])
            self.db.upsert_component(**c)
        self.db.snapshot_valid(self.db.get_components(), rankings)
        return {"valid": True, "configuration": staged, "violations": []}

    # -- risk events (P1/P2 semantics preserved, now SQLite-backed) ---------
    def handle_risk(self, data):
        ev = pb.RiskToPayload()
        ev.ParseFromString(data)
        if ev.header.sender != pb.RISK or ev.header.receiver != pb.PAYLOAD:
            raise ValueError("RiskToPayload must be RISK -> PAYLOAD")
        cat = CATNAME.get(ev.category, "")
        state = self.db.get_state()
        if ev.code == pb.P1:
            ranked = state["cached_rankings"].get(cat, [])
            cur = next((c["component_id"] for c in self.db.get_components()
                        if c["category"] == cat and
                        (not ev.component_id or
                         c["component_id"] == ev.component_id)), None)
            nxt = None
            if cur in ranked:
                i = ranked.index(cur)
                nxt = ranked[i + 1] if i + 1 < len(ranked) else None
            nxt = nxt or (ranked[0] if ranked else None)
            if not nxt:
                raise ValueError("P1: no cached candidates for %s" % cat)
            spec = self._spec(cat, nxt)
            reqs = self.db.get_requirements(category=cat)
            caps = ({k: reqs[0][k] for k in
                     ("max_mass_kg", "max_power_w", "max_volume_cm3")}
                    if reqs else {})
            trial = [c for c in self.db.get_components()
                     if c["component_id"] != cur] + [{
                         "component_id": nxt, "category": cat,
                         "quantity": 1, "manufacturer": spec["manufacturer"],
                         "mass_kg": spec["mass_kg"],
                         "power_w": spec["power_w"],
                         "volume_cm3": spec["volume_cm3"]}]
            if not eng.check_component(spec, **{k: v for k, v in caps.items()
                                                 if v is not None})["satisfied"]:
                raise ValueError("P1: next candidate fails validation")
            th = self.db.get_thresholds()
            if not eng.check_satellite(
                    trial, mass_threshold_kg=th["mass_threshold_kg"],
                    power_threshold_w=th["power_threshold_w"],
                    volume_threshold_cm3=th["volume_threshold_cm3"])["satisfied"]:
                raise ValueError("P1: next candidate breaks thresholds")
            if cur:
                self.db.remove_component(cur)
            self.db.upsert_component(nxt, cat, quantity=1, **spec)
            self.db.snapshot_valid(self.db.get_components(),
                                   state["cached_rankings"])
            return nxt
        if ev.code == pb.P2:
            last = state["last_valid_configuration"]
            self.db.conn.execute("DELETE FROM blueprint_components "
                                 "WHERE blueprint_id=?",
                                 (self.db.blueprint_id,))
            for c in last:
                self.db.upsert_component(**{k: c[k] for k in
                                             ("component_id", "category",
                                              "quantity", "manufacturer",
                                              "mass_kg", "power_w",
                                              "volume_cm3")})
            return True
        raise ValueError("unknown RiskPayloadCode")

    # -- structured tools for the Payload SLM --------------------------------
    def get_blueprint(self):
        return self.db.get_components()

    def get_satellite_thresholds(self):
        return self.db.get_thresholds()

    def get_component_requirements(self, category=None):
        return self.db.get_requirements(category)

    def manufacturers_for(self, category, **caps):
        """Actual manufacturers with at least one candidate fitting caps."""
        recs = store.filter_component_array(category, **caps)
        return sorted({r["manufacturer"] for r in recs if r["manufacturer"]})
