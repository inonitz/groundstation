"""Central config: model paths, the llama-server endpoint, and the colour code that lets
you tell the four overlay sources apart on screen (the whole point of this demo)."""
import os

# ROCm/MIOpen: fast kernel-search so the one-time GPU kernel compile at startup is short (harmless
# on non-AMD backends). Must be set before torch initializes the GPU.
os.environ.setdefault("MIOPEN_FIND_MODE", "2")

# --- VLM brain: Qwen3-VL-4B on the repo's llama-server (run_llama_server.sh) ---
LLAMA_URL   = os.environ.get("SCENE_LLAMA_URL", "http://127.0.0.1:8080")
VLM_TIMEOUT = 30                      # a warm 4B describe call is ~1-3 s

# --- Real-time eyes: YOLOE (Ultralytics). Prompt-free = always-on background;
#     promptable = on-demand highlight of a phrase. Swap to YOLOE-26 weights when local. ---
# Background (always-on, subtle): fast closed-set YOLO26 segmentation. You already have this
# locally; referenced by name it auto-downloads anywhere (point SCENE_BG at the local path to skip).
BG_SEG_MODEL    = os.environ.get("SCENE_BG",        "yolo26n-seg.pt")
# Highlight (on-demand, open-vocab): YOLOE-26 -- the 2026 model (arXiv 2602.00168), NOT the 2025
# yoloe-11. "l" scale; drop to yoloe-26s/m-seg.pt for less compute.
OPENVOCAB_MODEL = os.environ.get("SCENE_OPENVOCAB", "yoloe-26l-seg.pt")
SAM2_WEIGHTS    = os.environ.get("SCENE_SAM2",      "sam2.1_b.pt")
DEVICE           = os.environ.get("SCENE_DEVICE", "")   # "" = Ultralytics auto. ROCm torch shows as "cuda" (HIP). NO NVIDIA. Force "cpu" to be safe.
CONF_BG = float(os.environ.get("SCENE_CONF_BG", "0.35"))
CONF_HL = float(os.environ.get("SCENE_CONF_HL", "0.10"))   # open-vocab conf runs low; be lenient
HIGHLIGHT_HZ = float(os.environ.get("SCENE_HL_HZ", "2"))   # open-vocab highlight re-runs/sec (throttled)
DETECT_IMGSZ = int(os.environ.get("SCENE_IMGSZ", "640"))   # detector input size (speed knob)

# --- Ears: the EXISTING ROS2 asr_node publishes transcripts here (sttserv backend,
#     push-to-talk on the H key). We SUBSCRIBE; we never capture or transcribe in Python. ---
ASR_TOPIC = os.environ.get("SCENE_ASR_TOPIC", "/asr_server/transcribe")

# --- Camera / window ---
# Input: a webcam index ("0"), a video-file path, or a GStreamer pipeline. The drone stream
# drops in here for Phase 6, e.g.:
#   SCENE_INPUT='tcpclientsrc host=<phone-ip> port=5600 ! h264parse ! avdec_h264 ! videoconvert ! appsink'
INPUT = os.environ.get("SCENE_INPUT", os.environ.get("SCENE_CAM", "0"))
WIN_NAME  = "llm_cv_scene"
CHAT_W    = int(os.environ.get("SCENE_CHAT_W", "460"))     # ChatGPT-style side pane width (px)
RECORD    = os.environ.get("SCENE_RECORD", "")             # set to /path/out.mp4 to record the session

# --- Colour code (BGR). Four distinct sources, compared at a glance. ---
COL_BACKGROUND = (130, 130, 130)   # subtle grey  : always-on detector (thin)
COL_YOLOE_HL   = ( 60, 220,  60)   # vibrant green: YOLOE real-time highlight
COL_SAM2_HL    = (220,  60, 220)   # magenta      : SAM2 mask (other selection method)
COL_VLM_BOX    = (  0, 215, 255)   # amber        : the VLM's OWN one-shot grounding box
COL_TEXT       = (255, 255, 255)
COL_HUD        = (  0, 255, 255)

