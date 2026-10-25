"""Component dependency dictionary and island builder for Logistics.

SPEC (master-prompts + Logistics phase):
- A plain Python dict is the dependency dictionary:
    {component_id: {"category", "manufacturer", "raa_deadline_unix_sec",
                    "delivery_time_unix_sec", "status",
                    "depends_on": [component_id, ...]}}
- Components depend on each other / share an island ONLY when their RAA
  deadlines MATCH exactly. An island is a connected dependency graph inside
  one deadline group (union-find over the dependency edges). Cross-deadline
  dependencies are recorded in the dict but never merge islands.
- Missing manufacturer delivery information => status "waiting",
  delivery_time None. Never invented.
- No field or column is invented: everything comes from RAA messages and the
  (currently absent) manufacturer delivery source.
"""
from collections import defaultdict

WAITING = "waiting"
SCHEDULED = "scheduled"
VIOLATED = "violated"
ON_TIME = "delivered_in_time"


def build_dependency_dict(records):
    """records: iterable of {component_id, category, manufacturer,
    raa_deadline_unix_sec, delivery_time_unix_sec, depends_on}.
    Returns the dependency dict (see module docstring). No invention:
    delivery_time stays None when the record has none."""
    out = {}
    for r in records:
        cid = r["component_id"]
        if cid in out:  # later evidence wins; retries stay safe
            continue
        dl = r.get("raa_deadline_unix_sec")
        if dl is None:
            raise ValueError("no RAA deadline for %s" % cid)
        delivery = r.get("delivery_time_unix_sec")
        status = WAITING if delivery is None else (
            VIOLATED if delivery > dl else ON_TIME)
        out[cid] = {
            "component_id": cid,
            "category": r.get("category") or "",
            "manufacturer": r.get("manufacturer") or "",
            "raa_deadline_unix_sec": int(dl),
            "delivery_time_unix_sec": (None if delivery is None
                                       else int(delivery)),
            "status": status,
            "depends_on": list(r.get("depends_on") or []),
        }
    return out


def build_islands(dep):
    """Connected components over dependency edges, PER EXACT DEADLINE GROUP.
    Returns {"by_id": {component_id: island_id},
             "members": {island_id: [component_id, ...]},
             "deadlines": {island_id: deadline}}.
    Two agents over different deadlines are NEVER the same island even if
    one depends on the other."""
    by_deadline = defaultdict(list)
    for cid, r in dep.items():
        by_deadline[r["raa_deadline_unix_sec"]].append(cid)

    by_id, members, deadlines = {}, {}, {}
    for dl in sorted(by_deadline):
        group = by_deadline[dl]
        parent = {cid: cid for cid in group}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for cid in group:
            for other in dep[cid]["depends_on"]:
                if other in parent:  # same deadline group only
                    ri, ro = find(cid), find(other)
                    if ri != ro:
                        parent[ro] = ri
        roots = {}
        for cid in group:
            root = find(cid)
            roots.setdefault(root, len(roots) + 1)
            island = "ISLAND_%d_%d" % (dl, roots[root])
            by_id[cid] = island
            members.setdefault(island, []).append(cid)
            deadlines[island] = dl
    return {"by_id": by_id, "members": members, "deadlines": deadlines}


def island_gaps(dep, islands):
    """Gaps that RAA should know: components inside an island that are
    waiting (no manufacturer delivery). Enumerated, never filled."""
    gaps = []
    for island, cids in islands["members"].items():
        for cid in cids:
            if dep[cid]["status"] == WAITING:
                gaps.append({"island_id": island, "component_id": cid,
                             "reason": "no manufacturer delivery data"})
    return gaps


def deadline_violations(dep):
    """Delivery past the original RAA deadline. Deadlines are never
    extended by Logistics: the violation is reported as-is."""
    return [{"component_id": cid, "raa_deadline_unix_sec": r["raa_deadline_unix_sec"],
             "delivery_time_unix_sec": r["delivery_time_unix_sec"],
             "late_by_s": r["delivery_time_unix_sec"] - r["raa_deadline_unix_sec"]}
            for cid, r in sorted(dep.items())
            if r["status"] == VIOLATED]


def earlier_plan_candidates(dep):
    """Deliveries that arrive EARLIER than the RAA deadline: evidence for
    Risk R1 (RAA reconsiders ordering)."""
    return [{"component_id": cid, "raa_deadline_unix_sec": r["raa_deadline_unix_sec"],
             "expected_delivery_unix_sec": r["delivery_time_unix_sec"],
             "early_by_s": r["raa_deadline_unix_sec"] - r["delivery_time_unix_sec"]}
            for cid, r in sorted(dep.items())
            if r["status"] == ON_TIME and
            (r["delivery_time_unix_sec"] < r["raa_deadline_unix_sec"])]
