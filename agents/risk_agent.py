"""Autonomous Risk Agent: background state monitor (P1/P2, L1/L2, R1/R2).

Machine-oriented: no conversational output. Polls agent states from Redis
every PL_RISK_POLL_SEC seconds (default 10, configurable via constructor or
env). All outgoing messages are protobuf bytes built from the EXISTING
payload_logix.v1 messages (RiskToPayload / RiskToLogistics / RiskToRaa) and
are logged as one readable JSON line each:

  {ts, protocol_version, sender, receiver, message_type, code, category,
   component_id, deadline_unix_sec, delivered, action, assessment}

Redis note: Redis was absent from this codebase before this feature; its
first-defined key schema lives in agents/state_store.py. LOGISTICS and RAA
agents do not exist yet, so their stale-monitor rules (L2/R2) only fire if
their state keys (pl:state:logistics / pl:state:raa) appear; L1/R1 need
deadline/plan data that does not exist yet and are reported as a gap, never
invented.

Reliability:
- findings require TWO consecutive polls with identical evidence;
- fingerprints in pl:risk:actions suppress duplicate corrective messages
  within the dedup window unless evidence changes;
- corrections go through the receiver's own handler (handle_risk), never by
  direct state writes;
- Redis/model errors degrade the monitor instead of crashing.
"""
import json
import os
import sys
import threading
import time

from proto import payload_logix_pb2 as pb
from agents import master_state
from agents.state_store import AgentStateStore
from orchestrator.protocol import new_header

DEFAULT_INTERVAL = 10.0
PBCAT = {"RADIO": pb.RADIO, "REACTION_WHEEL": pb.REACTION_WHEEL,
         "PMAD": pb.PMAD, "SATELLITE": pb.SATELLITE}

MISSING_RECEIVERS = [
    "L1/R1 not implementable: no deadline or delivery-plan data exists yet",
    "L2/R2 stale-rules only fire when pl:state:logistics / pl:state:raa "
    "exist (LOGISTICS/RAA agents not built yet)",
]


def _terminal_sink(record):
    sys.stdout.write("RISK-MSG> %s\n" % json.dumps(record, sort_keys=True,
                                                    default=str))
    sys.stdout.flush()


