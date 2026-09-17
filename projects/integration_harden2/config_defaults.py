"""harden2 OVERRIDABLE settings — DRAFT (2026-09-10, completed 2026-09-11), not yet wired into the app.

Variables that HAVE a default but we change per run. Each reads an env var and falls back to the
default here, so there is one place to see and edit defaults, and a launch can still override any of
them without editing a script. Fixed values live in config_constants.py. Names describe intent; the
env keys in brackets are what you type at launch.
"""
import os, socket, subprocess, time
from config_constants import MOCK_WIRE_PORT, REAL_WIRE_PORT

def _default_route_ip():
    """The single device connected to the laptop = the WiFi hotspot gateway (the phone). Always derive
    it; never hardcode. Export PHONE_IP only to force a value."""
    try:
        for line in subprocess.run(["ip", "route"], capture_output=True, text=True).stdout.splitlines():
            if line.startswith("default"):
                return line.split()[2]
    except Exception:
        pass
    return None

# ── Run context (the handful you actually pass) ────────────────────────────────────────────
VIDEO_SOURCE        = os.environ.get("VIDEO", "webcam")        # [VIDEO]   webcam | dji
CONTROL_TARGET      = os.environ.get("CONTROL", "mock")        # [CONTROL] mock | real  (real = HUMAN-ONLY)
WEBCAM_DEVICE_INDEX = int(os.environ.get("WEBCAM_DEV", "0"))   # [WEBCAM_DEV] 0 = lid camera, 2 = C920
PHONE_IP            = os.environ.get("PHONE_IP") or _default_route_ip()   # [PHONE_IP] always derived; export to force

# ── Perception knobs we actually tune ───────────────────────────────────────────────────────
RELATIVE_CONFIDENCE_GATE = float(os.environ.get("SCENE_HL_REL", "0.65"))  # [SCENE_HL_REL] lower (0.45) for crowded scenes
HIGHLIGHT_PRESENCE_GATE  = os.environ.get("SCENE_GATE", "sam3")           # [SCENE_GATE] sam3 | either | vlm (default sam3)

# ── Speech (phone owns TTS; these are the tunables + the desk-debug fallbacks) ───────────────
TTS_ENABLED      = os.environ.get("MVD_TTS", "1") != "0"       # [MVD_TTS] phone TTS on; 0 to silence (desk tests)
TTS_HOST         = os.environ.get("SCENE_TTS_HOST", "")        # [SCENE_TTS_HOST] "" -> derive from video host / gateway
TTS_RATE         = float(os.environ.get("SCENE_TTS_RATE", "1.0"))     # [SCENE_TTS_RATE] POST /tts speech rate
TTS_TIMEOUT      = float(os.environ.get("SCENE_TTS_TIMEOUT", "3"))    # [SCENE_TTS_TIMEOUT] POST timeout (s)
TTS_PIPER_MODEL  = os.environ.get("SCENE_TTS_MODEL", "/root/models/tts/voices/en_US-lessac-medium.onnx")  # desk-debug only
TTS_PIPER_BIN    = os.environ.get("SCENE_TTS_PIPER_BIN", "/root/models/tts/piper/piper")                  # desk-debug only
TTS_PIPER_SR     = int(os.environ.get("SCENE_TTS_SR", "22050"))       # desk-debug piper raw sample rate
# Phonikud offline Hebrew TTS (SCENE_TTS=phonikud): G2P adds niqqud+stress -> IPA -> Piper onnx voice.
# Models are cc-nc (demo/competition use only); fetched by tools/devenv/install-runtime-deps.sh.
PHONIKUD_G2P     = os.environ.get("SCENE_PHONIKUD_G2P",    "/root/models/tts/phonikud/phonikud-1.0.int8.onnx")
PHONIKUD_VOICE   = os.environ.get("SCENE_PHONIKUD_VOICE",  "/root/models/tts/phonikud/model.onnx")
PHONIKUD_CONFIG  = os.environ.get("SCENE_PHONIKUD_CONFIG", "/root/models/tts/phonikud/model.config.json")

