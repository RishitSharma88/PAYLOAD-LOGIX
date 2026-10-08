"""Mock Payload Agent: deterministic spoke, NO LLM calls.

Receives protobuf PayloadCommand bytes, validates, updates the mock
blueprint + local cache, returns protobuf PayloadResponse bytes.

Handles Risk->Payload events:
  P1: selected component invalid -> fall back to next-best cached candidate.
  P2: internal failure/packet mismatch -> restore last valid state.

State persists as plain JSON files (no Redis/Kafka in this stage):
  agents/state/blueprint.json  (current payload configuration)
  agents/state/cache.json      (last valid state + ranked candidate lists)

Unit rule: the protocol carries STANDARD units (kg, W, cm3). The mock
catalog is built from the NASA extracts with the known pipeline quirk
normalized on entry (gram-scale radio masses / 1000 -> kg).
"""
import json
import os
import time
import uuid

from proto import payload_logix_pb2 as pb
from cag.retriever import NasaRetriever

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
PROTOCOL_VERSION = "1.0"

CATNAME = {pb.RADIO: "RADIO", pb.REACTION_WHEEL: "REACTION_WHEEL",
           pb.PMAD: "PMAD"}


def _now():
    return int(time.time())


class MockPayloadAgent:
    def __init__(self, state_dir=STATE_DIR):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.blueprint_path = os.path.join(state_dir, "blueprint.json")
        self.cache_path = os.path.join(state_dir, "cache.json")
        self.catalog = self._build_catalog()
        self.blueprint = self._load(self.blueprint_path,
                                    {"components": []})
        self.cache = self._load(self.cache_path,
                                {"last_valid": {"components": []},
                                 "ranked": {}, "selected": {}})

    # -- catalog ---------------------------------------------------------
    @staticmethod
    def _build_catalog():
        """Deterministic mock stock from NASA extracts, normalized to kg/W/cm3."""
        retr = NasaRetriever()
        cat = {}
        import csv
        master = os.path.join(os.path.dirname(STATE_DIR), "..",
                              "payload_logix_data", "processed",
                              "components_master_clean.csv")
        rows = {}
        with open(os.path.normpath(master)) as f:
            for row in csv.DictReader(f):
                rows.setdefault(row["category"], []).append(row)
        order = {"RADIO": "Radios",
                 "REACTION_WHEEL": "High Heritage Miniature Reaction Wheels",
                 "PMAD": "Power Management And Distribution System Products"}
        for proto_cat, soa_cat in order.items():
            items = []
            ids = sorted(c["id"] for c in retr.components
                         if c["proto_category"] == proto_cat)
            src = sorted(rows.get(soa_cat, []),
                         key=lambda r: (r.get("component_name") or ""))
            for cid, r in zip(ids, src):
                mass = (r.get("mass_kg") or "").strip()
                mass_kg = float(mass) if mass not in ("", "nan") else None
                if mass_kg is not None and proto_cat == "RADIO":
                    mass_kg = mass_kg / 1000.0  # gram-scale quirk -> kg
                pw = (r.get("power_w") or "").strip()
                vol = ((r.get("volume_cm3") or "").strip() or
                       (r.get("dimension_volume_cm3") or "").strip())
                items.append({
                    "component_id": cid,
                    "name": r.get("component_name") or "",
                    "mass_kg": mass_kg,
                    "power_w": float(pw) if pw not in ("", "nan") else None,
                    "volume_cm3": float(vol) if vol not in ("", "nan") else None,
                })
            cat[proto_cat] = items
        return cat

    # -- persistence ------------------------------------------------------
    @staticmethod
    def _load(path, default):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save(self):
        with open(self.blueprint_path, "w") as f:
            json.dump(self.blueprint, f, indent=1)
        with open(self.cache_path, "w") as f:
            json.dump(self.cache, f, indent=1)

    def reset(self):
        self.blueprint = {"components": []}
        self.cache = {"last_valid": {"components": []},
                      "ranked": {}, "selected": {}}
        self._save()

    # -- validation -------------------------------------------------------
    @staticmethod
    def _fail(cmd, code, detail):
        resp = pb.PayloadResponse(
            header=pb.Header(
                protocol_version=PROTOCOL_VERSION,
                message_id="msg-%s" % uuid.uuid4().hex[:8],
                request_id=cmd.header.request_id,
                sender=pb.PAYLOAD, receiver=pb.SLM,
                timestamp_unix_sec=_now()),
            success=False, error_code=code, error_detail=detail,
            category=cmd.category, quantity=cmd.quantity)
        return resp.SerializeToString()

    def _validate(self, cmd):
        if cmd.header.sender != pb.SLM:
            return pb.INVALID_SENDER, "sender must be SLM"
        if cmd.header.receiver != pb.PAYLOAD:
            return pb.INVALID_RECEIVER, "receiver must be PAYLOAD"
        if cmd.intent not in (pb.ADD, pb.REMOVE, pb.UPDATE):
            return pb.INVALID_INTENT, "intent must be ADD/REMOVE/UPDATE"
        if cmd.category not in (pb.RADIO, pb.REACTION_WHEEL, pb.PMAD):
            return pb.INVALID_CATEGORY, "unknown category"
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

    # -- selection (mock ranking stand-in; CatBoost plugs in later) ------
    def _rank(self, catname, cmd):
        cands = [c for c in self.catalog.get(catname, [])]
        scored = []
        for c in cands:
            ok = True
            for field, cap in (("mass_kg", cmd.mass_kg),
                               ("power_w", cmd.power_w),
                               ("volume_cm3", cmd.volume_cm3)):
                if cap > 0 and (c[field] is None or c[field] > cap):
                    ok = False
            if cmd.component_id and c["component_id"] != cmd.component_id:
                ok = False
            scored.append((0 if ok else 1, c["component_id"]))
        scored.sort()
        return [cid for _, cid in scored]

    # -- command handling --------------------------------------------------
    def handle_command(self, data):
        cmd = pb.PayloadCommand()
        try:
            cmd.ParseFromString(data)
        except Exception as e:
            resp = pb.PayloadResponse(
                header=pb.Header(protocol_version=PROTOCOL_VERSION,
                                 message_id="msg-%s" % uuid.uuid4().hex[:8],
                                 request_id="", sender=pb.PAYLOAD,
                                 receiver=pb.SLM,
                                 timestamp_unix_sec=_now()),
                success=False, error_code=pb.VALIDATION_ERROR,
                error_detail="unparseable PayloadCommand: %s" % e)
            return resp.SerializeToString()

        code, detail = self._validate(cmd)
        if code != pb.ERROR_NONE:
            return self._fail(cmd, code, detail)

        catname = CATNAME[cmd.category]
        if cmd.intent == pb.ADD:
            ranked = self._rank(catname, cmd)
            if not ranked or self._lookup(ranked[0], catname) is None:
                return self._fail(cmd, pb.UNKNOWN_COMPONENT,
                                  "no candidate fits constraints")
            chosen = ranked[0]
            # ADD without explicit id selects best-ranked; explicit id kept.
            pick = cmd.component_id or chosen
            entry = {"component_id": pick, "category": catname,
                     "quantity": cmd.quantity, "mass_kg": cmd.mass_kg,
                     "power_w": cmd.power_w, "volume_cm3": cmd.volume_cm3}
            self.blueprint["components"] = [
                c for c in self.blueprint["components"]
                if c["component_id"] != pick] + [entry]
            self.cache["ranked"][catname] = ranked
            self.cache["selected"][catname] = pick
            self.cache["last_valid"] = json.loads(json.dumps(self.blueprint))
            self._save()
            return self._ok(cmd, pick)
        if cmd.intent == pb.REMOVE:
            before = len(self.blueprint["components"])
            if cmd.component_id:
                self.blueprint["components"] = [
                    c for c in self.blueprint["components"]
                    if c["component_id"] != cmd.component_id]
            else:
                left, n = [], cmd.quantity
                for c in self.blueprint["components"]:
                    if c["category"] == catname and n > 0:
                        n -= 1
                    else:
                        left.append(c)
                self.blueprint["components"] = left
            if len(self.blueprint["components"]) == before:
                return self._fail(cmd, pb.UNKNOWN_COMPONENT,
                                  "nothing to remove")
            self.cache["last_valid"] = json.loads(json.dumps(self.blueprint))
            self._save()
            return self._ok(cmd, cmd.component_id)
        # UPDATE: replace stored envelope for the component.
        for c in self.blueprint["components"]:
            if c["component_id"] == (cmd.component_id or
                                     self.cache["selected"].get(catname)):
                if cmd.quantity > 0:
                    c["quantity"] = cmd.quantity
                for f in ("mass_kg", "power_w", "volume_cm3"):
                    v = getattr(cmd, f)
                    if v > 0:
                        c[f] = v
                self.cache["last_valid"] = json.loads(
                    json.dumps(self.blueprint))
                self._save()
                return self._ok(cmd, c["component_id"])
        return self._fail(cmd, pb.UNKNOWN_COMPONENT, "nothing to update")

    def _lookup(self, cid, catname):
        for c in self.catalog.get(catname, []):
            if c["component_id"] == cid:
                return c
        return None

    def _ok(self, cmd, pick):
        resp = pb.PayloadResponse(
            header=pb.Header(
                protocol_version=PROTOCOL_VERSION,
                message_id="msg-%s" % uuid.uuid4().hex[:8],
                request_id=cmd.header.request_id,
                sender=pb.PAYLOAD, receiver=pb.SLM,
                timestamp_unix_sec=_now()),
            success=True, error_code=pb.ERROR_NONE, error_detail="",
            component_id=pick or "", category=cmd.category,
            quantity=cmd.quantity)
        return resp.SerializeToString()

    # -- risk events --------------------------------------------------------
    def handle_risk(self, data):
        ev = pb.RiskToPayload()
        ev.ParseFromString(data)
        if ev.header.sender != pb.RISK or ev.header.receiver != pb.PAYLOAD:
            raise ValueError("RiskToPayload must be RISK -> PAYLOAD")
        catname = CATNAME.get(ev.category, "")
        if ev.code == pb.P1:
            ranked = self.cache.get("ranked", {}).get(catname, [])
            cur = self.cache.get("selected", {}).get(catname)
            nxt = None
            if cur in ranked:
                i = ranked.index(cur)
                nxt = ranked[i + 1] if i + 1 < len(ranked) else None
            nxt = nxt or (ranked[0] if ranked else None)
            if not nxt:
                raise ValueError("P1: no cached candidates for %s" % catname)
            for c in self.blueprint["components"]:
                if c["category"] == catname and \
                        c["component_id"] == (ev.component_id or cur):
                    c["component_id"] = nxt
            self.cache["selected"][catname] = nxt
            self.cache["last_valid"] = json.loads(json.dumps(self.blueprint))
            self._save()
            return nxt
        if ev.code == pb.P2:
            self.blueprint = json.loads(json.dumps(
                self.cache.get("last_valid", {"components": []})))
            self._save()
            return True
        raise ValueError("unknown RiskPayloadCode")
