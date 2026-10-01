"""The Recognizer: ONE sentence in -> a Routed out (API: docs/api-harden2/recognizer.h).
It parses EVERY sentence (owner ruling 2026-09-23) in two chained steps
(owner 2026-09-26, "One should make the decision, one should do the acting"):

    route(text) -> Decision   decides; sends nothing. The recognizer benchmark calls it.
    act(decision) -> Routed   carries it out: control, vision, or the words to say.
    handle(text) = act(route(text)), the app's one call.

What route() decides:
    emergency / manual / auto -> control at once (the fast path: no model ran)
    clear                     -> vision.clear() (no model ran)
    mission                   -> control.fly(steps): the bypass answered, no model ran
    reject                    -> the negation guard refused it (no model ran)
    direct                    -> ONE Gemma call, plan(), -> {kind, target_en, mission}
                                 -> a mission | a vision request | reject

It speaks nothing itself: flight goes through control, vision through perception2.vision,
and handle() returns a Routed that the app shows and speaks. The Gemma server is started
by the app; the Recognizer only asks it.
"""
import re
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Optional

import config
from control.flight import outcome_text
from perception2.vision import TASK_FULL
from util.guarded import parse_json
from .guards import is_shot_echo, numbers_vs_mission
from .lexicon import fix_target
from .parse import recognize_direct
from .prompts import UNIFIED_GRAMMAR, UNIFIED_PROMPT, UNIFIED_SHOTS

PLAN_TIMEOUT_S = 180.0              # one planning call
PLAN_MAX_TOKENS = 300
REJECT_HE = "לא הבנתי: "            # the Hebrew read-back prefix, spoken on a reject


def reject_why(action):
    """The plain reason for a rejection, so the operator can judge whether it was valid
    (owner 2026-09-12)."""
    a = action or ""
    if a.startswith("reject-neg-guard"):
        return "negation with no action (e.g. 'do not move')"
    if a.startswith("reject-numbers"):
        return "a number in the command did not match the plan"
    if a.startswith("reject-planner-echo"):
        return "the model echoed a built-in example, not a real plan"
    return (
        "the model could not turn this into an action "
        "(drone-state question / greeting / out of scope)"
    )


@dataclass
class Routed:
    """What the recognizer did with one sentence. The app shows and speaks it.
    @kind: critical | flight | vision | reject | gemma_failed | empty
    @action: the log tag (e.g. "mission(2 steps, planned)", "reject-numbers").
    @say: the text to show and speak, or None (a vision result arrives later, through
    the vision callbacks)."""
    kind: str
    action: str
    say: Optional[str] = None
    vision_task: Optional[int] = None
    vision_status: Optional[str] = None


@dataclass
class Decision:
    """What route() decided for one sentence. Nothing has been sent yet.
    @kind: emergency | manual | auto | clear | mission | highlight | count | describe |
        reject | gemma_failed | empty
    @text: the sentence as said.
    @he2: the Hebrew Gemma read ("" when no model ran).
    @mission: the steps (a mission; also a guarded reject, to show what was refused).
    @tag: how a mission was made: "bypass" (no model) or "planned" (Gemma).
    @target: the English target (highlight, count; describe: Gemma's target_en).
    @action: a reject's log tag (reject-neg-guard | reject-numbers |
        reject-planner-echo | reject).
    @flags: the parser's and the guards' notes."""
    kind: str
    text: str
    he2: str = ""
    mission: list = field(default_factory=list)
    tag: str = ""
    target: str = ""
    action: str = ""
    flags: list = field(default_factory=list)
    recognize_ms: int = 0
    plan_ms: int = 0


