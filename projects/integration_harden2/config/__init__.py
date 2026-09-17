"""harden2 config adapter. The app reads config through `import config; config.X`; this file is the
single import surface, but the VALUES live in the two merged config files:
  config_constants.py  — baked, decided values.
  config_defaults.py   — env-overridable defaults + the host-derived resolvers.
This file only maps those to the names the app uses and keeps the env overrides (so a launch can still
tune a knob). It imports no other app module, so it also loads from a bare script."""
import os
from . import constants as _K
from . import defaults as _D

# ROCm/MIOpen: fast kernel-search so the one-time GPU kernel compile at startup is short (harmless on
# non-AMD). Must be set before torch initializes the GPU.
os.environ.setdefault("MIOPEN_FIND_MODE", "2")

# ============================== 1. VLM brain ==============================
LLAMA_URL   = os.environ.get("SCENE_LLAMA_URL", "http://127.0.0.1:%d" % _K.LLAMA_SERVER_PORT)
VLM_TIMEOUT = _K.VLM_TIMEOUT_SECONDS

# =========================== 2. Eyes / detectors ==========================
# Background is OFF by decision (SCENE_BG=off); the guarded Eyes turns 'off' into no-YOLO. SAM2 + the
# omdet knobs remain for the (non-default) SCENE_SEG=omdet path.
BG_SEG_MODEL = os.environ.get("SCENE_BG",   "off")
CONF_BG      = float(os.environ.get("SCENE_CONF_BG", "0.35"))
DETECT_IMGSZ = int(os.environ.get("SCENE_IMGSZ", "640"))
DEVICE       = os.environ.get("SCENE_DEVICE", "")

# ============================== 3. Ears (ASR) =============================
ASR_TOPIC = os.environ.get("SCENE_ASR_TOPIC", _K.ASR_TRANSCRIBE_TOPIC)

# ============================ 4. Camera + window ==========================
INPUT        = os.environ.get("SCENE_INPUT", os.environ.get("SCENE_CAM", str(_D.WEBCAM_DEVICE_INDEX)))
CAM_W        = int(os.environ.get("SCENE_CAM_W", str(_K.CAMERA_REQUEST_WIDTH)))
CAM_H        = int(os.environ.get("SCENE_CAM_H", str(_K.CAMERA_REQUEST_HEIGHT)))
CHAT_W       = int(os.environ.get("SCENE_CHAT_W", str(_K.CHAT_PANE_WIDTH)))
HE_FONT_PATH = _D.resolve_he_font()
HE_FONT_SIZE = int(os.environ.get("SCENE_HE_FONT_SIZE", str(_K.HE_FONT_SIZE)))
OPEN_TIMEOUT = float(os.environ.get("SCENE_OPEN_TIMEOUT", str(_K.INPUT_OPEN_TIMEOUT_SECONDS)))
READ_RETRY   = int(os.environ.get("SCENE_READ_RETRY", str(_K.INPUT_READ_RETRY_LIMIT)))

# ============================ 5. Overlay colours ==========================
COL_BACKGROUND = _K.COL_BACKGROUND
COL_YOLOE_HL   = _K.COL_HIGHLIGHT          # vibrant green highlight (name kept; drawn by mvd)
COL_SAM2_HL    = _K.COL_MASK               # magenta mask
COL_HUD        = _K.COL_HUD
COL_CHAT_USER  = _K.COL_CHAT_USER
COL_CHAT_MODEL = _K.COL_CHAT_MODEL

# ============================ 6. Voice out (TTS) ==========================
TTS_BACKEND = os.environ.get("SCENE_TTS", _K.TTS_BACKEND)
TTS_HOST    = _D.TTS_HOST
TTS_PORT    = int(os.environ.get("SCENE_TTS_PORT", str(_K.TTS_PORT)))
TTS_LANG    = os.environ.get("SCENE_TTS_LANG", _K.TTS_LANGUAGE)
TTS_RATE    = _D.TTS_RATE
TTS_TIMEOUT = _D.TTS_TIMEOUT
TTS_MODEL     = _D.TTS_PIPER_MODEL
TTS_PIPER_BIN = _D.TTS_PIPER_BIN
TTS_SR        = _D.TTS_PIPER_SR
PHONIKUD_G2P    = _D.PHONIKUD_G2P
PHONIKUD_VOICE  = _D.PHONIKUD_VOICE
PHONIKUD_CONFIG = _D.PHONIKUD_CONFIG

# =============================== 7. Resolvers =============================
resolve_device       = _D.resolve_device
resolve_torch_device = _D.resolve_torch_device
default_gateway      = _D.default_gateway

# ============================ 8. Perception knobs =========================
# Env resolution lives here (moved out of mvd.py) so config is the single place. Consumers read config.X.
SEG          = os.environ.get("SCENE_SEG", _K.SEGMENTER)
SAM3_PERIOD  = float(os.environ.get("SCENE_SAM3_PERIOD", str(_K.SAM3_MIN_SECONDS_BETWEEN_FORWARDS)))
HL_GIVEUP    = float(os.environ.get("SCENE_HL_GIVEUP", str(_K.HIGHLIGHT_GIVEUP_SECONDS)))
GATE         = _D.HIGHLIGHT_PRESENCE_GATE
COUNT_FRAMES = int(os.environ.get("SCENE_COUNT_FRAMES", str(_K.COUNT_MEDIAN_FRAMES)))
COUNT_GAP    = float(os.environ.get("SCENE_COUNT_GAP", str(_K.COUNT_FRAME_GAP_SECONDS)))
MIN_BOX_FRAC = float(os.environ.get("SCENE_MIN_BOX_FRAC", str(_K.MIN_BOX_FRACTION_OF_FRAME)))
HL_TOPK      = int(os.environ.get("SCENE_HL_TOPK", str(_K.SAM3_MAX_BOXES_PER_QUERY)))
HL_MAX       = int(os.environ.get("SCENE_HL_MAX", str(_K.MAX_HIGHLIGHTS_DRAWN_PER_FRAME)))
DETECT_FLOOR = float(os.environ.get("SCENE_DETECT_FLOOR", str(_K.DETECTOR_QUERY_THRESHOLD)))
HL_CONF      = float(os.environ.get("SCENE_HL_CONF", str(_K.MIN_DRAW_CONFIDENCE)))
HL_REL       = _D.RELATIVE_CONFIDENCE_GATE

# ============================ 9. Ports + channels =========================
LLAMA_SERVER_PORT = _K.LLAMA_SERVER_PORT          # bare Gemma port (recognizer/pipeline.py)
PHONE_ASR_PORT    = int(os.environ.get("MVD_PHONE_ASR_PORT", str(_K.PHONE_ASR_PORT)))
PHONE_ASR_ENABLED = os.environ.get("MVD_PHONE_ASR", "1" if _K.PHONE_ASR_ENABLED else "0") != "0"
TTS_ENABLED       = _D.TTS_ENABLED

# ============================ 10. Video watchdog ==========================
WATCHDOG_STALL_SEC = float(os.environ.get("WATCHDOG_STALL_SEC", str(_K.WATCHDOG_STALL_SECONDS)))
WATCHDOG_RETRY_SEC = float(os.environ.get("WATCHDOG_RETRY_SEC", str(_K.WATCHDOG_RETRY_SECONDS)))

# ============================ 11. Scenario resolvers ======================
wire_target = _D.wire_target       # (host, port, is_real) for CONTROL=mock|real
video_input = _D.video_input       # the app's --source for VIDEO=webcam|dji
