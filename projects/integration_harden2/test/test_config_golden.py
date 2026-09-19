"""Config surface smoke (golden-master RETIRED 2026-09-18). The value-comparison golden test was a
behaviour-preserving net for the config PACKAGE refactor; that job is done. With the surface now
deliberately evolving, the golden only rubber-stamped intended edits, so it is replaced by this light
import + surface-presence check. capture_golden_config.py and golden_config.json are retired with it."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def test_config_imports_and_exposes_its_surface():
    import config
    surface = ["LLAMA_URL","VLM_TIMEOUT","ASR_TOPIC","INPUT","CAM_W","CAM_H","CHAT_W","HE_FONT_PATH",
               "HE_FONT_SIZE","OPEN_TIMEOUT","READ_RETRY","TTS_BACKEND","TTS_PORT","TTS_LANG","SEG","GATE",
               "HL_REL","HL_GIVEUP","SAM3_PERIOD","COUNT_FRAMES","HL_TOPK","HL_MAX","DETECT_FLOOR","HL_CONF",
               "LLAMA_SERVER_PORT","PHONE_ASR_PORT","PHONE_ASR_ENABLED","WATCHDOG_STALL_SEC","WATCHDOG_RETRY_SEC",
               "PLANNER","ASR_MODEL_PATH","WIRE_HOST","WIRE_PORT","WIRE_REAL","SAM3_MODEL_DIR","SAM3_PRECISION"]
    missing = [s for s in surface if not hasattr(config, s)]
    assert not missing, f"config surface missing: {missing}"
    for fn in ("wire_target","video_input","resolve_device","default_gateway"):
        assert callable(getattr(config, fn, None)), f"config.{fn} not callable"

def test_wire_target_and_video_input_resolve():
    import config
    assert config.wire_target("mock") == ("127.0.0.1", 8079, False)
    assert config.video_input("webcam") == "0" and config.video_input("dji") == "ros"
