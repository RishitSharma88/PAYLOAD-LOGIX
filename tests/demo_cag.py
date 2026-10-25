"""Demo 2 (NASA CAG): grounded answer + honest no-info case.

Run: venv/bin/python tests/demo_cag.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.slm import Orchestrator

if __name__ == "__main__":
    o = Orchestrator()
    print("=== Q1 (in-scope: S-band radios) ===")
    r = o.ask("Which NASA SOA radios support S-band?")
    print(r["context"])
    print("ANSWER:", r["answer"])
    print()
    print("=== Q2 (out-of-scope: Hall thrusters, propulsion not indexed) ===")
    r = o.ask("What Hall-effect thrusters are in the NASA source?")
    print(r["context"])
    print("ANSWER:", r["answer"])
