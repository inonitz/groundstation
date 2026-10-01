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
KEY_ACTION_RELEASED = 0
# evdev KEY_F4. A function key, never a letter: letters are typed in other windows
# (owner 2026-09-23).
KILL_KEY_CODE      = 62
KILL_KEY_NAME      = "F4"
# Every global action is a function key (owner 2026-09-23: "Use the function keys";
# letters are typed in other windows). Quit is F1, far from F4 (kill) and F5 (talk).
QUIT_KEY_CODE      = 59              # evdev KEY_F1
QUIT_KEY_NAME      = "F1"
CLEAR_KEY_CODE     = 60              # evdev KEY_F2: clear the highlight
CLEAR_KEY_NAME     = "F2"
# shown on screen; the binding itself is compiled into the asr_node
# (llm_to_action asr_node.hpp kPushToTalkKeyBind)
PUSH_TO_TALK_KEY_NAME = "F5"
PUSH_TO_TALK_KEY_CODE = 63            # evdev KEY_F5: its release starts the ASR timing

# Window keys: they act ONLY while the app window has the focus (cv2.waitKey codes)
WINDOW_TITLE            = "integration:mvd"
WINDOW_QUIT_KEYS        = (27, ord("q"))    # Esc, q
WINDOW_CLEAR_KEY        = ord("c")          # clear the highlight
WINDOW_MASKS_KEY        = ord("t")          # masks on/off
WINDOW_SCROLL_UP_KEY    = ord("[")          # older chat rows
WINDOW_SCROLL_DOWN_KEY  = ord("]")          # back toward the newest
WINDOW_CLEAR_CHAT_KEY   = ord("x")
CHAT_SCROLL_ROWS        = 3                 # chat rows per wheel notch or [ / ] press

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
# the preflight reads the selected camera again after this many seconds before it fails:
# a camera just released by a stopped run can give no frame for a moment (owner O3 a)
CAMERA_CHECK_RETRY_SECONDS = 1.0

# ---- Video stall guard (video/video.py) ----
WATCHDOG_STALL_SECONDS = 6.0          # no new frame for this long -> stalled
WATCHDOG_RETRY_SECONDS = 15.0         # seconds between gstreamer restarts

# ---- On-screen overlay colours (BGR; fixed) ----
COL_HIGHLIGHT  = ( 60, 220,  60)   # green  : a highlight box (SAM3)
COL_MASK       = (220,  60, 220)   # magenta: a highlight mask (SAM3)
COL_HUD        = (255, 255,   0)   # cyan   : fps / status line (BGR; #00ffff)
COL_HUD_SHADOW = (  0,   0,   0)   # black  : under HUD text, readable on a white wall
COL_PROMPT     = (163, 149, 139)   # grey   : the push-to-talk prompt
COL_STATUS_UP   = ( 80, 200,  80)  # green  : a system that is UP
# orange: WAITING, the user must fix it (owner 2026-09-23)
COL_STATUS_WAITING = ( 0, 150, 255)
# red    : any other state (STARTING, RECOVERING, FAILED, DOWN)
COL_STATUS_DOWN = ( 60,  60, 230)
COL_STATUS_NAME   = (235, 235, 235)   # a status row's name
COL_STATUS_DETAIL = (170, 170, 170)   # the detail under a row that is not UP
COL_PANE_GROUND = ( 31,  25,  22)  # the dark ground of the status + chat panes (#16191f)
COL_WAITING_TEXT = ( 0, 200, 255)  # "waiting for video..." before the first frame
MASK_TINT_ALPHA = 0.45             # a highlight mask's weight over the camera picture
# the chat pane (mockup tools/ui-mockups/live-pane.html, owner-inspected 2026-09-12)
CHAT_COLOURS = {
    "you": (120, 210, 255),
    "light": (240, 235, 231),
    "dim": (163, 149, 139),
    "green": (100, 220, 60),
    "amber": (41, 180, 240),
    "model": (176, 235, 160),
    "red": (107, 107, 255),
    "spoken": (74, 210, 255),
    "cmd": (245, 235, 150),
}
COL_CHAT_TAG  = (163, 149, 139)    # the dim tag column (mockup #8b95a3)
COL_CHAT_RULE = ( 59,  49,  43)    # the header rule and the turn separators
COL_CHAT_HINT = (150, 150, 150)    # the empty-chat hint

# ---- On-screen fonts (TrueType through PIL; OpenCV's font is ASCII only) ----
# DejaVu Sans for Hebrew (REQUIRED: missing = fatal), Ubuntu for English values and the
# header, DejaVu Sans Mono for the tag column (both optional: the Hebrew font stands in)
FONT_HEBREW_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_VALUE_PATH  = "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"
FONT_TAG_PATH    = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
TAG_FONT_SIZE    = HE_FONT_SIZE - 2

