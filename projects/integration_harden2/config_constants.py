"""harden2 BAKED constants — DRAFT (2026-09-10, completed 2026-09-11), not yet wired into the app.

Decided values that do not change between runs. One place, by category, readable at a glance. Names
describe intent. Anything you change per run is in config_defaults.py. Deleted knobs (the MVD_HOME fork-selector — harden2 is the only system, launchers hardcode it now —
translator, qwen3vl, omdet/sam2/yolo, thinking flag, SCENE_TTS backend-switch, the MVD_DRONE router toggle) do not
appear here at all. Routing is unconditional now: CONTROL_TARGET alone decides the wire, so there is no
"enable router" flag. Values here are the baseline proven in the 2026-09-11 golden capture (B1).
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
