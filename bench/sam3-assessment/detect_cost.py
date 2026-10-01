"""SAM3 detect() latency in the app's conditions (ruling C.2): SAM3 alone, with Gemma
loaded and idle, with Gemma busy on text requests, and with Gemma busy on vision
requests. Each condition runs a one-concept and a three-concept phrase (the app's
"dresser" fans out to three concepts, one forward each).

Replaces the method of bench/hebrew-command-bench/contention.py (saturation) with the
app's own modules: Sam3Backend, the supervisor's Gemma, perception2.vlm_client.ask.
GPU: ~6 min. Run: python3 bench/sam3-assessment/detect_cost.py"""
import threading
import time

import common
import config
from perception2 import vlm_client
from sam3.model import Sam3Backend

REPS = 16
COMMAND = "טוס קדימה חמישה מטרים ואז תסתובב ימינה"
QUESTION = "מה אתה רואה?"


def time_detects(sam3, frames, phrase):
    """REPS detects over the frames -> (ms list, hits list)."""
    out = []
    hits = []
    t0 = 0.0
    dets = []

    for i in range(REPS):
        t0 = time.perf_counter()
        _status, dets = sam3.detect(
            frames[i % len(frames)],
            phrase,
            conf=config.DETECT_FLOOR,
            topk=config.HL_TOPK
        )
        out.append(common.ms_since(t0))
        hits.append(len(dets))
    return out, hits


def text_load(gemma, frame):
    """One plan-sized text request, as the recognizer sends per command."""
    messages = [{"role": "user", "content": COMMAND}]
    gemma.request(messages, max_tokens=128, label="bench")
    return


def vision_load(gemma, frame):
    """One vision question with the frame, as perception2 sends for "describe"."""
    vlm_client.ask(gemma, frame, QUESTION, [])
    return


class Load:
    """Runs one Gemma request after another on a thread; counts them and times them."""

    def __init__(self, gemma, frame, request):
        self._stop = threading.Event()
        self._args = (gemma, frame)
        self._request = request
        self.ms = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        return

    def __enter__(self):
        self._thread.start()
        time.sleep(1.0)       # the first request is in flight before SAM3 starts
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        return False

    def _run(self):
        t0 = 0.0
        while not self._stop.is_set():
            t0 = time.perf_counter()
            self._request(*self._args)
            self.ms.append(common.ms_since(t0))
        return


def series(sam3, frames, sampler, label, results):
    """Both phrases under the current condition -> results[label]."""
    ms = []
    hits = []
    row = {}

    for name, phrase in (("one", common.PHRASE_ONE), ("three", common.PHRASE_THREE)):
        sampler.start()
        ms, hits = time_detects(sam3, frames, phrase)
        row[name] = common.stats(ms)
        row[name]["hits_p50"] = common.pct(hits, 50)
        row[name]["gpu"] = sampler.stop()
        print(f"{label:8s} {name:5s} {row[name]}", flush=True)
    results[label] = row
    return


def main():
    frames = common.frames(8)
    sampler = common.GpuSampler()
    results = {"gpu": sampler.name(), "reps": REPS, "frames": "desk x8, 1280x720"}
    sam3 = Sam3Backend()

    time_detects(sam3, frames, common.PHRASE_THREE)          # warm-up
    series(sam3, frames, sampler, "alone", results)
    noise_ms, _hits = time_detects(sam3, [common.noise_frame()], common.PHRASE_ONE)
    results["alone_noise_one"] = common.stats(noise_ms)
    print("noise one", results["alone_noise_one"], flush=True)

    with common.gemma_server() as gemma:
        text_load(gemma, frames[0])                          # warm-up
        vision_load(gemma, frames[0])
        series(sam3, frames, sampler, "idle", results)
        with Load(gemma, frames[0], text_load) as load:
            series(sam3, frames, sampler, "text", results)
        results["text_gemma_ms"] = common.stats(load.ms)
        with Load(gemma, frames[0], vision_load) as load:
            series(sam3, frames, sampler, "vision", results)
        results["vision_gemma_ms"] = common.stats(load.ms)
    common.write_result("detect-cost", results)
    return


if __name__ == "__main__":
    main()
