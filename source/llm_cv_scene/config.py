"""Central config: model paths, the llama-server endpoint, and the colour code that lets
you tell the four overlay sources apart on screen (the whole point of this demo)."""
import os

# --- VLM brain: Qwen3-VL-4B on the repo's llama-server (run_llama_server.sh) ---
LLAMA_URL   = os.environ.get("SCENE_LLAMA_URL", "http://127.0.0.1:8080")
VLM_TIMEOUT = 30                      # a warm 4B describe call is ~1-3 s

# --- Real-time eyes: YOLOE (Ultralytics). Prompt-free = always-on background;
#     promptable = on-demand highlight of a phrase. Swap to YOLOE-26 weights when local. ---
YOLOE_BACKGROUND = os.environ.get("SCENE_YOLOE_BG",     "yoloe-11l-seg-pf.pt")
YOLOE_PROMPT     = os.environ.get("SCENE_YOLOE_PROMPT", "yoloe-11l-seg.pt")
SAM2_WEIGHTS     = os.environ.get("SCENE_SAM2",         "sam2.1_b.pt")
DEVICE           = os.environ.get("SCENE_DEVICE", "")   # "" = Ultralytics auto. ROCm torch shows as "cuda" (HIP). NO NVIDIA. Force "cpu" to be safe.
CONF_BG, CONF_HL = 0.35, 0.25

# --- Ears: the EXISTING ROS2 asr_node publishes transcripts here (sttserv backend,
#     push-to-talk on the H key). We SUBSCRIBE; we never capture or transcribe in Python. ---
ASR_TOPIC = os.environ.get("SCENE_ASR_TOPIC", "/asr_server/transcribe")

# --- Camera / window ---
CAM_INDEX = int(os.environ.get("SCENE_CAM", "0"))
WIN_NAME  = "llm_cv_scene"

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
