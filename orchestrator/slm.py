"""PAYLOAD-LOGIX Orchestrator: local Qwen2.5-Coder-7B hub, weights frozen.

Pipeline per user request:
  text -> CAG retrieve -> Qwen interprets -> JSON command dict
  -> protobuf -> Mock Payload Agent -> protobuf response -> Qwen renders NL.

Qwen weights are NEVER modified or fine-tuned; all behavior comes from
config/orchestrator_system_prompt.txt + per-request CAG context.
"""
import json
import os

from proto import payload_logix_pb2 as pb
from orchestrator import protocol
from cag.retriever import NasaRetriever

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE, "models", "qwen2.5-coder-7b-instruct-4bit")
SYSTEM_PROMPT = os.path.join(BASE, "config", "orchestrator_system_prompt.txt")

_model = None
_tokenizer = None


def _load():
    global _model, _tokenizer
    if _model is None:
        from mlx_lm import load
        _model, _tokenizer = load(MODEL_PATH)
    return _model, _tokenizer


def _gen(system, user, max_tokens=256, temp=0.1, system_file=SYSTEM_PROMPT):
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler
    model, tok = _load()
    if system_file:
        with open(system_file) as f:
            sys = f.read()
        sys = sys + "\n\n" + system
    else:
        sys = system
    msgs = [{"role": "system", "content": sys},
            {"role": "user", "content": user}]
    prompt = tok.apply_chat_template(msgs, add_generation_prompt=True)
    return generate(model, tok, prompt=prompt, max_tokens=max_tokens,
                    sampler=make_sampler(temp=temp), verbose=False)


def _extract_json(text):
    s = text.strip()
    if "```" in s:  # strip code fences
        parts = s.split("```")
        for p in parts:
            if "{" in p:
                s = p[p.index("{"):]
                break
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object in model output: %r" % text[:200])
    return json.loads(s[i:j + 1])


class Orchestrator:
    def __init__(self, payload_agent=None):
        self.retriever = NasaRetriever()
        if payload_agent is None:
            from agents.mock_payload_agent import MockPayloadAgent
            payload_agent = MockPayloadAgent()
        self.payload = payload_agent

    def interpret(self, user_text):
        """NL -> command dict (or {'clarify': ...}). Uses CAG context."""
        ctx = self.retriever.format_context(user_text)
        out = _gen("TASK: translate the user request into ONE command "
                   "object.", ctx + "\n\nUSER REQUEST: " + user_text)
        return _extract_json(out), ctx

    def render(self, user_text, cmd_dict, resp_dict):
        out = _gen(
            "TASK: render the agent result for the user in 1-2 sentences.",
            "USER REQUEST: %s\nCOMMAND: %s\nAGENT RESPONSE: %s" %
            (user_text, json.dumps(cmd_dict), json.dumps(resp_dict)),
            max_tokens=128)
        return out.strip()

    def ask(self, user_text):
        """Grounded NASA Q&A: CAG context -> Qwen answer (no commands)."""
        ctx = self.retriever.format_context(user_text)
        out = _gen("You are the PAYLOAD-LOGIX Orchestrator answering a "
                   "NASA knowledge question. Use ONLY the CAG CONTEXT "
                   "below. Answer in plain sentences, citing record ids "
                   "like [RADIO_008]. If the context lacks the "
                   "information, say the NASA source does not provide "
                   "enough information. Never invent facts.",
                   ctx + "\n\nQUESTION: " + user_text, max_tokens=256,
                   system_file=None)
        return {"context": ctx, "answer": out.strip()}

    def run(self, user_text):
        """Full vertical slice. Returns trace dict for tests/demos."""
        trace = {"user": user_text}
        cmd_dict, ctx = self.interpret(user_text)
        trace["cag"] = ctx
        trace["command_dict"] = cmd_dict
        if "clarify" in cmd_dict:
            trace["final"] = cmd_dict["clarify"]
            return trace
        cmd = protocol.command_from_dict(cmd_dict)
        trace["protobuf_command"] = str(cmd).strip()
        raw = self.payload.handle_command(cmd.SerializeToString())
        resp = pb.PayloadResponse()
        resp.ParseFromString(raw)
        resp_dict = protocol.response_to_dict(resp)
        trace["response_dict"] = resp_dict
        trace["final"] = self.render(user_text, cmd_dict, resp_dict)
        return trace