# ── ASR escape hatches (keep all; the restore-English / swap-model path) ──────────────────
ASR_MODEL_PATH     = os.environ.get("ASR_MODEL_PATH", "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin")
ASR_BACKEND        = os.environ.get("ASR_BACKEND", "whisper-whisper")     # [ASR_BACKEND]
ASR_LANGUAGE       = os.environ.get("ASR_LANGUAGE", "he")                 # [ASR_LANGUAGE]
ASR_CAPTURE_DEVICE = os.environ.get("ASR_CAPTUREID")                      # [ASR_CAPTUREID] None = default mic

# ── Recording + session (ONE root; clips and logs derive from it) ─────────────────────────
RECORD_SESSION = os.environ.get("RECORD", "1") != "0"         # [RECORD] record the whole session (utterances + clips)
_HERE          = os.path.dirname(os.path.abspath(__file__))
SESSIONS_ROOT  = os.environ.get("MVD_SESSIONS_ROOT", os.path.join(_HERE, "sessions"))   # [MVD_SESSIONS_ROOT]
SESSION_DIR    = os.environ.get("MVD_SESSION_DIR") or os.path.join(                      # [MVD_SESSION_DIR]
                     SESSIONS_ROOT, "session-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), socket.gethostname()))
CLIPS_DIR      = os.path.join(SESSION_DIR, "clips")           # derived from SESSION_DIR (was ASR_RECORD_DIR)
LOG_DIR        = os.environ.get("DESK_TEST_LOGDIR", SESSION_DIR)   # [DESK_TEST_LOGDIR] derived from SESSION_DIR

# Derived, NOT stored (functions; computed from the above so they can never drift):
def video_input(video_source=None):
    """The app's --source. webcam -> the webcam index as a string; dji -> "ros" (gstreamer_rx publishes
    camera/stream). Anything else is passed through (a file, URL, or pipeline)."""
    v = VIDEO_SOURCE if video_source is None else video_source
    if v == "webcam":
        return str(WEBCAM_DEVICE_INDEX)
    if v == "dji":
        return "ros"
    return v

def wire_target(control_target=None):
    """(host, port, is_real) for the control wire. mock -> 127.0.0.1:MOCK_WIRE_PORT, not real.
    real -> PHONE_IP:REAL_WIRE_PORT, real (HUMAN-ONLY). Routing is unconditional; CONTROL alone decides."""
    c = CONTROL_TARGET if control_target is None else control_target
    if c == "real":
        return (PHONE_IP, REAL_WIRE_PORT, True)
    return ("127.0.0.1", MOCK_WIRE_PORT, False)

# ── Host-derived resolvers (functions + the font path; computed per machine, never stored) ──
import os.path as _op

def resolve_device():
    """Best available compute device, vendor-neutral, CPU fallback, never raises. torch.cuda covers
    CUDA and ROCm/HIP; mps covers Apple. Override with SCENE_DEVICE."""
    dev = os.environ.get("SCENE_DEVICE", "")
    if dev:
        return dev
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"

def resolve_torch_device():
    """torch-style device ('cuda'/'mps'/'cpu'); ROCm reports as 'cuda' too."""
    d = resolve_device()
    return d if d in ("cpu", "mps") else "cuda"

def default_gateway():
    """The workstation's WIRELESS default-route gateway = the phone on its hotspot. Returns None when
    there is no wireless default route (callers MUST handle None; a literal 'None' in a command is a
    real bug we shipped once). One home for the lookup."""
    routes = []
    try:
        for line in open("/proc/net/route").readlines()[1:]:
            f = line.split()
            if len(f) > 2 and f[1] == "00000000":
                routes.append((f[0], ".".join(str(int(f[2][i:i + 2], 16)) for i in (6, 4, 2, 0))))
    except Exception:
        return None
    for iface, gw in routes:
        if os.path.isdir("/sys/class/net/" + iface + "/wireless"):
            return gw
    return None

def resolve_he_font():
    """A monospace font file that has Hebrew glyphs. DejaVuSansMono has NONE (renders boxes); FreeMono
    does. Override with SCENE_HE_FONT."""
    for c in (os.environ.get("SCENE_HE_FONT"),
              "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if c and _op.exists(c):
            return c
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
