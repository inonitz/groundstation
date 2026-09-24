"""harden2 OVERRIDABLE settings: the ONE file that reads the environment (owner ruling
2026-09-24). config/__init__.py imports this.

Each setting reads an env var and falls back to its default, so there is one place to
see and edit defaults, and a launch can still override any of them without editing a
script. Fixed values live in constants.py. Names describe intent; the env keys in
brackets are what you type at launch.
"""
import os
import socket
import time

from . import constants as _K
from .constants import MOCK_DJI_PORT, REAL_DJI_PORT

# ROCm/MIOpen: fast kernel-search so the one-time GPU kernel compile at startup is short
# (harmless on non-AMD). Must be set before torch starts the GPU: config loads first.
os.environ.setdefault("MIOPEN_FIND_MODE", "2")


def _float(key, default):
    """An env override read as a float, else the default."""
    return float(os.environ.get(key, str(default)))


def _int(key, default):
    """An env override read as an int, else the default."""
    return int(os.environ.get(key, str(default)))


# ---- Run context (the handful you actually pass) ----
VIDEO_SOURCE        = os.environ.get("VIDEO", "webcam")        # [VIDEO]   webcam | dji
# [CONTROL] mock | real  (real = HUMAN-ONLY)
CONTROL_TARGET      = os.environ.get("CONTROL", "mock")
# [WEBCAM_DEV] 0 = lid camera, 2 = C920
WEBCAM_DEVICE_INDEX = int(os.environ.get("WEBCAM_DEV", "0"))

# ---- Perception knobs we actually tune ----
# [SCENE_HL_REL] lower (0.45) for crowded scenes
RELATIVE_CONFIDENCE_GATE = float(os.environ.get("SCENE_HL_REL", "0.65"))
SEGMENTER    = os.environ.get("SCENE_SEG", _K.SEGMENTER)                # [SCENE_SEG]
# [SCENE_SAM3_PERIOD] seconds between the starts of two highlight detects
SAM3_PERIOD  = _float("SCENE_SAM3_PERIOD", _K.SAM3_MIN_SECONDS_BETWEEN_FORWARDS)
# [SCENE_HL_GIVEUP] a highlight that finds nothing this long ends as lost
HL_GIVEUP    = _float("SCENE_HL_GIVEUP", _K.HIGHLIGHT_GIVEUP_SECONDS)
# [SCENE_COUNT_FRAMES] [SCENE_COUNT_GAP] the frames a count takes its median over
COUNT_FRAMES = _int("SCENE_COUNT_FRAMES", _K.COUNT_MEDIAN_FRAMES)
COUNT_GAP    = _float("SCENE_COUNT_GAP", _K.COUNT_FRAME_GAP_SECONDS)
MIN_BOX_FRAC = _float("SCENE_MIN_BOX_FRAC", _K.MIN_BOX_FRACTION_OF_FRAME)
HL_TOPK      = _int("SCENE_HL_TOPK", _K.SAM3_MAX_BOXES_PER_QUERY)     # [SCENE_HL_TOPK]
HL_MAX       = _int("SCENE_HL_MAX", _K.MAX_HIGHLIGHTS_DRAWN_PER_FRAME)  # [SCENE_HL_MAX]
DETECT_FLOOR = _float("SCENE_DETECT_FLOOR", _K.DETECTOR_QUERY_THRESHOLD)
HL_CONF      = _float("SCENE_HL_CONF", _K.MIN_DRAW_CONFIDENCE)        # [SCENE_HL_CONF]

# ---- Camera + video stall guard ----
OPEN_TIMEOUT       = _float("SCENE_OPEN_TIMEOUT", _K.INPUT_OPEN_TIMEOUT_SECONDS)
WATCHDOG_STALL_SEC = _float("WATCHDOG_STALL_SEC", _K.WATCHDOG_STALL_SECONDS)
WATCHDOG_RETRY_SEC = _float("WATCHDOG_RETRY_SEC", _K.WATCHDOG_RETRY_SECONDS)
# [SCENE_GATE] sam3 | either | vlm (default sam3)
HIGHLIGHT_PRESENCE_GATE  = os.environ.get("SCENE_GATE", "sam3")
# [SCENE_VERIFY] on | off: split-and-verify related nouns (perception2/verify.py);
# default ON (2026-09-20 ruling)
HIGHLIGHT_VERIFY         = os.environ.get("SCENE_VERIFY", "on")

# ---- Speech (phone owns TTS; these are the tunables + the desk-debug fallbacks) ----
TTS_RATE         = 1.0     # POST /tts speech rate; fixed
# Speech in and out: LISTS, all run at once (owner ruling 2026-09-23). Comma-separated.
# [ASR_SOURCES] ros = the laptop mic through our ASR server,
#               phone = the phone app's speech
ASR_SOURCES = [s for s in os.environ.get("ASR_SOURCES", "ros,phone").split(",") if s]
# [TTS_OUTPUTS] phone = the phone app's /tts, laptop = offline phonikud; "" = silent
TTS_OUTPUTS = [s for s in os.environ.get("TTS_OUTPUTS", "phone").split(",") if s]
# Phonikud offline Hebrew TTS (TTS_OUTPUTS=laptop): G2P adds niqqud+stress -> IPA ->
# Piper onnx voice. Models are cc-nc (demo/competition use only); fetched by
# tools/devenv/install-runtime-deps.sh.
PHONIKUD_G2P     = "/root/models/tts/phonikud/phonikud-1.0.int8.onnx"
PHONIKUD_VOICE   = "/root/models/tts/phonikud/model.onnx"
PHONIKUD_CONFIG  = "/root/models/tts/phonikud/model.config.json"

