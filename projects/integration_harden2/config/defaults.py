"""harden2 OVERRIDABLE settings — the live default source (config/__init__.py imports this).

Variables that HAVE a default but we change per run. Each reads an env var and falls back to the
default here, so there is one place to see and edit defaults, and a launch can still override any of
them without editing a script. Fixed values live in config_constants.py. Names describe intent; the
env keys in brackets are what you type at launch.
"""
import os, socket, time
from .constants import MOCK_WIRE_PORT, REAL_WIRE_PORT

# ── Run context (the handful you actually pass) ────────────────────────────────────────────
VIDEO_SOURCE        = os.environ.get("VIDEO", "webcam")        # [VIDEO]   webcam | dji
CONTROL_TARGET      = os.environ.get("CONTROL", "mock")        # [CONTROL] mock | real  (real = HUMAN-ONLY)
WEBCAM_DEVICE_INDEX = int(os.environ.get("WEBCAM_DEV", "0"))   # [WEBCAM_DEV] 0 = lid camera, 2 = C920

# ── Perception knobs we actually tune ───────────────────────────────────────────────────────
RELATIVE_CONFIDENCE_GATE = float(os.environ.get("SCENE_HL_REL", "0.65"))  # [SCENE_HL_REL] lower (0.45) for crowded scenes
HIGHLIGHT_PRESENCE_GATE  = os.environ.get("SCENE_GATE", "sam3")           # [SCENE_GATE] sam3 | either | vlm (default sam3)
HIGHLIGHT_VERIFY         = os.environ.get("SCENE_VERIFY", "on")          # [SCENE_VERIFY] on | off: split-and-verify related nouns (perception2/verify.py); default ON (2026-09-20 ruling)

# ── Speech (phone owns TTS; these are the tunables + the desk-debug fallbacks) ───────────────
TTS_HOST         = ""        # always derived from the phone/video host (tts_io); not an env knob
TTS_RATE         = 1.0     # POST /tts speech rate; fixed
TTS_TIMEOUT      = 3.0    # POST timeout (s); fixed
# Phonikud offline Hebrew TTS (SCENE_TTS=phonikud): G2P adds niqqud+stress -> IPA -> Piper onnx voice.
# Models are cc-nc (demo/competition use only); fetched by tools/devenv/install-runtime-deps.sh.
PHONIKUD_G2P     = "/root/models/tts/phonikud/phonikud-1.0.int8.onnx"
PHONIKUD_VOICE   = "/root/models/tts/phonikud/model.onnx"
PHONIKUD_CONFIG  = "/root/models/tts/phonikud/model.config.json"

# ── ASR escape hatches (keep all; the restore-English / swap-model path) ──────────────────
ASR_MODEL_PATH     = os.environ.get("ASR_MODEL_PATH", "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin")
ASR_BACKEND        = os.environ.get("ASR_BACKEND", "whisper-whisper")     # [ASR_BACKEND]
ASR_LANGUAGE       = os.environ.get("ASR_LANGUAGE", "he")                 # [ASR_LANGUAGE]
ASR_CAPTURE_DEVICE = os.environ.get("ASR_CAPTUREID")                      # [ASR_CAPTUREID] None = default mic

# ── Recording + session (ONE root; clips and logs derive from it) ─────────────────────────
RECORD_SESSION = os.environ.get("RECORD", "1") != "0"         # [RECORD] record the whole session (utterances + clips)
_HERE          = os.path.dirname(os.path.abspath(__file__))
SESSIONS_ROOT  = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "logs", "sessions"))   # <repo>/logs/sessions (config/ is 3 deep)
SESSION_DIR    = os.environ.get("MVD_SESSION_DIR") or os.path.join(                      # [MVD_SESSION_DIR]
                     SESSIONS_ROOT, "session-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), socket.gethostname()))
CLIPS_DIR      = os.path.join(SESSION_DIR, "asr_clips")       # derived from SESSION_DIR; the ASR server records here, session_log reads it
LOG_DIR        = SESSION_DIR   # fixed: derived from SESSION_DIR

# Derived, NOT stored (functions; computed from the above so they can never drift):
def video_input(video_source=None):
    """The app's --source. webcam -> the webcam index as a string; dji -> "ros" (gstreamer_rx publishes
    camera/stream). Anything else is passed through (a file, URL, or pipeline)."""
    v = VIDEO_SOURCE if video_source is None else video_source
    if v == "webcam":
        return str(WEBCAM_DEVICE_INDEX)
    if v == "dji":
        return "ros"
    if v in ("rtmp", "drone"):
        return "rtsp://127.0.0.1:8554/live"
    return v

def wire_target(control_target=None):
    """(host, port, is_real) for the control wire. mock -> 127.0.0.1:MOCK_WIRE_PORT, not real.
    real -> PHONE_IP:REAL_WIRE_PORT, real (HUMAN-ONLY). Routing is unconditional; CONTROL alone decides."""
    c = CONTROL_TARGET if control_target is None else control_target
    if c == "real":
        return (PHONE_IP, REAL_WIRE_PORT, True)
    return ("127.0.0.1", MOCK_WIRE_PORT, False)

# ── Host-derived resolvers (functions; computed per machine, never stored) ──

def resolve_device():
    """Best available compute device, vendor-neutral, CPU fallback, never raises. torch.cuda covers
    CUDA and ROCm/HIP; mps covers Apple. Override with SCENE_DEVICE."""
    dev = os.environ.get("SCENE_DEVICE", "")
    if dev:
        return dev
    import torch   # a hard dependency here; a missing torch is a real failure, not a silent cpu fallback
    if torch.cuda.is_available():
        return "0"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"

def resolve_torch_device():
    """torch-style device ('cuda'/'mps'/'cpu'); ROCm reports as 'cuda' too."""
    d = resolve_device()
    return d if d in ("cpu", "mps") else "cuda"

def default_gateway():
    """The workstation's WIRELESS default-route gateway = the phone on its hotspot. Returns None when
    there is no wireless default route (callers MUST handle None; a literal 'None' in a command is a
    real bug we shipped once). One home for the lookup."""
    if not os.path.exists("/proc/net/route"):   # no proc route table -> no gateway
        return None
    routes = []
    with open("/proc/net/route") as route_file:
        lines = route_file.readlines()[1:]
    for line in lines:
        fields = line.split()
        if len(fields) > 2 and fields[1] == "00000000":
            routes.append((fields[0], ".".join(str(int(fields[2][i:i + 2], 16)) for i in (6, 4, 2, 0))))
    for iface, gw in routes:
        if os.path.isdir("/sys/class/net/" + iface + "/wireless"):
            return gw
    return None

PHONE_IP = os.environ.get("PHONE_IP") or default_gateway()   # [PHONE_IP] the phone = the WIRELESS gateway; export to force (review R15)