class Recognizer:
    """@control: control.flight.Control. @vision: perception2.vision.Vision (None in the
    benches, which never route to vision). @gemma: gemma.client.Gemma. @log: the session
    log (every turn's record), or None (benches)."""

    def __init__(self, control, vision, gemma, log=None):
        self.control = control
        self.vision = vision
        self.gemma = gemma
        self.log = log
        return

    def close(self):
        """Nothing to release: the session log writes each record when it is made."""
        return

    def observe(self, **fields):
        """Add fields (he2, flags, kind, target, action, timings) to this turn's log
        record."""
        if self.log is None:
            return
        self.log.set(**fields)
        return

    # --- one sentence ---------------------------------------------------------------
    def handle(self, text):
        """Decide, then act: route() then act(). -> Routed."""
        t0 = time.monotonic()
        decision = self.route(text)
        routed = self.act(decision)
        e2e_ms = round((time.monotonic() - t0) * 1000)
        self.observe(
            timings={
                "recognizer_ms": decision.recognize_ms,
                "plan_ms": decision.plan_ms,
                "e2e_ms": e2e_ms,
            },
            action=routed.action
        )
        return routed

    def route(self, text):
        """Decide what one sentence means. It sends nothing: no control, no vision
        (owner 2026-09-26: "One should make the decision, one should do the acting").
        The app and the recognizer benchmark both call it. -> Decision."""
        plan_ms = 0

        t0 = time.monotonic()
        kind, payload, flags = recognize_direct(text)
        rec_ms = round((time.monotonic() - t0) * 1000)
        self.observe(flags=flags)

        if kind != "direct":
            decision = self._decide_without_model(kind, text, payload)
        else:
            self.observe(he2=payload)
            t_plan = time.monotonic()
            plan = self.plan(payload) or {}
            plan_ms = round((time.monotonic() - t_plan) * 1000)
            decision = self._decide_plan(text, payload, plan, flags)

        decision.flags = flags
        decision.recognize_ms = rec_ms
        decision.plan_ms = plan_ms
        return decision

    def act(self, decision):
        """Carry out a Decision: control, vision, or only the words to say. -> Routed."""
        kind = decision.kind

        if kind in ("emergency", "manual", "auto"):
            return self._critical(kind)
        if kind == "mission":
            return self._fly(decision.mission, decision.tag)
        if kind == "clear":
            return self._vision("clear", "")
        if kind == "describe":
            return self._vision("describe", decision.text)   # the question as said
        if kind in ("highlight", "count"):
            return self._vision(kind, decision.target)
        if kind == "gemma_failed":
            # not the user's fault: no "I did not understand"; the status pane shows
            # Gemma
            return Routed("gemma_failed", "gemma-failed")
        if kind == "empty":
            return Routed("empty", "planned-empty")
        return self._reject(decision.text, decision.action)

    def plan(self, he2):
        """The ONE Gemma call: Hebrew -> {"kind", "target_en", "mission"} under
        UNIFIED_GRAMMAR. -> the plan; {"kind": "failed"} when the request failed (so the
        user is not told "I did not understand"); None when the reply is not a plan."""
        msgs = plan_messages(he2)

        ok, out = self.gemma.request(
            msgs,
            grammar=UNIFIED_GRAMMAR,
            max_tokens=PLAN_MAX_TOKENS,
            timeout_s=PLAN_TIMEOUT_S,
            label="plan"
        )
        if not ok:
            return {"kind": "failed"}

        m = re.search(r"\{.*\}", out, re.S)
        if not m:
            return None
        ok, plan = parse_json(m.group(0))       # the model can write text, not JSON
        if not ok:
            return None
        return plan

    # --- deciding ---------------------------------------------------------------------
    def _decide_without_model(self, kind, text, payload):
        """The answers the parser gave on its own: critical, clear, mission, reject."""
        if kind in ("emergency", "manual", "auto"):
            self.observe(kind=kind)
            return Decision(kind, text)

        if kind == "clear":
            self.observe(kind="clear")
            return Decision("clear", text)

        if kind == "mission":
            self.observe(kind="mission", mission=payload)
            return Decision("mission", text, mission=payload, tag="bypass")

        # the negation guard refused it
        self.observe(kind="reject")
        return Decision("reject", text, action="reject-neg-guard")

    def _decide_plan(self, text, he2, plan, flags):
        """Judge Gemma's {kind, target_en, mission}. -> Decision."""
        kind = plan.get("kind")
        target = (plan.get("target_en") or "").strip()
        mission = plan.get("mission") or []
        self.observe(kind=kind, target_en=(target or None), mission=(mission or None))

        if kind == "mission":
            return self._decide_mission(text, he2, mission, flags)
        if kind in ("highlight", "count") and target:
            target, note = fix_target(he2, target)
            if note:
                # the HE->EN lexicon checks Gemma's target (block B 2026-09-09:
                # 'cabin' for מגירות)
                flags.append(note)
                print(f"[recognizer] {note}", flush=True)
            return Decision(kind, text, he2=he2, target=target)
        if kind == "describe":
            return Decision("describe", text, he2=he2, target=target)
        if kind == "failed":
            return Decision("gemma_failed", text, he2=he2)
        return Decision("reject", text, he2=he2, action="reject")

    def _decide_mission(self, text, he2, mission, flags):
        """A planned mission flies only past the number guard and the echo guard."""
        missing = numbers_vs_mission(he2, mission)
        if not mission:
            return Decision("empty", text, he2=he2)
        if missing:
            flags.append(f"REJECT-numbers{missing}")
            return Decision(
                "reject",
                text,
                he2=he2,
                mission=mission,
                action="reject-numbers"
            )
        if is_shot_echo(he2, mission):
            return Decision(
                "reject",
                text,
                he2=he2,
                mission=mission,
                action="reject-planner-echo"
            )
        return Decision("mission", text, he2=he2, mission=mission, tag="planned")

    # --- the outcomes -----------------------------------------------------------------
    def _critical(self, kind):
        """The fast path: hand a critical command to control at once. -> Routed."""
        if kind == "emergency":
            text = outcome_text("emergency stop", self.control.emergency_halt())
        elif kind == "manual":
            text = outcome_text("manual", self.control.manual())
        else:
            self.control.auto()
            text = outcome_text("auto", None)

        return Routed("critical", f"{kind}: {text}", text)

    def _fly(self, mission, tag):
        """Send the mission through control. -> Routed. Any result but "sent" carries a
        text to SAY: the user must hear that it did not fly. In manual mode control
        refuses it (CONFLICT); perception still answers."""
        base = f"mission({len(mission)} steps, {tag})"
        status = self.control.fly(mission)
        if status is not None and status.is_success:
            return Routed("flight", base)

        say = outcome_text("mission", status)
        if status == HTTPStatus.CONFLICT:
            return Routed("flight", f"refused-manual {base}", say)
        if status is None:
            return Routed("flight", f"FAILED-unreachable {base}", say)
        return Routed("flight", f"FAILED-HTTP-{int(status)} {base}", say)

    def _vision(self, kind, target):
        """Hand a typed request to perception. -> Routed."""
        if kind == "clear":
            self.vision.clear()
            return Routed("vision", "perception(clear)")

        start = {
            "count": self.vision.count,
            "highlight": self.vision.highlight,
            "describe": self.vision.describe,
        }[kind]
        status, task = start(target)
        if status == TASK_FULL:
            say = (
                f"Too many vision tasks ({config.VISION_MAX_TASKS}). Clear one, "
                "or wait."
            )
            action = f"perception({kind}) refused: full"
            return Routed("vision", action, say, task, status)

        # a describe's target is the whole question: the label leaves it out
        label = "perception(describe)"
        if kind != "describe":
            label = f"perception({kind}: {target})"
        return Routed("vision", label, None, task, status)

    def _reject(self, text, action):
        self.observe(reject_reason=reject_why(action))
        return Routed("reject", action, REJECT_HE + text)


def plan_messages(he2):
    """The planner's request: its long system prompt, the example turns, the sentence."""
    msgs = [{"role": "system", "content": UNIFIED_PROMPT}]
    for user, answer in UNIFIED_SHOTS:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": answer})
    msgs.append({"role": "user", "content": he2})
    return msgs


def warm_up(gemma):
    """One plan request at start (owner L1), so the planner's prompt sits in Gemma's
    prompt cache before the first command. Its answer is dropped: nothing is sent."""
    gemma.request(
        plan_messages(config.PLAN_WARM_UP_SENTENCE),
        grammar=UNIFIED_GRAMMAR,
        max_tokens=PLAN_MAX_TOKENS,
        timeout_s=PLAN_TIMEOUT_S,
        label="warmup"
    )
    return

