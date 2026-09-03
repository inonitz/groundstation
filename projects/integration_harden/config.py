"""Config for integration_harden -- the single home for every tunable and default.

Contract: every module does `import config; config.X`. This file imports no sibling module, so it
also loads from a bare script. It is organized into seven sections; to jump, search the banner for
the number (e.g. "3. Ears").

    1. VLM brain          Qwen3-VL endpoint + timeout
    2. Eyes / detectors   background + highlight models, detector knobs
    3. Ears (ASR)         the transcript topic we subscribe to
    4. Camera + window    video input source and window sizing
    5. Overlay colours    BGR colours for the on-screen overlays
    6. Voice out (TTS)    how spoken answers are produced
    7. Resolvers          device + gateway lookups (functions, not constants)
"""
import os

# ROCm/MIOpen: fast kernel-search so the one-time GPU kernel compile at startup is short (harmless
# on non-AMD backends). Must be set before torch initializes the GPU.
os.environ.setdefault("MIOPEN_FIND_MODE", "2")


# ============================== 1. VLM brain ==============================
# Qwen3-VL-4B on the repo's llama-server (run_llama_server.sh).
LLAMA_URL   = os.environ.get("SCENE_LLAMA_URL", "http://127.0.0.1:18090")
VLM_TIMEOUT = 30                      # a warm 4B describe call is ~1-3 s


# =========================== 2. Eyes / detectors ==========================
# Background = always-on closed-set YOLO26-seg (Eyes.background). Highlight = OmDet-Turbo open-vocab
# detection gated by the VLM presence check, then a SAM2 mask (perception/engine.py owns that
# decision). YOLOE and LLMDet/grounder were both removed on 2026-09-03.
BG_SEG_MODEL = os.environ.get("SCENE_BG",   "yolo26n-seg.pt")
SAM2_WEIGHTS = os.environ.get("SCENE_SAM2", "sam2.1_b.pt")
CONF_BG      = float(os.environ.get("SCENE_CONF_BG", "0.35"))   # background-detector confidence floor
DETECT_IMGSZ = int(os.environ.get("SCENE_IMGSZ", "640"))        # detector input size (speed knob)
DEVICE       = os.environ.get("SCENE_DEVICE", "")               # "" = auto (see resolve_device); "cpu" to force


# ============================== 3. Ears (ASR) =============================
# The EXISTING ROS2 asr_node publishes transcripts here (sttserv backend, push-to-talk on the H
# key). We SUBSCRIBE; we never capture or transcribe in Python.
ASR_TOPIC = os.environ.get("SCENE_ASR_TOPIC", "/asr_server/transcribe")


# ============================ 4. Camera + window ==========================
# Input: "ros" (the camera/stream topic), a webcam index ("0"), a video file, a URL, or a
# GStreamer pipeline, e.g.
#   SCENE_INPUT='tcpclientsrc host=<phone-ip> port=5600 ! h264parse ! avdec_h264 ! videoconvert ! appsink'
INPUT        = os.environ.get("SCENE_INPUT", os.environ.get("SCENE_CAM", "0"))
CAM_W        = int(os.environ.get("SCENE_CAM_W", "1280"))          # requested webcam width (falls to nearest supported)
CAM_H        = int(os.environ.get("SCENE_CAM_H", "720"))           # requested webcam height
CHAT_W       = int(os.environ.get("SCENE_CHAT_W", "460"))          # chat side-pane width (px)
OPEN_TIMEOUT = float(os.environ.get("SCENE_OPEN_TIMEOUT", "180"))  # secs to keep retrying a not-yet-live input
READ_RETRY   = int(os.environ.get("SCENE_READ_RETRY", "150"))      # consecutive read failures tolerated (network jitter)


# ============================ 5. Overlay colours ==========================
# BGR. Three overlay sources, told apart at a glance, plus the chat-pane labels.
COL_BACKGROUND = (130, 130, 130)   # subtle grey  : always-on background detector (thin boxes)
COL_YOLOE_HL   = ( 60, 220,  60)   # vibrant green: OmDet open-vocab highlight (name kept; drawn by scene_omdet)
COL_SAM2_HL    = (220,  60, 220)   # magenta      : SAM2 mask
COL_HUD        = (  0, 255, 255)   # cyan         : fps / status line
COL_CHAT_USER  = (255, 210, 120)   # 'You:' label
COL_CHAT_MODEL = (160, 235, 160)   # 'Scene:' label


# ============================ 6. Voice out (TTS) ==========================
# The PHONE app (DJI backend) OWNS TTS and speaks via POST /tts. LOCAL only, no cloud.
TTS_BACKEND = os.environ.get("SCENE_TTS", "phone")            # phone (default) | espeak | piper | both | off
# "both" speaks every answer TWICE (phone + laptop). It stays available for desk debugging with a
# phone attached, but it must be asked for explicitly -- it is not the default.
TTS_HOST    = os.environ.get("SCENE_TTS_HOST", "")            # phone IP; "" -> host= from SCENE_INPUT, else default_gateway()
TTS_PORT    = int(os.environ.get("SCENE_TTS_PORT", "8080"))   # app ApiServer port
TTS_LANG    = os.environ.get("SCENE_TTS_LANG", "en")          # POST /tts lang (country omitted)
TTS_RATE    = float(os.environ.get("SCENE_TTS_RATE", "1.0"))  # POST /tts speech rate (1.0 = normal)
TTS_TIMEOUT = float(os.environ.get("SCENE_TTS_TIMEOUT", "3")) # POST timeout (s)
# desk-debug fallbacks only (no phone): piper voice model, its binary, and its raw sample rate
TTS_MODEL     = os.environ.get("SCENE_TTS_MODEL", "/root/models/tts/voices/en_US-lessac-medium.onnx")
TTS_PIPER_BIN = os.environ.get("SCENE_TTS_PIPER_BIN", "/root/models/tts/piper/piper")
TTS_SR        = int(os.environ.get("SCENE_TTS_SR", "22050"))


# =============================== 7. Resolvers =============================

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


def resolve_torch_device():
    """torch-style device string ('cuda'/'mps'/'cpu') for transformers/HF models. Same portability
    contract as resolve_device(), but HF wants 'cuda' where Ultralytics wants '0'. ROCm reports as
    'cuda' (HIP) too, so this stays vendor-neutral."""
    dev = resolve_device()
    return dev if dev in ("cpu", "mps") else "cuda"   # "0"/"1" (CUDA or ROCm/HIP) -> torch "cuda"


def default_gateway():
    """The workstation's default-route gateway. On the phone's hotspot that IS the phone's IP, which
    is how tts_io, video_doctor and video_watchdog find the app. Returns None when there is no
    default route -- callers MUST handle that (a literal "None" in a command line is a real bug we
    already shipped once). This is the one home for the lookup; all three used to hand-roll it."""
    try:
        for line in open("/proc/net/route").readlines()[1:]:
            f = line.split()
            if f[1] == "00000000":              # destination 0.0.0.0 = the default route
                return ".".join(str(int(f[2][i:i + 2], 16)) for i in (6, 4, 2, 0))
    except Exception:
        pass
    return None
