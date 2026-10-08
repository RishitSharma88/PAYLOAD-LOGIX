"""Protocol helpers: dict <-> protobuf conversions with strict validation."""
import time
import uuid

from proto import payload_logix_pb2 as pb

PROTOCOL_VERSION = "1.0"

RECEIVERS = {"PAYLOAD": pb.PAYLOAD, "LOGISTICS": pb.LOGISTICS,
             "RAA": pb.RAA}
INTENTS = {"ADD": pb.ADD, "REMOVE": pb.REMOVE, "UPDATE": pb.UPDATE}
CATEGORIES = {"RADIO": pb.RADIO, "REACTION_WHEEL": pb.REACTION_WHEEL,
              "PMAD": pb.PMAD, "SATELLITE": pb.SATELLITE}


def new_header(sender, receiver, request_id=None):
    return pb.Header(protocol_version=PROTOCOL_VERSION,
                     message_id="msg-%s" % uuid.uuid4().hex[:8],
                     request_id=request_id or "req-%s" % uuid.uuid4().hex[:8],
                     sender=sender, receiver=receiver,
                     timestamp_unix_sec=int(time.time()))


def command_from_dict(d):
    """Strict: unknown enum strings raise ValueError (never default)."""
    if d.get("receiver") not in RECEIVERS:
        raise ValueError("invalid receiver: %r" % d.get("receiver"))
    if d.get("intent") not in INTENTS:
        raise ValueError("invalid intent: %r" % d.get("intent"))
    if d.get("category") not in CATEGORIES:
        raise ValueError("invalid category: %r" % d.get("category"))
    cons = d.get("constraints") or {}
    qty = d.get("quantity")
    if (qty is None or int(qty or 0) <= 0) and d["intent"] == "ADD":
        qty = 1  # singular requests ("a radio") imply one unit
    cmd = pb.PayloadCommand(
        header=new_header(pb.SLM, RECEIVERS[d["receiver"]]),
        intent=INTENTS[d["intent"]],
        category=CATEGORIES[d["category"]],
        component_id=d.get("component_id") or "",
        quantity=int(qty or 0),
        mass_kg=float(d.get("mass_kg") or cons.get("max_mass_kg") or 0.0),
        power_w=float(d.get("power_w") or cons.get("max_power_w") or 0.0),
        volume_cm3=float(d.get("volume_cm3")
                         or cons.get("max_volume_cm3") or 0.0))
    if d.get("dimensions_cm"):
        l, w, h = d["dimensions_cm"]
        cmd.dimensions.length_cm, cmd.dimensions.width_cm, \
            cmd.dimensions.height_cm = float(l), float(w), float(h)
    if d.get("constraints"):
        for k, f in (("max_mass_kg", "max_mass_kg"),
                     ("max_power_w", "max_power_w"),
                     ("max_volume_cm3", "max_volume_cm3")):
            if d["constraints"].get(k) is not None:
                setattr(cmd.constraints, f, float(d["constraints"][k]))
    return cmd


def response_to_dict(resp):
    return {"success": bool(resp.success),
            "error_code": pb.ErrorCode.Name(resp.error_code),
            "error_detail": resp.error_detail,
            "component_id": resp.component_id,
            "category": pb.ComponentCategory.Name(resp.category)
            if resp.category else "CATEGORY_UNSPECIFIED",
            "quantity": resp.quantity,
            "request_id": resp.header.request_id}
