"""One spoken turn, and the vision results that arrive later.

Turns: a transcript opens a log turn, goes to the recognizer (which routes it), and the
Routed result is shown and spoken. VisionSinks: perception2.vision reports each task's
result here; this is the one place that turns a vision result into chat lines, speech and
log records. Shared state is app.state.S."""
import time

from app.render import chat_kind
from app.state import S
from log.perf import NO_PERF
from log.session import SessionLog
from util.mission import step_text
from recognizer import reject_why
from perception2.vision import (
    HL_ABSENT,
    HL_CLEARED,
    HL_LOST,
    HL_NOT_READY,
    HL_TRACKING,
    TASK_FULL,
    TASK_OK,
    Sinks,
)

NOT_READY_HE = "המערכת עדיין לא מוכנה"    # "the system is not ready yet"


# ---- Chat helpers ----
def chat(role, text, kind):
    with S.lock:
        S.chat.append((role, text, kind))
    return


def show_record(rec):
    """Show what a turn did in the chat: its kind, its mission steps, its action, and a
    reject's reason. rec is the session's current record (None or empty: nothing)."""
    kind = None
    action = ""
    tag = ""

    if not rec:
        return

    kind = rec.get("kind")
    action = str(rec.get("action") or "")

    if kind:
        tag = "kind_hl" if kind == "highlight" else "kind_meta"
        chat("meta", str(kind), tag)

    # The first step is drawn as the head of the command list.
    for i, step in enumerate(rec.get("mission") or []):
        tag = "cmd_head" if i == 0 else "cmd"
        chat("cmd", f"{i}  " + step_text(step), tag)

    if action and not action.startswith("perception("):
        chat("meta", action, "action_meta")
    if action.startswith("reject") or kind == "reject":
        chat("model", reject_why(action), "reject")
    return


# ---- One spoken turn ----
class Turns:
    """@recognizer: recognizer.Recognizer. @say(text): chat + speech.
    @session: log.session.SessionLog."""

    def __init__(self, recognizer, say, session, perf=NO_PERF):
        self.recognizer = recognizer
        self.say = say
        self.session = session
        self._perf = perf
        return

    def __call__(self, text, source="mic"):
        # one utterance is one line: the ASR can put a line break inside a transcript
        text = " ".join((text or "").split())
        if not text:
            return

        # the mic's ASR time: from the push-to-talk release to this transcript
        asr_ms = self._perf.take_since("ptt_release") if source == "ros" else None
        if asr_ms is not None:
            self._perf.record("asr", asr_ms, chars=len(text))

        print("[app] you:", text, flush=True)
        chat("user", text, "user")
        self.session.begin(text, source)

        t0 = time.monotonic()
        routed = self.recognizer.handle(text)
        self._perf.record("turn", (time.monotonic() - t0) * 1000, kind=routed.kind)
        if routed.say:
            self.say(routed.say)
        if routed.vision_status == TASK_FULL:
            self.session.end_request(
                "refused: too many vision tasks",
                slot=routed.vision_task
            )

        self._record_turn()
        return

    def _record_turn(self):
        """Show what the turn did (kind, mission, action, a reject's reason) and commit
        the session record."""
        show_record(self.session.current())
        self.session.commit()
        return


# ---- Vision results (they arrive after the turn) ----
class VisionSinks:
    """The vision callbacks (perception2.vision.Sinks). @speak(text): speech only."""

    def __init__(self, session, speak):
        self.session = session
        self.speak = speak
        self._kinds = {}                   # task -> "count" | "highlight" | "describe"
        return

    def sinks(self):
        return Sinks(
            on_start=self.on_start,
            on_count=self.on_count,
            on_highlight=self.on_highlight,
            on_describe=self.on_describe,
            on_pass=self.on_pass
        )

    def on_start(self, task, kind, phrase):
        """On the turn's thread, before the task runs: open its log record in this
        turn."""
        self._kinds[task] = kind
        with S.lock:
            S.thinking = True
        self.session.begin_request(kind, phrase, query=f"{kind} {phrase}", slot=task)
        return

    def _not_ready(self, task, what):
        message = f'"{what}": SAM3 is not ready yet -- see the status pane, then retry'
        with S.lock:
            S.thinking = False
        chat("model", message, "miss")
        self.session.end_request({"not_ready": True}, slot=task)
        self.speak(NOT_READY_HE)
        return

    def on_count(self, task, status, n, phrase, counts):
        if status != TASK_OK:
            self._not_ready(task, phrase)
            return

        with S.lock:
            S.thinking = False
        chat("model", f"ספרתי {n}: {phrase}", "answer")
        print(f"[app] count '{phrase}' -> {n} (median of {counts})", flush=True)
        self.session.end_request({"n": n, "per_frame_counts": counts}, slot=task)
        if not n:
            self.speak("לא מצאתי")
            return
        self.speak(f"יש {n}")
        return

    def on_highlight(self, u):
        if u.state == HL_NOT_READY:
            self._not_ready(u.task, u.phrase)
            return

        if u.state == HL_TRACKING:
            with S.lock:
                S.thinking = False
                S.target = u.concepts
                S.hl_dets = u.dets
                S.hl_masks = u.masks
            if u.first and self._kinds.get(u.task) == "highlight":
                chat("model", f"Highlighting: {u.phrase}", "action")
                chat("meta", f"{u.concepts} · best {u.best:.2f} ✓", "sam3")
            return

        if u.state == HL_ABSENT:
            with S.lock:
                S.thinking = False
            chat("model", f'no "{u.concepts}" in view -- {u.reason}', "miss")
            self.session.end_request(
                {
                    "present": False,
                    "best_conf": round(u.best, 3),
                    "why": u.reason
                },
                slot=u.task
            )
            return

        # LOST or CLEARED: the drawing goes.
        with S.lock:
            S.target = None
            S.hl_dets = []
            S.hl_masks = []
        if u.state == HL_LOST:
            chat("model", f"לא מצאתי: {u.concepts}", "miss")
            self.session.end_request({"gave_up": True}, slot=u.task)
        elif u.state == HL_CLEARED:
            chat("model", "Cleared the highlight.", "scene")
            self.session.end_request("cleared", slot=u.task)
        self._kinds.pop(u.task, None)
        return

    def on_describe(self, task, ok, desc, spoken, frame):
        with S.lock:
            S.thinking = False
        if not ok:              # Gemma's state is on the status pane: no chat line
            self.session.end_request({"answer": None, "gemma": "failed"}, slot=task)
            return

        chat("model", desc, "scene")
        if spoken and spoken != desc:
            chat("spoken", spoken, "spoken")
        print("[app] scene:", desc, "|| spoken:", spoken, flush=True)
        self.session.save_pass(frame, {"answer": desc, "spoken": spoken}, slot=task)
        self.session.end_request({"answer": desc, "spoken": spoken}, slot=task)
        if spoken:
            self.speak(spoken)  # the screen shows both; speak the SHORT one
        return

    def on_pass(self, task, frame, dets, ms):
        self.session.save_pass(frame, SessionLog.det_payload(dets), ms, slot=task)
        return


# ---- Speech out ----
def say_with(voice):
    """-> say(text): one chat line (its kind from chat_kind) and the same text spoken."""
    def say(message):
        chat("model", message, chat_kind(message))
        print("[say]", message, flush=True)
        if voice is not None:
            voice.say(message)
        return
    return say
