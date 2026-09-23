"""Operator kill switch (owner ruling 2026-09-08). ONE key press stops the aircraft and hands manual control back to
the RC; a latch then refuses every motion verb until the operator re-arms. Only a human presses it: the assistant
never sends /c/stop to a real aircraft (CLAUDE.md drone-safety rules).

  kill()  -> wire.stop() = POST /c/stop = controller.stop(emergency=true): stops motion AND relinquishes our
             virtual-stick authority (the RC flies). The running /c/fly mission is cancelled phone-side.
  latch   -> takeoff / land / fly_mission / spin_by / fly_by / gimbal_pitch / scan_ground / go_home_to_user /
             follow_me return LATCHED (409) and are NOT sent until rearm(). stop() stays allowed (direct /c/stop);
             halt() is ALSO refused after a kill -- it routes through the guarded fly_mission (a /c/fly that
             re-takes stick control), which the latch correctly prevents.
Wraps the wire INSTANCE, so every caller (router basic verbs, pipeline missions, recorders) is covered.
Live key (mvd window must have focus): M toggles -- first press kills, next press re-arms."""

from control.dji_wire import LATCHED, sent


class KillSwitch:
    # Every motion verb is refused after a kill. takeoff/land POST directly; the rest route through
    # fly_mission -- listed explicitly (not left to transitive coverage) so a future refactor cannot
    # silently unguard one. Do NOT shrink this to {takeoff,land,fly_mission}: a kill switch must not
    # depend on every verb continuing to call fly_mission.
    MOTION = ("takeoff", "land", "fly_mission", "spin_by", "fly_by", "gimbal_pitch",
              "scan_ground", "go_home_to_user", "follow_me", "track_me", "wave")

    def __init__(self, wire, say=print):
        self.wire, self.say = wire, say
        self.killed, self.refused, self.kills = False, 0, 0
        for name in self.MOTION:
            fn = getattr(wire, name, None)
            if fn is not None:
                setattr(wire, name, self._guard(name, fn))

    def _guard(self, name, fn):
        def guarded(*a, **k):
            if self.killed:
                self.refused += 1
                self.say(f"KILL latch: refused {name} -- press M to re-arm")
                return LATCHED
            return fn(*a, **k)
        guarded.__name__ = name
        return guarded

    def kill(self):
        """POST /c/stop and latch every motion verb. Reports the REAL result: when the stop did not reach the
        aircraft, say so, and tell the operator to take over with the RC or the power button."""
        self.killed = True   # plain bool, set from the key thread; the guard reads it under the GIL
        self.kills += 1
        code = self.wire.stop()
        if sent(code):
            self.say(f"KILL: /c/stop -> HTTP {code}. Motion stopped, the RC has control, missions refused until M is pressed again.")
        else:
            self.say(f"KILL FAILED: /c/stop -> HTTP {code}. The stop did NOT reach the aircraft. "
                     "Take over with the RC, or hold the aircraft power button. Missions stay refused.")
        return code

    def rearm(self):
        self.killed = False
        self.say("re-armed: missions allowed again")

    def toggle(self):
        """The M key: kill when armed, re-arm when killed. Returns True when the switch is now KILLED."""
        if self.killed:
            self.rearm()
        else:
            self.kill()
        return self.killed
