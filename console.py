"""Interactive PAYLOAD-LOGIX console (local, no server).

Run: venv/bin/python console.py
Commands:
  /ask <question>   NASA-grounded Q&A (CAG + Qwen 7B)
  /blueprint        show current SQLite blueprint + thresholds
  /mock             switch to the mock Payload Agent
  /real             switch to the real Payload Agent (default)
  /convert <csv>    mount a synthetic CSV via the array tool
  /datasets         list mounted datasets
  /nasa             back to the NASA-backed agent path
  /quit             exit
With a dataset mounted, plain prompts run selection over it:
  Qwen interprets constraints -> deterministic filter -> Qwen selects.
"""
import sys

from agents.payload_agent import PayloadAgent
from orchestrator.slm import Orchestrator


def _caps_from_command(cmd):
    cons = cmd.get("constraints") or {}
    return {"max_mass_kg": cmd.get("mass_kg") or cons.get("max_mass_kg"),
            "max_power_w": cmd.get("power_w") or cons.get("max_power_w"),
            "max_volume_cm3": cmd.get("volume_cm3")
            or cons.get("max_volume_cm3")}


def main():
    agent = PayloadAgent()
    o = Orchestrator(payload_agent=agent)
    dataset = None
    print("PAYLOAD-LOGIX console (real agent). Type /quit to exit.")
    while True:
        try:
            line = input("\nYOU> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/mock":
            from agents.mock_payload_agent import MockPayloadAgent
            o.payload = MockPayloadAgent()
            dataset = None
            print("Switched to MOCK agent.")
            continue
        if line == "/real":
            o.payload = agent
            print("Switched to REAL agent.")
            continue
        if line == "/blueprint":
            print("THRESHOLDS:", agent.get_satellite_thresholds())
            for c in agent.get_blueprint():
                print(" -", c)
            continue
        if line == "/datasets":
            from payload import component_store as store
            print("Mounted:", store.loaded_names() or "(none)")
            continue
        if line == "/nasa":
            dataset = None
            print("Back to NASA-backed path.")
            continue
        if line.startswith("/convert "):
            from payload import component_store as store
            s = store.convert_csv(line[len("/convert "):].strip())
            dataset = s["dataset"]
            print("Converted:\n- file: %s\n- rows: %d\n- categories: %s"
                  "\n- manufacturers: %d\n- cached: %s" %
                  (s["file"], s["rows"], ",".join(s["categories"]),
                   len(s["manufacturers"]), "yes" if s["cached"] else "no"))
            continue
        if line.startswith("/ask "):
            r = o.ask(line[5:])
            print("SLM>", r["answer"])
            continue
        if dataset is not None:
            from payload import slm as pintel
            cmd, _ = o.interpret(line)
            if "clarify" in cmd:
                print("SLM>", cmd["clarify"])
                continue
            res = pintel.select_from_dataset(dataset, _caps_from_command(cmd))
            if res["component_id"] is None:
                print("SLM> No valid candidate exists for those "
                      "constraints.")
            else:
                print("SLM> Selected %s (%s)." %
                      (res["manufacturer"], res["component_id"]))
            continue
        t = o.run(line)
        if "clarify" in t.get("command_dict", {}):
            print("SLM>", t["command_dict"]["clarify"])
        else:
            print("CMD>", t["command_dict"])
            print("AGENT>", t["response_dict"])
            print("SLM>", t["final"])
    print("Bye.")


if __name__ == "__main__":
    sys.exit(main())
