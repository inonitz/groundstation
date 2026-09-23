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
VLM_TIMEOUT = _K.VLM_TIMEOUT_SECONDS
GEMMA_MODEL_PATH       = _K.GEMMA_MODEL_PATH          # gemma/server.py builds Gemma's command line from these
GEMMA_MMPROJ_PATH      = _K.GEMMA_MMPROJ_PATH
GEMMA_THINKING_ENABLED = _K.GEMMA_THINKING_ENABLED

# ============================== 3. Ears (ASR) =============================
ASR_TOPIC = os.environ.get("SCENE_ASR_TOPIC", _K.ASR_TRANSCRIBE_TOPIC)

# ============================ 4. Camera + window ==========================
INPUT        = _D.video_input(_D.VIDEO_SOURCE)   # derived from VIDEO=webcam|dji|rtmp; no SCENE_INPUT knob
CAM_W        = _K.CAMERA_REQUEST_WIDTH
CAM_H        = _K.CAMERA_REQUEST_HEIGHT
BOTTOM_H     = _K.BOTTOM_PANE_HEIGHT
STATUS_W     = _K.STATUS_PANE_WIDTH
HE_FONT_SIZE = _K.HE_FONT_SIZE
OPEN_TIMEOUT = float(os.environ.get("SCENE_OPEN_TIMEOUT", str(_K.INPUT_OPEN_TIMEOUT_SECONDS)))
READ_RETRY   = _K.INPUT_READ_RETRY_LIMIT

# ============================ 5. Overlay colours ==========================
COL_YOLOE_HL   = _K.COL_HIGHLIGHT          # vibrant green highlight (name kept; drawn by mvd)
COL_SAM2_HL    = _K.COL_MASK               # magenta mask
COL_HUD        = _K.COL_HUD
COL_STATUS_UP   = _K.COL_STATUS_UP
COL_STATUS_DOWN = _K.COL_STATUS_DOWN

# ============================ 6. Voice out (TTS) ==========================
TTS_BACKEND = os.environ.get("SCENE_TTS", _K.TTS_BACKEND)
TTS_HOST    = _D.TTS_HOST
TTS_PORT    = _K.TTS_PORT
TTS_LANG    = _K.TTS_LANGUAGE
TTS_RATE    = _D.TTS_RATE
TTS_TIMEOUT = _D.TTS_TIMEOUT
PHONIKUD_G2P    = _D.PHONIKUD_G2P
PHONIKUD_VOICE  = _D.PHONIKUD_VOICE
PHONIKUD_CONFIG = _D.PHONIKUD_CONFIG

# =============================== 7. Resolvers =============================
resolve_torch_device = _D.resolve_torch_device
default_gateway      = _D.default_gateway

