"""B3 golden-master: the completed config_constants.py + config_defaults.py must resolve to the SAME
values the current code path produces (test/golden_config.json, captured by capture_golden_config.py).

Scope: the ACTIVE keys, for the three scenarios the APP actually runs in (webcam_mock, dji_mock, dji_real).
The bench scenario is excluded — it does not run the app, and its yolo/en values are the stale config.py
defaults the merge intentionally drops. Dead keys (omdet/sam2/yolo + translator) and host/network-derived
values (HE font path, device, the real-mode phone IP) are not asserted; the merge keeps those resolvers.

This proves the merge is behaviour-preserving at the config layer BEFORE any app rewire. It is the net that
stands in for a live run for every deterministic knob. The residual (live perception/camera/TTS runtime) is
confirmed by one owner webcam run when the app is wired (B2).
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config_constants as K
import config_defaults as D

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = json.load(open(os.path.join(HERE, "golden_config.json"), encoding="utf-8"))

# Dead keys the merge drops (omdet/sam2/yolo detector path + translator). Not asserted.
DEAD = {"BG_SEG_MODEL", "SAM2_WEIGHTS", "CONF_BG", "DETECT_IMGSZ", "DEVICE",
        "TRANSLATOR", "XLATE_PORT", "TRANSLATE_PROMPT"}
# Host/network-derived. Asserted only where deterministic (see resolved()).
DERIVED = {"WIRE_HOST"}

def resolved(video, control):
    """Resolve the active golden keys from the two config files for one app scenario. This mirrors what
    the rewired app must read. It is the spec for B2."""
    host, port, is_real = D.wire_target(control)
    return {
        "LLAMA_URL":      "http://127.0.0.1:%d" % K.LLAMA_SERVER_PORT,
        "VLM_TIMEOUT":    K.VLM_TIMEOUT_SECONDS,
        "ASR_TOPIC":      K.ASR_TRANSCRIBE_TOPIC,
        "INPUT":          D.video_input(video),
        "CAM_W":          K.CAMERA_REQUEST_WIDTH,
        "CAM_H":          K.CAMERA_REQUEST_HEIGHT,
        "CHAT_W":         K.CHAT_PANE_WIDTH,
        "HE_FONT_SIZE":   K.HE_FONT_SIZE,
        "OPEN_TIMEOUT":   K.INPUT_OPEN_TIMEOUT_SECONDS,
        "READ_RETRY":     K.INPUT_READ_RETRY_LIMIT,
        "TTS_BACKEND":    K.TTS_BACKEND,
        "TTS_HOST":       D.TTS_HOST,
        "TTS_PORT":       K.TTS_PORT,
        "TTS_LANG":       K.TTS_LANGUAGE,
        "TTS_RATE":       D.TTS_RATE,
        "TTS_TIMEOUT":    D.TTS_TIMEOUT,
        "TTS_MODEL":      D.TTS_PIPER_MODEL,
        "TTS_PIPER_BIN":  D.TTS_PIPER_BIN,
        "TTS_SR":         D.TTS_PIPER_SR,
        "TTS_ON":         D.TTS_ENABLED,
        "PHONE_ASR_ON":   K.PHONE_ASR_ENABLED,
        "PHONE_ASR_PORT": K.PHONE_ASR_PORT,
        "SEG":            K.SEGMENTER,
        "SAM3_PERIOD":    K.SAM3_MIN_SECONDS_BETWEEN_FORWARDS,
        "HL_GIVEUP":      K.HIGHLIGHT_GIVEUP_SECONDS,
        "GATE":           D.HIGHLIGHT_PRESENCE_GATE,
        "COUNT_FRAMES":   K.COUNT_MEDIAN_FRAMES,
        "COUNT_GAP":      K.COUNT_FRAME_GAP_SECONDS,
        "MIN_BOX_FRAC":   K.MIN_BOX_FRACTION_OF_FRAME,
        "HL_TOPK":        K.SAM3_MAX_BOXES_PER_QUERY,
        "HL_MAX":         K.MAX_HIGHLIGHTS_DRAWN_PER_FRAME,
        "DETECT_FLOOR":   K.DETECTOR_QUERY_THRESHOLD,
        "HL_CONF":        K.MIN_DRAW_CONFIDENCE,
        "HL_REL":         D.RELATIVE_CONFIDENCE_GATE,
        "PLANNER":        "gemma4",          # Gemma is the only planner; the toggle is deleted
        "DRONE_ROUTER":   True,              # routing is unconditional
        "WIRE_HOST":      host,
        "WIRE_REAL":      is_real,
        "WATCHDOG_STALL_SEC": K.WATCHDOG_STALL_SECONDS,
        "WATCHDOG_RETRY_SEC": K.WATCHDOG_RETRY_SECONDS,
    }

SCENARIOS = {"webcam_mock": ("webcam", "mock"), "dji_mock": ("dji", "mock"), "dji_real": ("dji", "real")}

def test_every_active_key_matches_golden_per_app_scenario():
    diffs = []
    for name, (video, control) in SCENARIOS.items():
        r = resolved(video, control)
        g = GOLDEN[name]
        for key, val in r.items():
            if key in DEAD:
                continue
            if key == "WIRE_HOST" and control == "real":
                continue                      # network-derived phone IP; golden is a sentinel
            if key not in g:
                diffs.append(f"[{name}] {key}: not in golden")
                continue
            if g[key] != val:
                diffs.append(f"[{name}] {key}: golden={g[key]!r} new={val!r}")
    assert not diffs, "config merge changes behaviour:\n  " + "\n  ".join(diffs)

def test_no_active_golden_key_is_unmapped():
    """Every golden key (minus dead ones) must be produced by resolved(), so nothing is silently lost."""
    produced = set(resolved("webcam", "mock"))
    missing = [k for k in GOLDEN["webcam_mock"] if k not in DEAD and k not in produced]
    assert not missing, f"golden keys not reproduced by the merged config: {missing}"
