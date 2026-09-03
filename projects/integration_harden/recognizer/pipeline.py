"""Glue between the Recognizer and the live system.

Pipeline.handle() is a drop-in for the Router's on_complex callback: the router keeps handling
tiers 4/3/1 (emergency, override, basic verbs) exactly as today, and everything it classifies
COMPLEX lands here. handle() runs recognize(), then acts on the result:

    mission            -> wire.fly_mission(steps)           bypass answered, no model ran
    command            -> planner (Qwen3-VL) -> wire.fly_mission(mission)
    perception         -> vlm_query(text)
    reject             -> say() the recognized text back to the user (ruling 2026-09-02)
    emergency          -> wire.halt()   (backup net only: the router's own emergency tier acts
                          first and this branch should never run)

Both model servers are assumed already running: DictaLM on dicta_port (CPU, see
run_dicta_server.sh) and the resident Qwen3-VL on qwen_port. The Pipeline starts no servers.
Every utterance is recorded by trace.Trace.
"""
import json
import re
import time

try:
    from .llama import chat
    from .prompts import (REVISED_PROMPT, PLANNER_SHOTS_D, WIRE_GRAMMAR, LINE_GRAMMAR,
                          TRANSLATE_SYS, TRANSLATE_SHOTS)
    from .recognizer import recognize
    from .trace import Trace
except ImportError:                    # run flat from inside the package directory
    from llama import chat
    from prompts import (REVISED_PROMPT, PLANNER_SHOTS_D, WIRE_GRAMMAR, LINE_GRAMMAR,
                          TRANSLATE_SYS, TRANSLATE_SHOTS)
    from recognizer import recognize
    from trace import Trace

DICTA_PORT = 18091
QWEN_PORT = 18090

MISSION_KEYS = {"takeoff": set(), "land": set(), "fly_by": {"dx", "dy", "dz", "velocity"},
                "spin_by": {"degrees"}, "delay": {"seconds"}}
REJECT_PREFIX = "לא הבנתי, שמעתי: "


class Pipeline:

    def __init__(self, wire, vlm_query=None, say=print,
                 dicta_port=DICTA_PORT, qwen_port=QWEN_PORT,
                 plan_fn=None, trace_dir=None):
        self.wire = wire
        self.vlm_query = vlm_query or (lambda text: None)
        self.say = say
        self.dicta_port = dicta_port
        self.qwen_port = qwen_port
        self.plan_fn = plan_fn or self._plan          # tests inject a fake planner here
        self.trace = Trace(trace_dir)

    def handle(self, text):
        """Process one COMPLEX utterance. Returns a short action string for logs."""
        t0 = time.time()
        kind, payload, flags = recognize(text, self._translate)

        if kind == "emergency":                        # router missed it; the net still acts
            self.wire.halt()
            action = "emergency-halt(backup)"
        elif kind == "mission":
            self.wire.fly_mission(payload)
            action = f"mission({len(payload)} steps, bypass)"
        elif kind == "reject":
            self.say(REJECT_PREFIX + payload)
            action = "reject"
        elif kind == "perception":
            self.vlm_query(payload)
            action = "perception"
        elif kind == "command":
            mission = self.plan_fn(payload)
            if mission:                                # an empty mission is a refusal: no flight
                self.wire.fly_mission(mission)
                action = f"mission({len(mission)} steps, planned)"
            else:
                action = "planned-empty"
        else:                                          # unknown kind: never fall through to flight
            action = f"unknown-kind({kind})"

        self.trace.record(text=text, kind=kind, flags=flags, action=action,
                          payload=payload, ms=round((time.time() - t0) * 1000))
        return action

    def _translate(self, he, required_numbers=None):
        """Stage 3: one DictaLM call. Names the required numbers on the guard's retry, and
        re-asks without examples when the model echoes one of them."""
        system = TRANSLATE_SYS
        if required_numbers:
            listed = ", ".join(str(int(x)) if x == int(x) else str(x) for x in required_numbers)
            system += "\nThe English MUST contain exactly these numbers: " + listed
        text, _ = chat(self.dicta_port, system, he, max_tokens=200,
                       grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)
        text = text.strip()
        if any(text == answer for question, answer in TRANSLATE_SHOTS if question != he):
            retry, _ = chat(self.dicta_port, TRANSLATE_SYS + "\nTranslate ONLY the given sentence.",
                            he, max_tokens=200, grammar=LINE_GRAMMAR)
            if retry.strip():
                text = retry.strip()
        return text

    def _plan(self, english):
        """One Qwen3-VL call: English command -> wire-schema mission (or None on bad output).
        The grammar makes malformed JSON impossible; this parse is the second net."""
        out, _ = chat(self.qwen_port, REVISED_PROMPT, english,
                      grammar=WIRE_GRAMMAR, shots=PLANNER_SHOTS_D)
        m = re.search(r"\[.*\]", out or "", re.S)
        if not m:
            return None
        try:
            mission = json.loads(m.group(0))
        except Exception:
            return None
        if not isinstance(mission, list):
            return None
        for step in mission:
            if not isinstance(step, dict) or step.get("type") not in MISSION_KEYS:
                return None
            if any(k != "type" and k not in MISSION_KEYS[step["type"]] for k in step):
                return None
        return mission
