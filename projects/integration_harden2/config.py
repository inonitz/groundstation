"""harden2 config adapter. The app reads config through `import config; config.X`; this file is the
single import surface, but the VALUES live in the two merged config files:
  config_constants.py  — baked, decided values.
  config_defaults.py   — env-overridable defaults + the host-derived resolvers.
This file only maps those to the names the app uses and keeps the env overrides (so a launch can still
tune a knob). It imports no other app module, so it also loads from a bare script."""
import os
import config_constants as _K
import config_defaults as _D

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

# =============================== 7. Resolvers =============================
resolve_device       = _D.resolve_device
resolve_torch_device = _D.resolve_torch_device
default_gateway      = _D.default_gateway
