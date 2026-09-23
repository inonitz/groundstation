"""Glue between the Recognizer and the live system (harden2: one Gemma call, no translator).

Pipeline.handle() is the Router's on_complex callback. Everything the router classifies COMPLEX lands
in handle_direct(), which runs recognize_direct() then acts on the result:

    mission     -> wire.fly_mission(steps)     bypass answered, no model ran
    (direct)    -> one Gemma call (_plan2) -> {"kind","target_en","mission"} -> fly / perceive / reject
    reject      -> say() the Hebrew back (negation guard, number guard, planner echo, unroutable)
    emergency   -> wire.halt()   (backup net only; the router's own emergency tier acts first)

The Gemma server is assumed already running on qwen_port (18090). The Pipeline starts no servers.
Every utterance is recorded by trace.Trace.
"""
import json
import re
import time
import config
from control.dji_wire import LATCHED, UNREACHABLE, sent
from gemma.client import request
from perception2.lexicon import fix_target   # HE->EN correction net under Gemma; a required module

try:
    from .prompts import UNIFIED_PROMPT, UNIFIED_GRAMMAR, UNIFIED_SHOTS, PLANNER_SHOTS_D
    from .recognizer import _nums_en, recognize_direct, numbers_vs_mission
    from .trace import Trace
except ImportError:                    # run flat from inside the package directory
    from prompts import UNIFIED_PROMPT, UNIFIED_GRAMMAR, UNIFIED_SHOTS, PLANNER_SHOTS_D
    from recognizer import _nums_en, recognize_direct, numbers_vs_mission
    from trace import Trace

QWEN_PORT = config.LLAMA_SERVER_PORT       # the Gemma server (name kept for the bench's qwen_port= call)
PLAN_TIMEOUT_S = 180.0                     # one planning call; was the old chat() timeout

# The planner's own few-shot missions. A planned mission identical to one of them, from an input that
# carries none of that example's numbers, is a COPY of the example, not a plan (live 2026-09-08 u74).
SHOT_MISSIONS = [(json.loads(a)) for _, a in PLANNER_SHOTS_D if json.loads(a)]


def _mission_numbers(mission):
    return {abs(float(v)) for step in mission for k, v in step.items() if k != "type"}


def is_shot_echo(english, mission):
    for shot in SHOT_MISSIONS:
        if mission == shot:
            nums = _mission_numbers(shot)
            if not nums or not (set(_nums_en(english)) & nums):
                return True
    return False


