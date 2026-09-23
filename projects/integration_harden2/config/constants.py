"""harden2 BAKED constants — values baked into the app (read through config/__init__.py).

Decided values that do not change between runs. One place, by category, readable at a glance. Names
describe intent. Anything you change per run is in config/defaults.py. Deleted knobs (the MVD_HOME fork-selector — harden2 is the only system, launchers hardcode it now —
translator, qwen3vl, omdet/sam2/yolo, thinking flag, SCENE_TTS backend-switch, the MVD_DRONE router toggle) do not
appear here at all. Routing is unconditional: the live wire target is derived from CONTROL (mock|real) via config.wire_target;
DjiWire's loopback guard is the mock/real gate. There is no "enable router" flag.
"""

# ── Model / planner (Gemma 4 E4B only) ─────────────────────────────────────────────────────
GEMMA_DIR              = "/root/models/vlm/Gemma-4-E4B"
GEMMA_MODEL_PATH       = GEMMA_DIR + "/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"
GEMMA_MMPROJ_PATH      = GEMMA_DIR + "/mmproj-BF16.gguf"
GEMMA_THINKING_ENABLED = False        # thinking OFF (decided)
VLM_TIMEOUT_SECONDS    = 30           # a warm 4B describe call is ~1-3 s

# ── Ports ────────────────────────────────────────────────────────────────────────────────
LLAMA_SERVER_PORT = 18090             # the Gemma server
MOCK_WIRE_PORT    = 8079              # mock control target
REAL_WIRE_PORT    = 8080              # real drone (phone) control target
PHONE_ASR_PORT    = 8080              # phone speech channel

# ── Segmentation / perception ────────────────────────────────────────────────────────────
SEGMENTER                       = "sam3"   # omdet path deleted (may return with a better vision system)
# SAM3 vision model: ONE local file at SAM3_MODEL_DIR. Loaded locally (HF_HUB_OFFLINE=1, no download)
# and compressed to 4-bit (nf4) IN MEMORY at load by bitsandbytes -- there is NO separate quantized
# file. SAM3_PRECISION is fixed here, not an env knob. The overlay shows the model NAME.
SAM3_MODEL_DIR                  = "/root/models/vision/sam3-official"
SAM3_PRECISION                  = "nf4"
SAM3_MAX_BOXES_PER_QUERY        = 128       # cap on boxes SAM3 returns — high so a real scene never clips
MAX_HIGHLIGHTS_DRAWN_PER_FRAME  = 128       # cap on detections actually drawn — effectively draw-all
MIN_DRAW_CONFIDENCE             = 0.30      # absolute floor: nothing below this score is ever drawn
DETECTOR_QUERY_THRESHOLD        = 0.12      # threshold handed to the detector, low so candidates surface
MIN_BOX_FRACTION_OF_FRAME       = 0.001     # ignore boxes smaller than this fraction of the frame (specks)
COUNT_MEDIAN_FRAMES             = 3         # a count is the median of this many frames
COUNT_FRAME_GAP_SECONDS         = 0.3       # seconds between those frames
HIGHLIGHT_GIVEUP_SECONDS        = 8.0       # seconds without a SAM3 hit before a highlight is dropped
SAM3_MIN_SECONDS_BETWEEN_FORWARDS = 1.0     # rate-limit SAM3 so it does not starve Gemma + whisper on the GPU
VISION_MAX_ACTIVE_TASKS         = 8         # cap on queued vision tasks; tune to the GPU (SAM3 alone ~2.4 forwards/s)

# ── Process supervisor (system/supervisor.py) ────────────────────────────────────────────
import os as _os
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".."))
NATIVE_BIN_DIR      = _os.path.join(_REPO, "build", "release", "shared", "dji", "bin")   # the C++ binaries + libs
MOCK_APISERVER_PATH = _os.path.join(_REPO, "tools", "dji_mock", "mock_apiserver.py")      # the DJI API test double
SUPERVISOR_MAX_RESTARTS   = 3       # restarts of a dead process before the app die()s (owner 2026-09-22)
SUPERVISOR_STABLE_SECONDS = 60.0    # a process up this long has its restart count reset
SERVICE_RETRY_SECONDS     = 2.0     # wait between recovery attempts of a remote service (the phone TTS)

# ── Camera + on-screen UI (fixed geometry) ────────────────────────────────────────────────
CAMERA_REQUEST_WIDTH  = 1280          # requested webcam width (falls to nearest supported)
CAMERA_REQUEST_HEIGHT = 720           # requested webcam height
BOTTOM_PANE_HEIGHT    = 300           # the band under the camera: status | chat (owner 2026-09-22)
STATUS_PANE_WIDTH     = 300           # system status pane, right of the chat pane (px)
HE_FONT_SIZE          = 17            # Hebrew overlay glyph size
INPUT_OPEN_TIMEOUT_SECONDS = 180.0    # keep retrying a not-yet-live input this long
INPUT_READ_RETRY_LIMIT     = 150      # consecutive read failures tolerated (network jitter)

# ── Video stall guard (video/camera_stream.StallGuard) ───────────────────────────────────
WATCHDOG_STALL_SECONDS = 6.0          # no new frame for this long -> stalled
WATCHDOG_RETRY_SECONDS = 15.0         # seconds between reconnect attempts

# ── Speech ─────────────────────────────────────────────────────────────────────────────
ASR_TRANSCRIBE_TOPIC = "/asr_server/transcribe"   # ROS2 topic the asr_node publishes to (we subscribe)
TTS_BACKEND      = "phone"            # the phone app owns TTS via POST /tts (only backend in the active system)
TTS_PORT         = REAL_WIRE_PORT     # the phone ApiServer port (same 8080)
TTS_LANGUAGE     = "he"               # phone answers in Hebrew
PHONE_ASR_ENABLED = True              # always listen on the phone speech channel

# ── Always-on environment ────────────────────────────────────────────────────────────────
PULSE_SERVER         = "unix:/tmp/pulse-socket"

# ── On-screen overlay colours (BGR; fixed) ───────────────────────────────────────────────
COL_HIGHLIGHT  = ( 60, 220,  60)   # green  : open-vocab highlight (SAM3/OmDet)
COL_MASK       = (220,  60, 220)   # magenta: SAM3/SAM2 mask
COL_HUD        = (255, 255,   0)   # cyan   : fps / status line (BGR; #00ffff)
COL_STATUS_UP   = ( 80, 200,  80)  # green  : a system that is UP
COL_STATUS_DOWN = ( 60,  60, 230)  # red    : any other state (STARTING, RECOVERING, FAILED, DOWN)
