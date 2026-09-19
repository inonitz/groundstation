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
VIDEO_TCP_PORT    = 5600              # gstreamer_rx receives the phone's H.264

# ── Segmentation / perception ────────────────────────────────────────────────────────────
SEGMENTER                       = "sam3"   # omdet path deleted (may return with a better vision system)
# SAM3 vision model: ONE local file at SAM3_MODEL_DIR. Loaded locally (HF_HUB_OFFLINE=1, no download)
# and compressed to 4-bit (nf4) IN MEMORY at load by bitsandbytes -- there is NO separate quantized
# file. SAM3_PRECISION is fixed here, not an env knob. The overlay shows the model NAME.
SAM3_MODEL_DIR                  = "/root/models/vision/sam3-official"
SAM3_PRECISION                  = "nf4"
BACKGROUND_SEGMENTER            = None      # background YOLO OFF (saves ~282 MiB)
SAM3_MAX_BOXES_PER_QUERY        = 128       # cap on boxes SAM3 returns — high so a real scene never clips
MAX_HIGHLIGHTS_DRAWN_PER_FRAME  = 128       # cap on detections actually drawn — effectively draw-all
MIN_DRAW_CONFIDENCE             = 0.30      # absolute floor: nothing below this score is ever drawn
DETECTOR_QUERY_THRESHOLD        = 0.12      # threshold handed to the detector, low so candidates surface
MIN_BOX_FRACTION_OF_FRAME       = 0.001     # ignore boxes smaller than this fraction of the frame (specks)
COUNT_MEDIAN_FRAMES             = 3         # a count is the median of this many frames
COUNT_FRAME_GAP_SECONDS         = 0.3       # seconds between those frames
HIGHLIGHT_GIVEUP_SECONDS        = 8.0       # seconds without a SAM3 hit before a highlight is dropped
SAM3_MIN_SECONDS_BETWEEN_FORWARDS = 1.0     # rate-limit SAM3 so it does not starve Gemma + whisper on the GPU

# ── Camera + on-screen UI (fixed geometry) ────────────────────────────────────────────────
CAMERA_REQUEST_WIDTH  = 1280          # requested webcam width (falls to nearest supported)
CAMERA_REQUEST_HEIGHT = 720           # requested webcam height
CHAT_PANE_WIDTH       = 460           # chat side-pane width (px)
HE_FONT_SIZE          = 17            # Hebrew overlay glyph size (font FILE is resolved per host, see defaults)
INPUT_OPEN_TIMEOUT_SECONDS = 180.0    # keep retrying a not-yet-live input this long
INPUT_READ_RETRY_LIMIT     = 150      # consecutive read failures tolerated (network jitter)

# ── Video stall watchdog ─────────────────────────────────────────────────────────────────
WATCHDOG_STALL_SECONDS = 6.0          # no new frame for this long -> stalled
WATCHDOG_RETRY_SECONDS = 15.0         # seconds between reconnect attempts

# ── Speech ─────────────────────────────────────────────────────────────────────────────
ASR_TRANSCRIBE_TOPIC = "/asr_server/transcribe"   # ROS2 topic the asr_node publishes to (we subscribe)
TTS_BACKEND      = "phone"            # the phone app owns TTS via POST /tts (only backend in the active system)
TTS_PORT         = REAL_WIRE_PORT     # the phone ApiServer port (same 8080)
TTS_LANGUAGE     = "he"               # phone answers in Hebrew
PHONE_ASR_ENABLED = True              # always listen on the phone speech channel

# ── Always-on environment ────────────────────────────────────────────────────────────────
HF_HUB_OFFLINE       = True           # never touch the hub (the hotspot has no internet)
TRANSFORMERS_OFFLINE = True
TMUX_SESSION_NAME    = "mvd"          # the tmux session the app runs in (pane management + teardown)
X_DISPLAY            = ":0"           # X display for the app window
PULSE_SERVER         = "unix:/tmp/pulse-socket"

# ── On-screen overlay colours (BGR; fixed) ───────────────────────────────────────────────
COL_BACKGROUND = (130, 130, 130)   # grey   : always-on background detector (thin boxes)
COL_HIGHLIGHT  = ( 60, 220,  60)   # green  : open-vocab highlight (SAM3/OmDet)
COL_MASK       = (220,  60, 220)   # magenta: SAM3/SAM2 mask
COL_HUD        = (255, 255,   0)   # cyan   : fps / status line (BGR; #00ffff)
COL_CHAT_USER  = (255, 210, 120)   # 'You:' label
COL_CHAT_MODEL = (160, 235, 160)   # 'Scene:' label