class Pipeline:

    REJECT_HE = "לא הבנתי: "                # Hebrew readback prefix (answers go straight to the phone TTS)

    def __init__(self, wire, vlm_query=None, say=print, qwen_port=QWEN_PORT,
                 trace_dir=None, plan2_fn=None, observe=None):
        self.wire = wire
        self.vlm_query = vlm_query or (lambda text: None)
        self.say = say
        self.qwen_port = qwen_port
        self.plan2_fn = plan2_fn                # tests inject the unified Gemma call here
        self.observe = observe or (lambda **k: None)   # optional: report he2/flags/kind/target to a trace sink
        self.flight_allowed = lambda: True             # mvd wires this to Router.mode (manual -> no flight)
        self.trace = Trace(trace_dir)

    def _fly(self, mission, tag):
        """Send the mission; name the outcome so the session log tells a flight from a refusal.
        Refuses in manual mode (Router handed control to the RC) -- perception still answers."""
        base = f"mission({len(mission)} steps, {tag})"
        if not self.flight_allowed():
            return f"refused-manual {base}"
        code = self.wire.fly_mission(mission)
        if sent(code):
            return base
        if code == LATCHED:
            return f"REFUSED-kill-latch {base}"
        if code == UNREACHABLE:
            return f"FAILED-unreachable {base}"
        return f"FAILED-HTTP-{code} {base}"                 # the phone answered with an error (review R13)

    def handle(self, text):
        return self.handle_direct(text)

    def handle_direct(self, text):
        """harden2: one Gemma call routes, plans and names the object. Returns the action string."""
        t0 = time.time()
        kind, payload, flags = recognize_direct(text)
        _rec_ms = round((time.time() - t0) * 1000)
        _plan_ms = 0
        self.observe(flags=flags)
        obj = None
        if kind == "emergency":
            code = self.wire.halt()
            if sent(code):
                action = "emergency-halt(backup)"
            elif code == LATCHED:
                action = "emergency-halt(backup) refused: the kill latch is on"
            else:
                action = f"emergency-halt(backup) FAILED (HTTP {code})"
            self.observe(kind="emergency")
        elif kind == "mission":
            action = self._fly(payload, "bypass")
            self.observe(kind="mission", mission=payload)
        elif kind == "reject":
            self.say(self.REJECT_HE + text)
            action = "reject-neg-guard"
            self.observe(kind="reject")
        else:
            he2 = payload
            self.observe(he2=he2)
            _tp = time.time()
            obj = (self.plan2_fn or self._plan2)(he2) or {}
            _plan_ms = round((time.time() - _tp) * 1000)
            k2 = obj.get("kind")
            target = (obj.get("target_en") or "").strip()
            mission = obj.get("mission") or []
            self.observe(kind=k2, target_en=(target or None), mission=(mission or None))
            if k2 == "mission":
                missing = numbers_vs_mission(he2, mission)
                if not mission:
                    action = "planned-empty"
                elif missing:
                    self.say(self.REJECT_HE + text)
                    flags.append(f"REJECT-numbers{missing}")
                    action = "reject-numbers"
                elif is_shot_echo(he2, mission):
                    self.say(self.REJECT_HE + text)
                    action = "reject-planner-echo"
                else:
                    action = self._fly(mission, "planned")
            elif k2 in ("highlight", "count") and target:
                target, note = fix_target(he2, target)          # HE->EN lexicon under Gemma (block B 2026-09-09: 'cabin' for מגירות)
                if note:
                    flags.append(note); print(f"[recognizer] {note}", flush=True)
                if k2 == "highlight":
                    self.vlm_query(f"highlight the {target}")
                    action = f"perception(highlight: {target})"
                else:
                    self.vlm_query(f"count the {target}")   # -> TextHandler._handle_count -> SAM3 alone
                    action = f"perception(count: {target})"
            elif k2 == "describe":
                self.vlm_query(text)
                action = "perception(describe)"
            elif k2 == "failed":
                action = "gemma-failed"       # not the user's fault: no "I did not understand"; the panel shows Gemma
            else:
                self.say(self.REJECT_HE + text)
                action = "reject"
        self.observe(timings={"recognizer_ms": _rec_ms, "plan_ms": _plan_ms, "e2e_ms": round((time.time() - t0) * 1000)})
        self.observe(action=action)
        self.trace.record(text=text, kind=kind, flags=flags, action=action, payload=obj, ms=round((time.time() - t0) * 1000))
        return action

    def _plan2(self, he2):
        """One Gemma call: Hebrew -> {"kind", "target_en", "mission"} under UNIFIED_GRAMMAR.
        A failed request -> {"kind": "failed"}, so handle() does not answer "I did not understand"."""
        msgs = [{"role": "system", "content": UNIFIED_PROMPT}]
        for user, answer in UNIFIED_SHOTS:
            msgs += [{"role": "user", "content": user}, {"role": "assistant", "content": answer}]
        msgs.append({"role": "user", "content": he2})
        ok, out = request(msgs, grammar=UNIFIED_GRAMMAR, max_tokens=300, timeout_s=PLAN_TIMEOUT_S, port=self.qwen_port)
        if not ok:
            return {"kind": "failed"}
        m = re.search(r"\{.*\}", out, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:   # the model returned text that is not valid JSON
            return None
