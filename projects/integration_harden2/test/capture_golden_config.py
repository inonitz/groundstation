"""B1 golden capture (2026-09-11): resolve the CURRENT config surface per launch scenario and write
test/golden_config.json. The golden is the behaviour-preserving baseline for the config merge (B2/B3).

It resolves two sources under one process per scenario, so both see the same env:
  1. config.py module attributes (import).
  2. the getenv reads scattered in mvd.py / recognizer/pipeline.py / video/video_watchdog.py.

Host/network/time-derived values are NOT in the golden (they differ per box and per run): the resolved
HE font path, resolve_device()/resolve_torch_device() output, default_gateway()/PHONE_IP, and the session
dir. Those stay as functions; the merge keeps the same resolvers. The golden fixes the deterministic knobs.
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
PKG  = os.path.dirname(HERE)

# Exactly what run_mvd.sh exports into the app, by (VIDEO, CONTROL). "bench" = the naked defaults the
# unified_bench sees (no launcher). PHONE_IP is network-derived -> sentinel in the real scenario.
def launcher_env(video, control):
    e = {
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "SCENE_TMUX_SESSION": "mvd",
        "MVD_DRONE": "1", "SCENE_SEG": "sam3", "MVD_PLANNER": "gemma4", "MVD_TRANSLATOR": "none",
        "SCENE_TTS_LANG": "he", "MVD_XLATE_PORT": "18091",
        "SCENE_SAM2": "/root/models/vision/sam2.1_b.pt", "SCENE_BG": "off",
        "DISPLAY": ":0", "PULSE_SERVER": "unix:/tmp/pulse-socket",
    }
    e["SCENE_INPUT"] = "0" if video == "webcam" else "ros"
    if control == "real":
        e.update({"MVD_WIRE_HOST": "<PHONE_IP>", "MVD_WIRE_PORT": "8080", "MVD_WIRE_REAL": "1"})
    else:
        e.update({"MVD_WIRE_HOST": "127.0.0.1", "MVD_WIRE_PORT": "8079", "MVD_WIRE_REAL": ""})
    return e

SCENARIOS = {
    "bench":        {},                              # naked defaults (unified_bench path)
    "webcam_mock":  launcher_env("webcam", "mock"),
    "dji_mock":     launcher_env("dji",    "mock"),
    "dji_real":     launcher_env("dji",    "real"),
}

# The scattered getenv reads, transcribed verbatim from the source (file:line in the comment).
def scattered(env):
    g = env.get
    return {
        # mvd.py
        "SEG":            g("SCENE_SEG", "sam3"),                    # L162
        "SAM3_PERIOD":    float(g("SCENE_SAM3_PERIOD", "1.0")),      # L163
        "HL_GIVEUP":      float(g("SCENE_HL_GIVEUP", "8.0")),        # L164
        "GATE":           g("SCENE_GATE", "sam3"),                  # L165
        "COUNT_FRAMES":   int(g("SCENE_COUNT_FRAMES", "3")),        # L166
        "COUNT_GAP":      float(g("SCENE_COUNT_GAP", "0.3")),        # L167
        "MIN_BOX_FRAC":   float(g("SCENE_MIN_BOX_FRAC", "0.001")),   # L168
        "HL_TOPK":        int(g("SCENE_HL_TOPK", "128")),           # L174
        "HL_MAX":         int(g("SCENE_HL_MAX", "128")),            # L175
        "DETECT_FLOOR":   float(g("SCENE_DETECT_FLOOR", "0.12")),    # L540
        "HL_CONF":        float(g("SCENE_HL_CONF", "0.30")),         # L541
        "HL_REL":         float(g("SCENE_HL_REL", "0.65")),          # L542
        "PLANNER":        g("MVD_PLANNER", "gemma4"),               # L426
        "TTS_ON":         g("MVD_TTS", "1") != "0",                 # L546
        "DRONE_ROUTER":   bool(g("MVD_DRONE")),                     # L555
        "WIRE_HOST":      g("MVD_WIRE_HOST", "127.0.0.1"),          # L593
        "WIRE_REAL":      bool(g("MVD_WIRE_REAL")),                 # L594
        "PHONE_ASR_ON":   g("MVD_PHONE_ASR", "1") != "0",          # L603
        "PHONE_ASR_PORT": int(g("MVD_PHONE_ASR_PORT", "8080")),    # L606
        # recognizer/pipeline.py
        "XLATE_PORT":     int(g("MVD_XLATE_PORT", "18091")),        # L40
        "TRANSLATOR":     g("MVD_TRANSLATOR", "none"),             # L83
        "TRANSLATE_PROMPT": g("MVD_TRANSLATE_PROMPT", "v1"),      # L184
        # video/video_watchdog.py
        "WATCHDOG_STALL_SEC": float(g("WATCHDOG_STALL_SEC", "6")), # L15
        "WATCHDOG_RETRY_SEC": float(g("WATCHDOG_RETRY_SEC", "15")),# L16
    }

# config.py attrs to capture (deterministic knobs only; HE_FONT_PATH/DEVICE-resolution excluded).
CONFIG_ATTRS = ["LLAMA_URL","VLM_TIMEOUT","BG_SEG_MODEL","SAM2_WEIGHTS","CONF_BG","DETECT_IMGSZ","DEVICE",
                "ASR_TOPIC","INPUT","CAM_W","CAM_H","CHAT_W","HE_FONT_SIZE","OPEN_TIMEOUT","READ_RETRY",
                "TTS_BACKEND","TTS_HOST","TTS_PORT","TTS_LANG","TTS_RATE","TTS_TIMEOUT","TTS_MODEL",
                "TTS_PIPER_BIN","TTS_SR"]

def capture_one(env):
    # fresh subprocess-like isolation via importlib reload under the scenario env
    for k in list(os.environ):
        if k.startswith(("SCENE_","MVD_","ASR_","WATCHDOG_","WEBCAM_","VIDEO","CONTROL","HF_","TRANSFORMERS_","DISPLAY","PULSE_","RECORD","DESK_","PHONE_IP","TMPDIR")):
            os.environ.pop(k, None)
    os.environ.update(env)
    sys.path.insert(0, PKG)
    import importlib
    import config as _c
    importlib.reload(_c)
    cfg = {a: getattr(_c, a, None) for a in CONFIG_ATTRS}
    cfg.update(scattered(os.environ))
    return cfg

def main():
    golden = {name: capture_one(dict(env)) for name, env in SCENARIOS.items()}
    out = os.path.join(HERE, "golden_config.json")
    json.dump(golden, open(out, "w"), indent=1, ensure_ascii=False, sort_keys=True)
    print("wrote", out)
    for name in SCENARIOS:
        print(f"\n== {name} ==")
        for k in sorted(golden[name]): print(f"  {k} = {golden[name][k]!r}")

if __name__ == "__main__":
    main()
