"""The command router: ASR transcript -> {emergency, override, resume, complex}.

  EMERGENCY  -> wire.halt() = POST /c/fly [{delay:0}] -- preempts current motion and KEEPS our
                control. NOT /c/stop. One-shot, no mode change.
  OVERRIDE   -> wire.stop() + switch to MANUAL (hand control to the RC).
  RESUME     -> switch back to AUTO.
  COMPLEX    -> hand the raw text to the Gemma recognizer (on_complex): it routes AND plans.

harden2 (2026-09-19): the deterministic BASIC verb path was retired -- command typing and mission
planning are the Gemma recognizer's job now (in Hebrew, directly). This dispatcher keeps only the
safety tiers. The auto/manual mode still lives here; the recognizer reads it (Pipeline.flight_allowed)
to gate flight while manual -- a mission is refused, perception still answers.
"""
from dataclasses import dataclass

from . import commands
from .commands import Tier


@dataclass
class Result:
    tier: Tier
    action: str          # what we did, for logs/tests
    dispatched: bool     # did it reach the wire / recognizer


class Router:
    def __init__(self, wire, on_complex=None):
        self.wire = wire
        self.on_complex = on_complex or (lambda text: None)
        self.mode = "auto"   # "auto" = ASR commands fly the drone; "manual" = RC has control

    def handle(self, text: str) -> Result:
        cmd = commands.classify(text)

        if cmd.tier is Tier.EMERGENCY:
            self.wire.halt()                       # delay:0 preempts current motion; NOT /c/stop. Keeps control.
            return Result(cmd.tier, "stop", True)  # NO mode change: the user keeps control after a stop.

        if cmd.tier is Tier.OVERRIDE:
            self.wire.stop()
            self.mode = "manual"
            return Result(cmd.tier, "override->manual", True)

        if cmd.tier is Tier.RESUME:
            self.mode = "auto"
            return Result(cmd.tier, "resume->auto", True)

        # COMPLEX -> the Gemma recognizer (routes + plans; it gates its own flight while manual).
        self.on_complex(cmd.text)
        return Result(cmd.tier, "complex->recognizer", True)
