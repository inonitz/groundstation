"""harden2 FIXED constants: decided values that do not change between runs (read
through config/__init__.py). One place, by category, readable at a glance. Names
describe intent. Anything you change per run is in config/defaults.py, the one file
that reads the environment.

The phone-app target is derived from CONTROL (mock|real) in defaults.dji_target;
DjiApp's loopback guard is the mock/real gate.
"""
import os as _os

# Paths below are built from the repo root (config/ is 3 deep).
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".."))

# ---- VLM brain: Gemma 4 E4B only ----
GEMMA_DIR              = "/root/models/vlm/Gemma-4-E4B"
GEMMA_MODEL_PATH       = GEMMA_DIR + "/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
GEMMA_MMPROJ_PATH      = GEMMA_DIR + "/mmproj-BF16.gguf"
GEMMA_THINKING_ENABLED = False        # thinking OFF (decided)
VLM_TIMEOUT_SECONDS    = 30           # a warm 4B describe call is ~1-3 s
LLAMA_SERVER_PORT      = 18090        # the Gemma server

# ---- Speech in and out ----
# ROS2 topic the asr_node publishes to (we subscribe)
ASR_TRANSCRIBE_TOPIC = "/asr_server/transcribe"
PHONE_ASR_PORT       = 8080           # phone speech channel
TTS_LANGUAGE         = "he"           # phone answers in Hebrew

# ---- Operator keys ----
# Global: the llm_to_action keyboard hook reads /dev/input in every window.
# the hook publishes [evdev key code, action] (Int32MultiArray)
KEYBOARD_RAW_TOPIC = "/keyboard/in/raw"
# evdev EV_KEY value: 0 release, 1 press, 2 auto-repeat
KEY_ACTION_PRESSED = 1
# evdev KEY_F4. A function key, never a letter: letters are typed in other windows
# (owner 2026-09-23).
KILL_KEY_CODE      = 62
KILL_KEY_NAME      = "F4"
# shown on screen; the binding itself is compiled into the asr_node
# (llm_to_action asr_node.hpp kPushToTalkKeyBind)
PUSH_TO_TALK_KEY_NAME = "F5"

# ---- Camera + on-screen UI (fixed geometry) ----
# requested webcam width (falls to nearest supported)
CAMERA_REQUEST_WIDTH  = 1280
CAMERA_REQUEST_HEIGHT = 720           # requested webcam height
# the band under the camera: status | chat (owner 2026-09-22)
BOTTOM_PANE_HEIGHT    = 300
STATUS_PANE_WIDTH     = 300           # system status pane, right of the chat pane (px)
HE_FONT_SIZE          = 17            # Hebrew overlay glyph size
INPUT_OPEN_TIMEOUT_SECONDS = 180.0    # keep retrying a not-yet-live input this long
# consecutive read failures tolerated (network jitter)
INPUT_READ_RETRY_LIMIT     = 150

# ---- Video stall guard (video/video.py) ----
WATCHDOG_STALL_SECONDS = 6.0          # no new frame for this long -> stalled
WATCHDOG_RETRY_SECONDS = 15.0         # seconds between gstreamer restarts

# ---- On-screen overlay colours (BGR; fixed) ----
COL_HIGHLIGHT  = ( 60, 220,  60)   # green  : a highlight box (SAM3)
COL_MASK       = (220,  60, 220)   # magenta: a highlight mask (SAM3)
COL_HUD        = (255, 255,   0)   # cyan   : fps / status line (BGR; #00ffff)
COL_STATUS_UP   = ( 80, 200,  80)  # green  : a system that is UP
# orange: WAITING, the user must fix it (owner 2026-09-23)
COL_STATUS_WAITING = ( 0, 150, 255)
# red    : any other state (STARTING, RECOVERING, FAILED, DOWN)
COL_STATUS_DOWN = ( 60,  60, 230)

# ---- Segmentation / perception ----
# omdet path deleted (may return with a better vision system)
SEGMENTER                       = "sam3"
# SAM3 vision model: ONE local file at SAM3_MODEL_DIR. Loaded locally (HF_HUB_OFFLINE=1,
# no download) and compressed to 4-bit (nf4) IN MEMORY at load by bitsandbytes -- there
# is NO separate quantized file. SAM3_PRECISION is fixed here, not an env knob. The
# overlay shows the model NAME.
SAM3_MODEL_DIR                  = "/root/models/vision/sam3-official"
SAM3_PRECISION                  = "nf4"
# cap on boxes SAM3 returns — high so a real scene never clips
SAM3_MAX_BOXES_PER_QUERY        = 128
# cap on detections actually drawn — effectively draw-all
MAX_HIGHLIGHTS_DRAWN_PER_FRAME  = 128
# absolute floor: nothing below this score is ever drawn
MIN_DRAW_CONFIDENCE             = 0.30
# threshold handed to the detector, low so candidates surface
DETECTOR_QUERY_THRESHOLD        = 0.12
# ignore boxes smaller than this fraction of the frame (specks)
MIN_BOX_FRACTION_OF_FRAME       = 0.001
COUNT_MEDIAN_FRAMES             = 3         # a count is the median of this many frames
COUNT_FRAME_GAP_SECONDS         = 0.3       # seconds between those frames
# seconds without a SAM3 hit before a highlight is dropped
HIGHLIGHT_GIVEUP_SECONDS        = 8.0
# a live highlight re-detects every this many seconds, counted from the START of each
# detect, so SAM3 does not starve Gemma + whisper on the GPU
SAM3_MIN_SECONDS_BETWEEN_FORWARDS = 1.0
# vision tasks alive at once; one more is refused (never queued). Chosen for clarity,
# not speed: SAM3 alone does ~2.4 forwards/s and threads do not raise that.
VISION_MAX_ACTIVE_TASKS         = 8

# ---- Drone control target (the phone app, or its mock) ----
MOCK_DJI_PORT       = 8079            # mock control target
REAL_DJI_PORT       = 8080            # real drone (phone) control target
# the DJI API test double
MOCK_APISERVER_PATH = _os.path.join(_REPO, "tools", "dji_mock", "mock_apiserver.py")

# ---- Process supervisor (system/supervisor.py) ----
# the C++ binaries + libs
NATIVE_BIN_DIR      = _os.path.join(_REPO, "build", "release", "shared", "dji", "bin")
# restarts of a dead process before the app die()s (owner 2026-09-22)
SUPERVISOR_MAX_RESTARTS   = 3
SUPERVISOR_STABLE_SECONDS = 60.0    # a process up this long has its restart count reset
# a WAITING service (the phone app, the mock, gstreamer) is retried this often
WAITING_RETRY_SECONDS     = 5.0
# the host sound server the ASR server records from (env override: defaults.py)
PULSE_SERVER         = "unix:/tmp/pulse-socket"
