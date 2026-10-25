"""Master prompt/state files for PAYLOAD-LOGIX agents (config/).

Files (created by the master-prompts feature):
  config/payload_master_prompt.txt   Payload Agent role definition
  config/payload_master_state.txt    Payload current state + updated ts
  config/risk_master_prompt.txt      Risk Agent role definition
  config/risk_master_state.txt       Risk current state + updated ts

State file format (machine-readable, exactly 2 lines):
  <STATE>           max 3 words, e.g. "IDLE awaiting commands"
  updated <unix_t>  unix seconds of the last state write
"""
import os
import time

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "config")

PROMPTS = {"payload": "payload_master_prompt.txt",
           "risk": "risk_master_prompt.txt",
           "logistics": "logistics_master_prompt.txt",
           "raa": "raa_master_prompt.txt"}
STATES = {"payload": "payload_master_state.txt",
          "risk": "risk_master_state.txt",
          "logistics": "logistics_master_state.txt",
          "raa": "raa_master_state.txt"}
MAX_WORDS = 3


def load_prompt(agent):
    with open(os.path.join(CONFIG_DIR, PROMPTS[agent])) as f:
        return f.read()


def read_state(agent):
    try:
        with open(os.path.join(CONFIG_DIR, STATES[agent])) as f:
            lines = f.read().splitlines()
        return {"state": lines[0].strip(),
                "updated": int(lines[1].split()[-1])}
    except (OSError, IndexError, ValueError):
        return {"state": "UNKNOWN unreadable state", "updated": 0}


def set_state(agent, line, ts=None):
    """Atomic state-file update. Raises ValueError if the line exceeds
    %d words (≤3 words per state is the contract). ts override is for
    tests/stale-window simulation only.""" % MAX_WORDS
    line = " ".join(line.split())
    if len(line.split()) > MAX_WORDS:
        raise ValueError("state line >%d words: %r" % (MAX_WORDS, line))
    path = os.path.join(CONFIG_DIR, STATES[agent])
    ts = int(ts or time.time())
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("%s\nupdated %d\n" % (line, ts))
    os.replace(tmp, path)
    return {"state": line, "updated": ts}