def resolve_device():
    """Best available compute device -- vendor-neutral, CPU fallback, never raises. This is the
    whole portability contract: nothing here names a platform. torch.cuda.is_available() is True
    for BOTH NVIDIA (CUDA) and AMD (ROCm/HIP); mps covers Apple. Move the app to any box and it
    uses whatever GPU is there, or CPU. (The VLM is even more portable -- llama.cpp on Vulkan runs
    on any vendor.) Override with SCENE_DEVICE if you must."""
    if DEVICE:
        return DEVICE
    try:
        import torch
        if torch.cuda.is_available():                       # CUDA or ROCm/HIP
            return "0"
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():           # Apple
            return "mps"
    except Exception:
        pass
    return "cpu"

# --- chat pane colours + requested webcam resolution (appended) ---
COL_CHAT_USER  = (255, 210, 120)   # 'You:' label (BGR)
COL_CHAT_MODEL = (160, 235, 160)   # 'Scene:' label (BGR)
CAM_W = int(os.environ.get("SCENE_CAM_W", "1280"))   # requested webcam width (falls to nearest supported)
CAM_H = int(os.environ.get("SCENE_CAM_H", "720"))    # requested webcam height

DETECT_HZ = float(os.environ.get("SCENE_DETECT_HZ", "15"))   # cap background detection so it can't starve the display
PERF      = os.environ.get("SCENE_PERF", "0") not in ("", "0", "false", "False")


# --- On-demand highlight grounder (REPLACES YOLOE for highlight). LLMDet-tiny: open-vocab PHRASE
#     grounding, 2025 SOTA on rare/long-tail classes -- built for exactly the esoteric/small/described
#     objects YOLOE could not find. Loads via the transformers MM-Grounding-DINO implementation, whose
#     deformable attention has a pure-PyTorch fallback -> runs on ROCm/CUDA/CPU identically. Swap to a
#     lighter/stable-only checkpoint with e.g.
#     SCENE_GROUNDER=openmmlab-community/mm_grounding_dino_tiny_o365v1_goldg_grit_v3det ---
GROUNDER_REPO = os.environ.get("SCENE_GROUNDER", "iSEE-Laboratory/llmdet_tiny")
GND_BOX_THR   = float(os.environ.get("SCENE_GND_BOX",  "0.30"))   # box-confidence gate
GND_TEXT_THR  = float(os.environ.get("SCENE_GND_TEXT", "0.25"))   # phrase-match gate
GND_TOPK      = int(os.environ.get("SCENE_GND_TOPK", "1"))        # keep at most this many matches

def resolve_torch_device():
    """torch-style device string ('cuda'/'mps'/'cpu') for transformers/HF models. Same portability
    contract as resolve_device(), but HF wants 'cuda' where Ultralytics wants '0'. ROCm reports as
    'cuda' (HIP) too, so this stays vendor-neutral."""
    dev = resolve_device()
    return dev if dev in ("cpu", "mps") else "cuda"   # "0"/"1" (CUDA or ROCm/HIP) -> torch "cuda"

WARMUP = os.environ.get("SCENE_WARMUP", "1") not in ("", "0", "false", "False")   # front-load the GPU kernel compile at startup

OPEN_TIMEOUT = float(os.environ.get("SCENE_OPEN_TIMEOUT", "180"))  # secs to keep retrying a not-yet-live input (drone RTMP)
READ_RETRY   = int(os.environ.get("SCENE_READ_RETRY", "150"))        # consecutive read failures tolerated (network jitter)

HIGHLIGHT_BACKEND = os.environ.get("SCENE_HL_BACKEND", "vlm")   # "vlm"=Qwen3-VL grounds the described referent (understands "red hat", refuses if absent) + SAM2 mask; "yoloe"/"grounder"=detector highlight

VLM_COORD_SCALE = float(os.environ.get("SCENE_VLM_COORD_SCALE", "1000"))  # Qwen3-VL(llama.cpp) returns boxes on a 0-1000 scale -> scale to frame pixels
VLM_MAX_OBJECTS = int(os.environ.get("SCENE_VLM_MAX_OBJECTS", "8"))          # cap boxes per query so a general "what do you see" does not clutter