# ---- The panes' layout (px; owner D8 a) ----
CHAT_MARGIN       = 12    # the text's left and right margin, and the header's top
CHAT_TAG_RIGHT    = 66    # tags are right-aligned, ending at this x
CHAT_VALUE_X      = 76    # values start at this x
CHAT_HEADER_LINE  = 19    # one header line
CHAT_ROW_LINE     = 21    # one wrapped conversation line
CHAT_TURN_GAP     = 14    # the gap a turn separator takes
CHAT_BOTTOM       = 14    # the newest line's gap above the pane's bottom
STATUS_MARGIN      = 12   # the title's and the state box's x; the state's right margin
STATUS_TEXT_X      = 36   # a row's name and its detail start here
STATUS_FIRST_ROW_Y = 50   # the first row's baseline
STATUS_ROW_LINE    = 22   # a row
STATUS_DETAIL_LINE = 17   # one detail line
STATUS_ROW_GAP     = 6    # after each row and its detail
STATUS_DETAIL_CHARS = 38  # a detail wraps at this many characters
STATUS_DETAIL_LINES = 3   # at most this many detail lines

# ---- Segmentation / perception ----
# omdet path deleted (may return with a better vision system)
SEGMENTER                       = "sam3"
# SAM3 vision model: the bf16 checkpoint at SAM3_MODEL_DIR (loaded locally,
# HF_HUB_OFFLINE=1, no download). SAM3_PRECISION is fixed here, not an env knob. The
# overlay shows the model NAME.
SAM3_MODEL_DIR                  = "/root/models/vision/sam3-official"
# SAM3 saved ONCE in its nf4 form (owner S7 c): the app loads it ready, no quantizing at
# start. sam3/save_nf4.py writes it; the install script runs that when it is missing.
SAM3_NF4_DIR                    = "/root/models/vision/sam3-nf4"
SAM3_PRECISION                  = "nf4"
# the warm-up at start (owner L1, 2026-09-30): one SAM3 pass on a blank camera-size
# frame, and one Gemma plan of this sentence, before their rows turn UP. A cold first
# pass took 1.4-2.1 s and a cold first plan 1.5 s
# (docs/research-complete-e2e-latency-breakdown.md).
SAM3_WARM_UP_PHRASE             = "person"
PLAN_WARM_UP_SENTENCE           = "טוס קדימה מטר אחד"
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

# ---- Process supervisor (runtime/supervisor.py) ----
# the C++ binaries + libs
NATIVE_BIN_DIR      = _os.path.join(_REPO, "build", "release", "shared", "dji", "bin")
# one build installs all four programs (runtime/deps.py checks them at start-up)
LLAMA_SERVER_BIN    = _os.path.join(NATIVE_BIN_DIR, "llama-server")
ASR_SERVER_BIN      = _os.path.join(NATIVE_BIN_DIR, "llm_to_action_asr_server")
KEYBOARD_HOOK_BIN   = _os.path.join(NATIVE_BIN_DIR, "llm_to_action_keyboard_hook")
GSTREAMER_RX_BIN    = _os.path.join(NATIVE_BIN_DIR, "llm_to_action_gstreamer_rx")
# restarts of a dead process before the app die()s (owner 2026-09-22)
SUPERVISOR_MAX_RESTARTS   = 3
SUPERVISOR_STABLE_SECONDS = 60.0    # a process up this long has its restart count reset
# a WAITING process (the mock, gstreamer) is restarted this often
WAITING_RETRY_SECONDS     = 5.0
# the phone-app client checks a WAITING phone app this often (owner U6 a, 2026-09-28)
PHONE_APP_CHECK_SECONDS   = 2.0
# the host sound server the ASR server records from (env override: defaults.py)
PULSE_SERVER         = "unix:/tmp/pulse-socket"

# ---- the perf record (log/perf.py, perf_report.py; owner rulings C.1, R7, Q3, V1) ----
# R7: the buffer is written this often; a hard kill loses at most this much
PERF_FLUSH_SECONDS        = 5.0
PERF_GPU_SAMPLE_SECONDS   = 1.0     # Q3 a: one pynvml sample (0.018 ms) this often
# the status rows are checked this often until every row has been UP once
PERF_STARTUP_POLL_SECONDS = 0.1
PERF_SLOWEST_FRAMES       = 20      # V1 a: the report lists this many slowest frames