# ============================ 8. Perception knobs =========================
# Env resolution lives here (moved out of mvd.py) so config is the single place. Consumers read config.X.
SEG          = os.environ.get("SCENE_SEG", _K.SEGMENTER)
SAM3_PERIOD  = float(os.environ.get("SCENE_SAM3_PERIOD", str(_K.SAM3_MIN_SECONDS_BETWEEN_FORWARDS)))
HL_GIVEUP    = float(os.environ.get("SCENE_HL_GIVEUP", str(_K.HIGHLIGHT_GIVEUP_SECONDS)))
GATE         = _D.HIGHLIGHT_PRESENCE_GATE
VERIFY       = _D.HIGHLIGHT_VERIFY            # on | off (default ON, 2026-09-20): related-noun verify on top of the gate
COUNT_FRAMES = int(os.environ.get("SCENE_COUNT_FRAMES", str(_K.COUNT_MEDIAN_FRAMES)))
COUNT_GAP    = float(os.environ.get("SCENE_COUNT_GAP", str(_K.COUNT_FRAME_GAP_SECONDS)))
MIN_BOX_FRAC = float(os.environ.get("SCENE_MIN_BOX_FRAC", str(_K.MIN_BOX_FRACTION_OF_FRAME)))
HL_TOPK      = int(os.environ.get("SCENE_HL_TOPK", str(_K.SAM3_MAX_BOXES_PER_QUERY)))
HL_MAX       = int(os.environ.get("SCENE_HL_MAX", str(_K.MAX_HIGHLIGHTS_DRAWN_PER_FRAME)))
DETECT_FLOOR = float(os.environ.get("SCENE_DETECT_FLOOR", str(_K.DETECTOR_QUERY_THRESHOLD)))
HL_CONF      = float(os.environ.get("SCENE_HL_CONF", str(_K.MIN_DRAW_CONFIDENCE)))
HL_REL       = _D.RELATIVE_CONFIDENCE_GATE
SUPERVISOR_MAX_RESTARTS   = _K.SUPERVISOR_MAX_RESTARTS
NATIVE_BIN_DIR      = _K.NATIVE_BIN_DIR
MOCK_WIRE_PORT      = _K.MOCK_WIRE_PORT
MOCK_APISERVER_PATH = _K.MOCK_APISERVER_PATH
PULSE_SERVER        = _K.PULSE_SERVER
PHONE_IP            = _D.PHONE_IP
SESSION_DIR         = _D.SESSION_DIR
CLIPS_DIR           = _D.CLIPS_DIR
RECORD_SESSION      = _D.RECORD_SESSION
ASR_CAPTURE_DEVICE  = _D.ASR_CAPTURE_DEVICE
SUPERVISOR_STABLE_SECONDS = _K.SUPERVISOR_STABLE_SECONDS
SERVICE_RETRY_SECONDS     = _K.SERVICE_RETRY_SECONDS
VISION_MAX_TASKS = _K.VISION_MAX_ACTIVE_TASKS   # a hardware-tuned constant, not an env knob (owner 2026-09-22)

# ============================ 9. Ports + channels =========================
LLAMA_SERVER_PORT = _K.LLAMA_SERVER_PORT          # bare Gemma port (recognizer/pipeline.py)
PHONE_ASR_PORT    = int(os.environ.get("MVD_PHONE_ASR_PORT", str(_K.PHONE_ASR_PORT)))
PHONE_ASR_ENABLED = os.environ.get("MVD_PHONE_ASR", "1" if _K.PHONE_ASR_ENABLED else "0") != "0"

# ============================ 10. Video stall guard =======================
WATCHDOG_STALL_SEC = float(os.environ.get("WATCHDOG_STALL_SEC", str(_K.WATCHDOG_STALL_SECONDS)))
WATCHDOG_RETRY_SEC = float(os.environ.get("WATCHDOG_RETRY_SEC", str(_K.WATCHDOG_RETRY_SECONDS)))

# ============================ 11. Scenario resolvers ======================

# ============================ 12. Ports, planner, wire, ASR ================
PLANNER        = "gemma4"                 # the only planner (MVD_PLANNER toggle deleted)
ASR_MODEL_PATH = _D.ASR_MODEL_PATH
ASR_BACKEND    = _D.ASR_BACKEND
ASR_LANGUAGE   = _D.ASR_LANGUAGE
# Live wire target: derived from ONE decision, CONTROL (mock|real), via wire_target above. DjiWire.from_env,
# the startup print and the HUD read WIRE_HOST/PORT/REAL. run.sh exports CONTROL (+ PHONE_IP); config derives.
WIRE_HOST, WIRE_PORT, WIRE_REAL = _D.wire_target(_D.CONTROL_TARGET)   # one decision: CONTROL=mock|real

# ============================ 13. SAM3 model identity =====================
SAM3_MODEL_DIR = _K.SAM3_MODEL_DIR   # single source: the SAM3 loader + the overlay label read this
SAM3_PRECISION = _K.SAM3_PRECISION   # nf4, fixed at load; no env override
