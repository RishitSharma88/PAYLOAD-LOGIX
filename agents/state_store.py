"""Minimal Redis state mirror for PAYLOAD-LOGIX agents.

Redis was NOT present in this codebase before this feature (payload/db.py and
mock_payload_agent.py both said "no Redis in this stage"). Redis 8 was
introduced by that feature at the user's request; THESE KEYS are the first
defined state keys:

  pl:state:<agent>     -- current state line (== .txt line 1);
                          agents: payload, risk, logistics, raa
  pl:updated:<agent>   -- unix ts of the last state write
  pl:<agent>:health    -- JSON evidence blob (per-agent schema):
      payload    : last PayloadResponse summary (success, error_code, ...)
      logistics  : deadline_violations, waiting_count, earlier_plan,
                   islands, ts (written by the Logistics Agent)
      raa        : events, next_deadline, gaps, ts (written by RAA)
  pl:risk:actions      -- HASH field "<CODE>|<category>|<detail>|<component>"
                          -> unix ts of the last corrective message sent by
                          the Risk Agent (duplicate suppression)

Any Redis error is swallowed into .ok=False / .last_error so agents keep
operating without Redis. Connection URL: PL_REDIS_URL (default
redis://localhost:6379/0).
"""
import os
import time
import urllib.parse

import redis

DEFAULT_URL = "redis://localhost:6379/0"

K_STATE = "pl:state:%s"
K_UPDATED = "pl:updated:%s"
K_HEALTH = "pl:%s:health"
K_ACTIONS = "pl:risk:actions"


def redis_url():
    return os.environ.get("PL_REDIS_URL", DEFAULT_URL)


class AgentStateStore:
    def __init__(self, url=None):
        self.url = url or redis_url()
        self.last_error = None
        self.ok = False
        self._client = None
        self.recheck()

    # -- connection --------------------------------------------------------
    def recheck(self):
        """(Re)try connecting. Never raises."""
        try:
            c = redis.Redis.from_url(
                self.url, decode_responses=True,
                socket_connect_timeout=1.0, socket_timeout=1.0)
            c.ping()
            self._client, self.ok, self.last_error = c, True, None
        except Exception as e:
            self._client, self.ok, self.last_error = None, False, str(e)
        return self.ok

    def _op(self, fn):
        if not self.ok:
            return None
        try:
            return fn(self._client)
        except Exception as e:
            self.ok, self.last_error = False, str(e)
            return None

    # -- agent states -------------------------------------------------------
    def set_state(self, agent, line, ts=None):
        ts = int(ts or time.time())
        self._op(lambda r: r.set(K_STATE % agent, line))
        self._op(lambda r: r.set(K_UPDATED % agent, ts))
        return {"state": line, "updated": ts}

    def get_state(self, agent):
        """Returns {'state', 'updated'} or None if absent/unreachable."""
        line = self._op(lambda r: r.get(K_STATE % agent))
        if line is None:
            return None
        up = self._op(lambda r: r.get(K_UPDATED % agent))
        try:
            return {"state": line, "updated": int(up)}
        except (TypeError, ValueError):
            return {"state": line, "updated": 0}

    # -- agent health evidence ---------------------------------------------
    def set_health(self, data, agent="payload"):
        data = dict(data)
        data["ts"] = int(time.time())
        ok = self._op(lambda r: r.set(K_HEALTH % agent, _dumps(data)))
        return ok is not None

    def get_health(self, agent="payload"):
        raw = self._op(lambda r: r.get(K_HEALTH % agent))
        return _loads(raw)

    # -- duplicate suppression -----------------------------------------------
    def last_action_ts(self, key):
        return self._op(lambda r: r.hget(K_ACTIONS, key))

    def mark_action(self, key, ts=None):
        ts = int(ts or time.time())
        self._op(lambda r: r.hset(K_ACTIONS, key, ts))
        return ts

    def clear_actions(self):
        self._op(lambda r: r.delete(K_ACTIONS))


def _dumps(d):
    import json
    return json.dumps(d, default=str)


def _loads(raw):
    if raw is None:
        return None
    import json
    try:
        return json.loads(raw)
    except ValueError:
        return None
