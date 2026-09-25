"""harden2 config adapter. The app reads config through `import config; config.X`; this
file is the single import surface, but the VALUES live in two files:
  constants.py  -- fixed, decided values.
  defaults.py   -- env-overridable defaults + the host-derived resolvers: the ONE file
                   that reads the environment (owner ruling 2026-09-24).
This file only maps those to the names the app uses. It imports no other app module, so
it also loads from a bare script."""
from . import constants as _K
from . import defaults as _D

# ============================== 1. VLM brain ==============================
PLANNER           = "gemma4"            # the only planner (MVD_PLANNER toggle deleted)
VLM_TIMEOUT       = _K.VLM_TIMEOUT_SECONDS
LLAMA_SERVER_PORT = _K.LLAMA_SERVER_PORT   # the one Gemma server (gemma/)
# gemma/server.py builds Gemma's command line from these
GEMMA_MODEL_PATH       = _K.GEMMA_MODEL_PATH
GEMMA_MMPROJ_PATH      = _K.GEMMA_MMPROJ_PATH
GEMMA_THINKING_ENABLED = _K.GEMMA_THINKING_ENABLED

# ============================== 2. Speech in (ASR) ========================
ASR_SOURCES = _D.ASR_SOURCES   # speech in: every source runs, each feeds the recognizer
ASR_TOPIC   = _D.ASR_TOPIC
PHONE_ASR_PORT = _D.PHONE_ASR_PORT
# the ASR server's model and mic (escape hatches, see defaults.py)
ASR_MODEL_PATH     = _D.ASR_MODEL_PATH
ASR_BACKEND        = _D.ASR_BACKEND
ASR_LANGUAGE       = _D.ASR_LANGUAGE
ASR_CAPTURE_DEVICE = _D.ASR_CAPTURE_DEVICE

# ============================== 3. Voice out (TTS) ========================
TTS_OUTPUTS = _D.TTS_OUTPUTS   # speech out: every sentence goes to each output
TTS_LANG    = _K.TTS_LANGUAGE
TTS_RATE    = _D.TTS_RATE
PHONIKUD_G2P    = _D.PHONIKUD_G2P
PHONIKUD_VOICE  = _D.PHONIKUD_VOICE
PHONIKUD_CONFIG = _D.PHONIKUD_CONFIG

# ============================== 4. Operator keys ==========================
KEYBOARD_RAW_TOPIC = _K.KEYBOARD_RAW_TOPIC
KEY_ACTION_PRESSED = _K.KEY_ACTION_PRESSED
KILL_KEY_CODE      = _K.KILL_KEY_CODE
KILL_KEY_NAME      = _K.KILL_KEY_NAME
PUSH_TO_TALK_KEY_NAME = _K.PUSH_TO_TALK_KEY_NAME
PUSH_TO_TALK_KEY_CODE = _K.PUSH_TO_TALK_KEY_CODE

# ============================== 5. Camera + window ========================
# derived from VIDEO=webcam|dji|rtmp; no SCENE_INPUT knob
INPUT        = _D.video_input(_D.VIDEO_SOURCE)
WEBCAM_DEVICE_INDEX = _D.WEBCAM_DEVICE_INDEX   # [WEBCAM_DEV] the webcam a run opens
CAM_W        = _K.CAMERA_REQUEST_WIDTH
CAM_H        = _K.CAMERA_REQUEST_HEIGHT
BOTTOM_H     = _K.BOTTOM_PANE_HEIGHT
STATUS_W     = _K.STATUS_PANE_WIDTH
HE_FONT_SIZE = _K.HE_FONT_SIZE
OPEN_TIMEOUT = _D.OPEN_TIMEOUT
READ_RETRY   = _K.INPUT_READ_RETRY_LIMIT

# ============================== 6. Video stall guard ======================
WATCHDOG_STALL_SEC = _D.WATCHDOG_STALL_SEC
WATCHDOG_RETRY_SEC = _D.WATCHDOG_RETRY_SEC

# ============================== 7. Overlay colours ========================
COL_YOLOE_HL   = _K.COL_HIGHLIGHT          # the highlight box (old name kept)
COL_SAM2_HL    = _K.COL_MASK               # the highlight mask (old name kept)
COL_HUD        = _K.COL_HUD
COL_STATUS_UP   = _K.COL_STATUS_UP
COL_STATUS_WAITING = _K.COL_STATUS_WAITING
COL_STATUS_DOWN = _K.COL_STATUS_DOWN

# ============================== 8. Perception knobs =======================
SEG            = _D.SEGMENTER
SAM3_MODEL_DIR = _K.SAM3_MODEL_DIR   # single source for the SAM3 loader + overlay label
SAM3_PRECISION = _K.SAM3_PRECISION   # nf4, fixed at load; no env override
SAM3_PERIOD  = _D.SAM3_PERIOD
HL_GIVEUP    = _D.HL_GIVEUP
GATE         = _D.HIGHLIGHT_PRESENCE_GATE
# on | off (default ON, 2026-09-20): related-noun verify on top of the gate
VERIFY       = _D.HIGHLIGHT_VERIFY
COUNT_FRAMES = _D.COUNT_FRAMES
COUNT_GAP    = _D.COUNT_GAP
MIN_BOX_FRAC = _D.MIN_BOX_FRAC
HL_TOPK      = _D.HL_TOPK
HL_MAX       = _D.HL_MAX
DETECT_FLOOR = _D.DETECT_FLOOR
HL_CONF      = _D.HL_CONF
HL_REL       = _D.RELATIVE_CONFIDENCE_GATE
# a hardware-tuned constant, not an env knob (owner 2026-09-22)
VISION_MAX_TASKS = _K.VISION_MAX_ACTIVE_TASKS

# ============================== 9. Drone control target ===================
# Live phone-app target: derived from ONE decision, CONTROL (mock|real), via
# defaults.dji_target. DjiApp.from_env, the startup print and the HUD read
# DJI_HOST/PORT/REAL. run.sh exports CONTROL (+ PHONE_IP); config derives.
DJI_HOST, DJI_PORT, DJI_REAL = _D.dji_target(_D.CONTROL_TARGET)   # CONTROL=mock|real
PHONE_IP            = _D.PHONE_IP
MOCK_DJI_PORT       = _K.MOCK_DJI_PORT
MOCK_APISERVER_PATH = _K.MOCK_APISERVER_PATH

# ============================== 10. Process supervisor ====================
NATIVE_BIN_DIR            = _K.NATIVE_BIN_DIR
SUPERVISOR_MAX_RESTARTS   = _K.SUPERVISOR_MAX_RESTARTS
SUPERVISOR_STABLE_SECONDS = _K.SUPERVISOR_STABLE_SECONDS
WAITING_RETRY_SECONDS     = _K.WAITING_RETRY_SECONDS
PULSE_SERVER              = _D.PULSE_SERVER
TMUX_SESSION              = _D.TMUX_SESSION

# ============================== 11. Session + recording ===================
SESSIONS_ROOT  = _D.SESSIONS_ROOT       # every session folder lives under this
SESSION_DIR    = _D.SESSION_DIR
CLIPS_DIR      = _D.CLIPS_DIR
RECORD_SESSION = _D.RECORD_SESSION

# ============================== 12. Resolvers =============================
resolve_torch_device = _D.resolve_torch_device
default_gateway      = _D.default_gateway
