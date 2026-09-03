"""The 4-tier command router: ASR transcript -> {emergency, override, basic verb, complex}.

  Tier 4  EMERGENCY  -> wire.halt() = POST /c/fly [{delay:0}] -- preempts current motion (fly cancels
                        the running mission) and KEEPS our control. NOT /c/stop. One-shot, no mode change.
  Tier 3  OVERRIDE   -> wire.stop() + switch to MANUAL (hand control to the RC; ASR verbs ignored).
          RESUME     -> switch back to AUTO. Next mission verb (/c/fly) re-takes stick authority.
  Tier 1  BASIC      -> bounded deterministic verb on the wire (no LLM)
  Tier 2  COMPLEX    -> hand the raw text to the perception engine (answers; does NOT fly)

The LLM/VLM never reaches this dispatcher -- only deterministic verbs move the drone.
"""
from dataclasses import dataclass

from . import commands
from .commands import Tier

# Conservative indoor envelope: the Router() defaults, and their only consumer. They used to live in
# dji_wire.py, which never read them itself.
# NOTE: indoors the drone's VPS often refuses lateral/vertical motion (see docs/NOTES /
# indoor-vps-denial); yaw + slow vertical are the reliable axes.
DEFAULT_SPEED_MPS = 0.5      # m/s, well under the app's kDjiMaxSpeedMps=2.0
DEFAULT_YAW_DEG_S = 45.0     # deg/s -- the app reads ANGULAR_VELOCITY in degrees, not rad
DEFAULT_NUDGE_S = 1.5        # seconds of bounded motion per verb


# Unit direction per verb, scaled at dispatch. Body-frame: vx fwd+, vy right+, vz up+.
_FLYBY = {          # directional verbs -> native relative move (POST /c/fly fly_by). x+ fwd, y+ right, z+ up.
    "go_forward":  (1.0, 0.0, 0.0),
    "go_backward": (-1.0, 0.0, 0.0),
    "go_right":    (0.0, 1.0, 0.0),
    "go_left":     (0.0, -1.0, 0.0),
    "go_up":       (0.0, 0.0, 1.0),
    "go_down":     (0.0, 0.0, -1.0),
}


@dataclass
class Result:
    tier: Tier
    action: str          # what we did, for logs/tests
    dispatched: bool     # did it reach the wire / perception


class Router:
    def __init__(self, wire, on_complex=None,
                 speed=DEFAULT_SPEED_MPS, yaw_rate=DEFAULT_YAW_DEG_S, nudge_s=DEFAULT_NUDGE_S,
                 spin_deg=360.0, move_m=1.0, move_vel=2.0):
        self.wire = wire
        self.on_complex = on_complex or (lambda text: None)
        self.speed = speed
        self.yaw_rate = yaw_rate
        self.nudge_s = nudge_s
        self.spin_deg = spin_deg      # 'spin' = a full turn via native SpinBy
        self.move_m = move_m          # directional verbs = fly_by this many metres (tunable)
        self.move_vel = move_vel      # fly_by velocity (m/s)
        self.mode = "auto"   # "auto" = ASR verbs fly the drone; "manual" = RC has control

    def handle(self, text: str) -> Result:
        cmd = commands.classify(text)

        if cmd.tier is Tier.EMERGENCY:
            self.wire.halt()                       # delay:0 preempts current motion; NOT /c/stop. Keeps control.
            return Result(cmd.tier, "stop", True)  # NO mode change: the user keeps ASR control after a stop.

        if cmd.tier is Tier.OVERRIDE:
            self.wire.stop()
            self.mode = "manual"
            return Result(cmd.tier, "override->manual", True)

        if cmd.tier is Tier.RESUME:
            self.mode = "auto"
            return Result(cmd.tier, "resume->auto", True)

        if cmd.tier is Tier.BASIC:
            if cmd.name == "unknown_move":            # movement intent, no direction -> no-op + feedback
                return Result(cmd.tier, "didn't catch a direction -- try 'go forward/up/left'", False)
            if self.mode == "manual":
                # RC has authority; swallow ASR verbs until "resume".
                return Result(cmd.tier, f"ignored:{cmd.name}(manual)", False)
            self._dispatch_basic(cmd.name, cmd.param)
            action = cmd.name + (f" {cmd.param}" if cmd.param else "")
            return Result(cmd.tier, action, True)

        # COMPLEX -> perception engine (answers on the laptop; makes no flight decision)
        self.on_complex(cmd.text)
        return Result(cmd.tier, "complex->perception", True)

    def _dispatch_basic(self, name: str, param: str = ""):
        if name == "takeoff":
            self.wire.takeoff()
        elif name == "land":
            self.wire.land()
        elif name == "spin":
            self.wire.spin_by(self.spin_deg)      # native precise-angle turn (POST /c/fly spin_by)
        elif name == "rotate":
            try: deg = int(param)
            except (TypeError, ValueError): deg = 90
            self.wire.spin_by(float(deg))         # +CW / -CCW, exact angle via SpinBy
        elif name == "scan":
            self.wire.scan_ground(facing="OUTWARDS")   # orbit facing OUT (survey the surroundings)
        elif name == "search":
            self.wire.scan_ground(facing="INWARDS")    # orbit facing IN (search a central point)
        elif name == "track":
            self.wire.track_me()                       # camera-track the user's phone GPS
        elif name == "follow":
            self.wire.follow_me()                      # fly-follow the user's phone GPS
        elif name == "come_home":
            self.wire.go_home_to_user()                # return to the user's phone GPS
        elif name == "wave":
            self.wire.wave()                           # gimbal bob greeting (hello / how are you)
        elif name == "gimbal_forward":
            self.wire.gimbal_pitch(0.0)                # camera to the horizon
        elif name == "gimbal_down":
            self.wire.gimbal_pitch(-60.0)              # camera down 60 (not the full -90)
        elif name == "gimbal_up":
            self.wire.gimbal_pitch(30.0)               # camera up ~30 (physical max)
        elif name in _FLYBY:
            dx, dy, dz = _FLYBY[name]
            self.wire.fly_by(dx=dx * self.move_m, dy=dy * self.move_m,
                             dz=dz * self.move_m, velocity=self.move_vel)
        else:
            raise ValueError(f"unmapped basic verb: {name!r}")