# ---- ASR escape hatches (keep all; the restore-English / swap-model path) ----
ASR_MODEL_PATH     = os.environ.get(
    "ASR_MODEL_PATH",
    "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin"
)
ASR_BACKEND        = os.environ.get("ASR_BACKEND", "whisper-whisper")  # [ASR_BACKEND]
ASR_LANGUAGE       = os.environ.get("ASR_LANGUAGE", "he")               # [ASR_LANGUAGE]
# [ASR_CAPTUREID] None = default mic
ASR_CAPTURE_DEVICE = os.environ.get("ASR_CAPTUREID")
ASR_TOPIC      = os.environ.get("SCENE_ASR_TOPIC", _K.ASR_TRANSCRIBE_TOPIC)
PHONE_ASR_PORT = _int("MVD_PHONE_ASR_PORT", _K.PHONE_ASR_PORT)   # [MVD_PHONE_ASR_PORT]
# [PULSE_SERVER] the host sound server the ASR server records from
PULSE_SERVER   = os.environ.get("PULSE_SERVER", _K.PULSE_SERVER)

# ---- Launch context ----
# [SCENE_TMUX_SESSION] set by run.sh: quitting the app tears this tmux session down
TMUX_SESSION = os.environ.get("SCENE_TMUX_SESSION", "")
# OpenCV reads its RTSP transport from the environment: TCP, not UDP, for a stream
# source (set here, before any capture opens).
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

# ---- Recording + session (ONE root; clips derive from it) ----
# [RECORD] record the whole session (utterances + clips)
RECORD_SESSION = os.environ.get("RECORD", "1") != "0"
_HERE          = os.path.dirname(os.path.abspath(__file__))
# <repo>/logs/sessions (config/ is 3 deep)
SESSIONS_ROOT  = os.path.abspath(
    os.path.join(_HERE, "..", "..", "..", "logs", "sessions")
)
# [MVD_SESSION_DIR]
SESSION_DIR    = os.environ.get("MVD_SESSION_DIR") or os.path.join(
    SESSIONS_ROOT,
    "session-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), socket.gethostname())
)
# derived from SESSION_DIR; the ASR server records here, log/session.py reads it
CLIPS_DIR      = os.path.join(SESSION_DIR, "asr_clips")


# ---- Derived, NOT stored (computed from the above so they can never drift) ----
def video_input(video_source=None):
    """The app's --source. webcam -> the webcam index as a string;
    dji -> "ros" (gstreamer_rx publishes camera/stream). Anything
    else is passed through (a file, URL, or pipeline)."""
    v = VIDEO_SOURCE if video_source is None else video_source
    if v == "webcam":
        return str(WEBCAM_DEVICE_INDEX)
    if v == "dji":
        return "ros"
    if v in ("rtmp", "drone"):
        return "rtsp://127.0.0.1:8554/live"
    return v


def dji_target(control_target=None):
    """(host, port, is_real) for the phone app. mock -> 127.0.0.1:MOCK_DJI_PORT, not
    real. real -> PHONE_IP:REAL_DJI_PORT, real (HUMAN-ONLY). Routing is unconditional;
    CONTROL alone decides."""
    c = CONTROL_TARGET if control_target is None else control_target
    if c == "real":
        return (PHONE_IP, REAL_DJI_PORT, True)
    return ("127.0.0.1", MOCK_DJI_PORT, False)


# ---- Host-derived resolvers (computed per machine, never stored) ----
def resolve_device():
    """Best available compute device, vendor-neutral, CPU fallback, never raises.
    torch.cuda covers CUDA and ROCm/HIP; mps covers Apple. Override with SCENE_DEVICE."""
    dev = os.environ.get("SCENE_DEVICE", "")
    if dev:
        return dev

    # a hard dependency; a missing torch is a real failure, not a silent cpu fallback.
    # Imported here, not at the top, so config still loads without torch.
    import torch
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


def _route_hex_to_ip(hex_addr):
    """/proc/net/route stores an IPv4 address as 8 hex digits, least significant byte
    first: read the byte pairs from the end."""
    return ".".join(str(int(hex_addr[i:i + 2], 16)) for i in (6, 4, 2, 0))


def default_gateway():
    """The workstation's WIRELESS default-route gateway = the phone
    on its hotspot. Returns None when there is no wireless default
    route (callers MUST handle None; a literal 'None' in a command
    is a real bug we shipped once). One home for the lookup."""
    routes = []
    fields = []

    if not os.path.exists("/proc/net/route"):   # no proc route table -> no gateway
        return None

    with open("/proc/net/route") as route_file:
        lines = route_file.readlines()[1:]

    # Collect every default route (destination 00000000) as (interface, gateway).
    for line in lines:
        fields = line.split()
        if len(fields) <= 2 or fields[1] != "00000000":
            continue
        routes.append((fields[0], _route_hex_to_ip(fields[2])))

    # The phone is the gateway of the wireless interface, not of a wired one.
    for iface, gw in routes:
        if os.path.isdir("/sys/class/net/" + iface + "/wireless"):
            return gw
    return None


# Last: it calls default_gateway above.
# [PHONE_IP] the phone = the WIRELESS gateway; export to force (review R15)
PHONE_IP = os.environ.get("PHONE_IP") or default_gateway()
