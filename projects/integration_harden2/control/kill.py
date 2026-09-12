"""Operator kill switch (owner ruling 2026-09-08). ONE key press stops the aircraft and hands manual control back to
the RC; a latch then refuses every motion verb until the operator re-arms. Only a human presses it: the assistant
never sends /c/stop to a real aircraft (CLAUDE.md drone-safety rules).

  kill()  -> wire.stop() = POST /c/stop = controller.stop(emergency=true): stops motion AND relinquishes our
             virtual-stick authority (the RC flies). The running /c/fly mission is cancelled phone-side.
  latch   -> takeoff / land / fly_mission / spin_by / fly_by / gimbal_pitch / scan_ground / go_home_to_user /
             follow_me return REFUSED (409) and are NOT sent until rearm(). halt() and stop() stay allowed.
Wraps the wire INSTANCE, so every caller (router basic verbs, pipeline missions, recorders) is covered.
Live key (mvd window must have focus): M toggles -- first press kills, next press re-arms."""


class KillSwitch:
    MOTION = ("takeoff", "land", "fly_mission", "spin_by", "fly_by", "gimbal_pitch",
              "scan_ground", "go_home_to_user", "follow_me")
    REFUSED = 409

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
                return self.REFUSED
            return fn(*a, **k)
        guarded.__name__ = name
        return guarded

    def kill(self):
        self.killed = True; self.kills += 1
        code = self.wire.stop()
        self.say(f"KILL: /c/stop -> HTTP {code}. Motion stopped, the RC has control, missions refused until M is pressed again.")
        return code

    def rearm(self):
        self.killed = False
        self.say("re-armed: missions allowed again")

    def toggle(self):
        """The M key: kill when armed, re-arm when killed. Returns True when the switch is now KILLED."""
        if self.killed: self.rearm()
        else: self.kill()
        return self.killed
