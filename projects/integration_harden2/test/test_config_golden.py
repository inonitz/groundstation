"""B3 golden-master (reworked for the config/ package, 2026-09-17): the config SURFACE must resolve to
the SAME values the frozen baseline captured (test/golden_config.json). Every value is read through
`import config` ONLY -- the package surface, never its internals (config.constants / config.defaults).

Scope: the ACTIVE keys for the three scenarios the APP runs in (webcam_mock, dji_mock, dji_real). The
per-scenario keys (INPUT, WIRE_*) come from the surface resolvers video_input()/wire_target(), which
take the scenario as an argument. The static knobs are read under an env cleared of SCENE_/MVD_
overrides -- the env the golden was captured at. Dead keys (omdet/sam2/yolo + translator) and
host/network-derived values (HE font, device, the real-mode phone IP) are not asserted.

This proves the config/ package is behaviour-preserving at the config layer. It is the golden-master net.
"""
import os, sys, importlib, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = json.load(open(os.path.join(HERE, "golden_config.json"), encoding="utf-8"))

# Dead keys the merge drops (omdet/sam2/yolo detector path + translator). Not asserted.
DEAD = {"BG_SEG_MODEL", "SAM2_WEIGHTS", "CONF_BG", "DETECT_IMGSZ", "DEVICE",
        "TRANSLATOR", "XLATE_PORT", "TRANSLATE_PROMPT"}

_OVERRIDE_PREFIXES = ("SCENE_", "MVD_", "ASR_", "WATCHDOG_", "WEBCAM_", "VIDEO",
                      "CONTROL", "RECORD", "DESK_", "PHONE_IP")

def _clean_config():
    """Import config under an env cleared of launch overrides, so the surface yields the baked baseline
    the golden was captured at. Returns the reloaded surface module."""
    for k in list(os.environ):
        if k.startswith(_OVERRIDE_PREFIXES):
            os.environ.pop(k, None)
    import config
    return importlib.reload(config)

def resolved(cfg, video, control):
    """The active golden keys, read entirely through the config surface. wire_target()/video_input()
    take the scenario, so they need no env. This mirrors exactly what the app reads."""
    host, port, is_real = cfg.wire_target(control)
    return {
        "LLAMA_URL":      cfg.LLAMA_URL,
        "VLM_TIMEOUT":    cfg.VLM_TIMEOUT,
        "ASR_TOPIC":      cfg.ASR_TOPIC,
        "INPUT":          cfg.video_input(video),
        "CAM_W":          cfg.CAM_W,
        "CAM_H":          cfg.CAM_H,
        "CHAT_W":         cfg.CHAT_W,
        "HE_FONT_SIZE":   cfg.HE_FONT_SIZE,
        "OPEN_TIMEOUT":   cfg.OPEN_TIMEOUT,
        "READ_RETRY":     cfg.READ_RETRY,
        "TTS_BACKEND":    cfg.TTS_BACKEND,
        "TTS_HOST":       cfg.TTS_HOST,
        "TTS_PORT":       cfg.TTS_PORT,
        "TTS_LANG":       cfg.TTS_LANG,
        "TTS_RATE":       cfg.TTS_RATE,
        "TTS_TIMEOUT":    cfg.TTS_TIMEOUT,
        "TTS_MODEL":      cfg.TTS_MODEL,
        "TTS_PIPER_BIN":  cfg.TTS_PIPER_BIN,
        "TTS_SR":         cfg.TTS_SR,
        "TTS_ON":         cfg.TTS_ENABLED,
        "PHONE_ASR_ON":   cfg.PHONE_ASR_ENABLED,
        "PHONE_ASR_PORT": cfg.PHONE_ASR_PORT,
        "SEG":            cfg.SEG,
        "SAM3_PERIOD":    cfg.SAM3_PERIOD,
        "HL_GIVEUP":      cfg.HL_GIVEUP,
        "GATE":           cfg.GATE,
        "COUNT_FRAMES":   cfg.COUNT_FRAMES,
        "COUNT_GAP":      cfg.COUNT_GAP,
        "MIN_BOX_FRAC":   cfg.MIN_BOX_FRAC,
        "HL_TOPK":        cfg.HL_TOPK,
        "HL_MAX":         cfg.HL_MAX,
        "DETECT_FLOOR":   cfg.DETECT_FLOOR,
        "HL_CONF":        cfg.HL_CONF,
        "HL_REL":         cfg.HL_REL,
        "PLANNER":        "gemma4",
        "DRONE_ROUTER":   True,
        "WIRE_HOST":      host,
        "WIRE_REAL":      is_real,
        "WATCHDOG_STALL_SEC": cfg.WATCHDOG_STALL_SEC,
        "WATCHDOG_RETRY_SEC": cfg.WATCHDOG_RETRY_SEC,
    }

SCENARIOS = {"webcam_mock": ("webcam", "mock"), "dji_mock": ("dji", "mock"), "dji_real": ("dji", "real")}

def _restore(saved):
    os.environ.clear(); os.environ.update(saved)
    import config; importlib.reload(config)

def test_every_active_key_matches_golden_per_app_scenario():
    saved = dict(os.environ)
    try:
        cfg = _clean_config()
        diffs = []
        for name, (video, control) in SCENARIOS.items():
            r = resolved(cfg, video, control)
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
        assert not diffs, "config package changes behaviour:\n  " + "\n  ".join(diffs)
    finally:
        _restore(saved)

def test_no_active_golden_key_is_unmapped():
    saved = dict(os.environ)
    try:
        cfg = _clean_config()
        produced = set(resolved(cfg, "webcam", "mock"))
        missing = [k for k in GOLDEN["webcam_mock"] if k not in DEAD and k not in produced]
        assert not missing, f"golden keys not reproduced by the config surface: {missing}"
    finally:
        _restore(saved)