class RiskAgent:
    def __init__(self, payload=None, logistics=None, raa=None,
                 poll_interval=None, dedup_window_s=60.0,
                 stale_after_s=None, log_sink=None, redis_url=None,
                 use_model=True):
        self.prompt = master_state.load_prompt("risk")
        env_i = os.environ.get("PL_RISK_POLL_SEC")
        if poll_interval is None:
            poll_interval = float(env_i) if env_i else DEFAULT_INTERVAL
        self.poll_interval = float(poll_interval)
        env_d = os.environ.get("PL_RISK_DEDUP_SEC")
        self.dedup_window_s = float(env_d) if env_d else float(dedup_window_s)
        self.stale_after_s = float(os.environ.get("PL_RISK_STALE_SEC", 0)) \
            or (stale_after_s or 3.0 * self.poll_interval)
        self.payload = payload
        self.logistics = logistics
        self.raa = raa
        self.log_sink = log_sink or _terminal_sink
        self.use_model = use_model
        self.store = AgentStateStore(url=redis_url)
        self.gaps = list(MISSING_RECEIVERS)
        self.poll_count = 0
        self.sent = []          # JSON log records of outgoing messages
        self.recoveries = []
        self._pending = {}      # rule fingerprint -> first-seen ts
        self._last_health_fp = None
        self._stop = threading.Event()
        self._thread = None

    # -- master state -------------------------------------------------------
    def _update_state(self, line):
        try:
            info = master_state.set_state("risk", line)
            self.store.set_state("risk", info["state"], info["updated"])
        except Exception:
            pass

    # -- lifecycle ----------------------------------------------------------
    def start(self, background=True):
        self._update_state("STARTING monitor")
        self._stop.clear()
        if background:
            t = threading.Thread(target=self._loop, daemon=True,
                                 name="risk-agent")
            self._thread = t
            t.start()
            return t
        self._loop()
        return None

    def _loop(self):
        while not self._stop.is_set():
            began = time.time()
            try:
                self.poll_once()
            except Exception:
                self._update_state("FAILED poll cycle")
            self._stop.wait(max(0.05, self.poll_interval -
                                (time.time() - began)))

    def stop(self, timeout=2.0):
        """Clean, idempotent stop."""
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout)
        self._thread = None
        self._update_state("STOPPED idle")
        return True

    # -- one monitoring cycle -------------------------------------------------
    def poll_once(self):
        self.poll_count += 1
        if not self.store.ok:
            self.store.recheck()
            if not self.store.ok:
                self._update_state("DEGRADED no redis")
                return {"acted": False, "reason": "redis_unavailable"}
        self._update_state("MONITORING agent states")
        pstate = self.store.get_state("payload")
        if pstate is None:
            return {"acted": False, "reason": "no_payload_state"}
        findings = self._evaluate(pstate)
        if not findings:
            return {"acted": False, "reason": "healthy"}
        self._update_state("EVALUATING findings")
        results = [self._act(f) for f in findings]
        acted = [r for r in results if r.get("delivered")]
        if any(r.get("code") == "P1" and r.get("delivered") for r in results):
            self._update_state("CORRECTING blueprint")
        elif acted:
            self._update_state("RECOVERING state")
        return {"acted": bool(acted), "results": results}

    # -- explicit detection rules ----------------------------------------------
    def _evaluate(self, pstate):
        out = []
        # RULE STALE: non-IDLE activity unrefreshed longer than stale window.
        busy = not pstate["state"].startswith("IDLE") \
            and not pstate["state"].startswith("STOPPED") \
            and not pstate["state"].startswith("RECOVERED")
        if busy and (time.time() - pstate["updated"]) > self.stale_after_s:
            fp = "STALE|%.0f" % pstate["updated"]
            if self._confirmed(fp):
                out.append({"rule": "STALE", "msg": "RiskToPayload",
                            "code": "P2", "category": "", "component_id": "",
                            "detail": "stale state %.0fs: %r" %
                                      (self.stale_after_s, pstate["state"])})
        # RULE FAILED_PERSISTENT: identical failure evidence twice in a row.
        health = self.store.get_health()
        fp = None
        if health and not health.get("success"):
            fp = "%s|%s" % (health.get("error_code"),
                            health.get("error_detail"))
            if self._last_health_fp == fp:  # seen in a PREVIOUS poll
                cat = health.get("category") or ""
                cid = health.get("component_id") or ""
                if health.get("error_code") == int(pb.UNKNOWN_COMPONENT) \
                        and cat in PBCAT:
                    # next-best cached candidate (P1 semantics)
                    out.append({"rule": "FAILED_PERSISTENT",
                                "msg": "RiskToPayload", "code": "P1",
                                "category": cat, "component_id": cid,
                                "detail": "UNKNOWN_COMPONENT persists"})
                else:
                    # restore last valid state (P2 semantics)
                    out.append({"rule": "FAILED_PERSISTENT",
                                "msg": "RiskToPayload", "code": "P2",
                                "category": "", "component_id": "",
                                "detail": "failure persists: %s" %
                                          (health.get("error_detail") or "")[
                                              :120]})
            self._last_health_fp = fp
        else:
            self._last_health_fp = None
        # RULE CONFLICT: state line claims recovery/rest while failure
        # persists. Observed (own state) only; FAILED_PERSISTENT corrects,
        # so Conflict never duplicates a corrective message.
        st = master_state.read_state("payload")
        if health and not health.get("success") and \
                st["state"].startswith("IDLE") and fp and \
                self._last_health_fp == fp:
            self._update_state("WATCHING conflict")
        # RULE AGENT_STALE for LOGISTICS / RAA (only when their state exists).
        for agent, msg, code in (("logistics", "RiskToLogistics", "L2"),
                                 ("raa", "RiskToRaa", "R2")):
            s = self.store.get_state(agent)
            if s and s.get("state") not in ("STOPPED idle",) and \
                    (time.time() - s.get("updated", 0)) > self.stale_after_s:
                fp2 = "%s|%.0f" % (agent, s.get("updated", 0))
                if self._confirmed(fp2):
                    out.append({"rule": "AGENT_STALE", "msg": msg,
                                "code": code, "category": "",
                                "component_id": "", "deadline_unix_sec": 0,
                                "detail": "%s unresponsive" % agent.upper()})
        # RULE DEADLINE_VIOLATION: Logistics reports a delivery past the
        # original RAA deadline (evidence in pl:logistics:health). L1 =
        # deadline/order sync problem for that component + deadline.
        lh = self.store.get_health("logistics")
        if lh:
            for v in lh.get("deadline_violations") or []:
                fp3 = "DEADLINE_VIOLATION|%s|%s" % (
                    v.get("component_id"), v.get("raa_deadline_unix_sec"))
                if self._confirmed(fp3):
                    out.append({"rule": "DEADLINE_VIOLATION",
                                "msg": "RiskToLogistics", "code": "L1",
                                "category": "",
                                "component_id": v.get("component_id", ""),
                                "deadline_unix_sec":
                                    v.get("raa_deadline_unix_sec", 0),
                                "detail": "delivery late by %ss" %
                                          v.get("late_by_s", "?")})
            # RULE EARLIER_PLAN: Logistics reports an earlier valid delivery
            # -> RAA reconsiders ordering (R1).
            for e in lh.get("earlier_plan") or []:
                fp4 = "EARLIER_PLAN|%s|%s" % (
                    e.get("component_id"), e.get("expected_delivery_unix_sec"))
                if self._confirmed(fp4):
                    out.append({"rule": "EARLIER_PLAN", "msg": "RiskToRaa",
                                "code": "R1", "category": "",
                                "component_id": e.get("component_id", ""),
                                "deadline_unix_sec": 0,
                                "detail": "%s@earlier delivery plan" %
                                          e.get("component_id", "")})
        return out

    def _confirmed(self, fp):
        """True only when fp was already seen in a previous poll (two-poll
        confirmation). Returns False on the first sighting."""
        first = self._pending.get(fp)
        if first is None:
            self._pending[fp] = time.time()
            return False
        return True

    # -- corrective dispatch ------------------------------------------------------
    def _act(self, f):
        key = "%s|%s|%s|%s" % (f["code"], f.get("category") or "",
                               f.get("detail") or "",
                               f.get("component_id") or "")
        last = self.store.last_action_ts(key)
        # Unchanged evidence retries only after the dedup window expires.
        if last is not None and (time.time() - max(0.0, float(last))) < \
                self.dedup_window_s:
            return {"skipped": "duplicate", "record": None}
        assessment, source = self._assess(f)
        if f["msg"] == "RiskToPayload":
            delivered, err = self._dispatch_payload(f)
        elif f["msg"] == "RiskToLogistics":
            delivered, err = self._dispatch_logistics(f)
        elif f["msg"] == "RiskToRaa":
            delivered, err = self._dispatch_raa(f)
        else:
            # L1/L2/R1/R2: receivers are not registered in this build.
            delivered, err = False, "no receiver registered"
        rec = self._log(f, delivered=delivered, action=f["detail"],
                        assessment=assessment, assessment_source=source,
                        error=err)
        self.sent.append(rec)
        if delivered and f["code"] in ("P1", "P2"):
            self.recoveries.append({"code": f["code"], "rule": f["rule"],
                                    "ts": rec["ts"]})
        return {"delivered": delivered, "code": f["code"], "record": rec}

    def _dispatch_payload(self, f):
        if self.payload is None:
            return False, "no payload receiver registered"
        data = pb.RiskToPayload(
            header=new_header(pb.RISK, pb.PAYLOAD),
            code=pb.P1 if f["code"] == "P1" else pb.P2,
            category=PBCAT.get(f.get("category") or "", pb.CATEGORY_UNSPECIFIED),
            component_id=f.get("component_id") or "",
            detail=(f.get("detail") or "")[:200]).SerializeToString()
        try:
            self.payload.handle_risk(data)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _dispatch_logistics(self, f):
        if self.logistics is None:
            return False, "no logistics receiver registered"
        data = pb.RiskToLogistics(
            header=new_header(pb.RISK, pb.LOGISTICS),
            code=pb.L1 if f["code"] == "L1" else pb.L2,
            category=PBCAT.get(f.get("category") or "", pb.CATEGORY_UNSPECIFIED),
            component_id=f.get("component_id") or "",
            deadline_unix_sec=int(f.get("deadline_unix_sec") or 0),
            detail=(f.get("detail") or "")[:200]).SerializeToString()
        try:
            self.logistics.handle_risk(data)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _dispatch_raa(self, f):
        if self.raa is None:
            return False, "no raa receiver registered"
        data = pb.RiskToRaa(
            header=new_header(pb.RISK, pb.RAA),
            code=pb.R1 if f["code"] == "R1" else pb.R2,
            detail=(f.get("detail") or "")[:200]).SerializeToString()
        try:
            self.raa.handle_risk(data)
            return True, ""
        except Exception as e:
            return False, str(e)

    def receive_from_logistics(self, data):
        """Accept status evidence without conversational output."""
        return data

    def receive_from_raa(self, data):
        return data

    # -- model assessment (shared Qwen3-1.7B config, optional) ---------------------
    def _assess(self, f):
        if os.environ.get("PL_RISK_MODEL", "1") == "0" or not self.use_model:
            return "rules matched %s -> %s" % (f["rule"], f["code"]), \
                "rules_only"
        try:
            from payload import slm
            out = slm._gen(
                "You are the RISK agent monitor. Output ONE short machine "
                "phrase (max 12 words) stating which rule matched and which "
                "protocol code is required. No prose, no thinking.",
                "Finding %s" % json.dumps(f)[:400], max_tokens=512)
            txt = out.split("</think>")[-1] if "</think>" in out else out
            txt = " ".join(txt.split())[:120]
            if txt:
                return txt, "qwen3"
            raise ValueError("empty assessment")
        except Exception:
            return "rules matched %s -> %s" % (f["rule"], f["code"]), \
                "rules_fallback"

    # -- JSON logging -------------------------------------------------------------
    def _log(self, f, delivered, action, assessment=None,
             assessment_source=None, error=None):
        rec = {
            "ts": round(time.time(), 3),
            "protocol_version": "1.0",
            "sender": "RISK",
            "receiver": {"RiskToPayload": "PAYLOAD",
                         "RiskToLogistics": "LOGISTICS",
                         "RiskToRaa": "RAA"}[f["msg"]],
            "message_type": f["msg"],
            "code": f["code"],
            "category": f.get("category") or "",
            "component_id": f.get("component_id") or "",
            "deadline_unix_sec": f.get("deadline_unix_sec", 0),
            "delivered": bool(delivered),
            "rule": f["rule"],
            "action": action,
            "assessment": assessment or "",
            "assessment_source": assessment_source or "",
        }
        if error:
            rec["error"] = error
        # Successful deliveries renew the dedup window; failures retry soon.
        self.store.mark_action(
            "%s|%s|%s|%s" % (f["code"], rec["category"], f.get("detail") or "",
                             rec["component_id"]),
            ts=rec["ts"] if delivered else 0)
        try:
            self.log_sink(rec)
        except Exception:
            pass
        return rec
