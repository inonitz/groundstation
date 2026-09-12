"""Capture layer (2026-09-12): trace.jsonl (one line per utterance) + causal clip-claim + per-request
perception dirs with one RAW frame + json per SAM3/Gemma pass. Model-agnostic (no burned boxes)."""
import os, sys, json, glob, tempfile, shutil
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mvd as SO


def _session():
    d = tempfile.mkdtemp(); os.environ["MVD_SESSION_DIR"] = d
    return d, SO.SessionLog()


def test_trace_line_and_causal_clip_claim():
    d, log = _session()
    # a clip exists in asr_clips before the transcript arrives (the C++ node wrote it first)
    open(os.path.join(d, "asr_clips", "audio_000000_x.wav"), "wb").close()
    log.begin("סמן את הגיטרות")
    assert log.cur_seq() == 0
    log.set(kind="highlight", target_en="guitars", action="perception(highlight: guitars)")
    log.commit()
    # clip claimed + renamed to the utterance seq
    assert os.path.isfile(os.path.join(d, "asr_clips", "utt_0000.wav"))
    assert not glob.glob(os.path.join(d, "asr_clips", "audio_*.wav"))
    line = json.loads(open(os.path.join(d, "trace.jsonl")).readline())
    assert line["seq"] == 0 and line["audio_clip"] == "asr_clips/utt_0000.wav"
    assert line["heard_he"] == "סמן את הגיטרות" and line["kind"] == "highlight"
    # trace.jsonl is at the root; the old utterances.jsonl must be gone
    assert not os.path.exists(os.path.join(d, "asr", "utterances.jsonl"))
    assert not os.path.exists(os.path.join(d, "utterances.jsonl"))
    shutil.rmtree(d, ignore_errors=True)


def test_reject_reason_in_trace():
    d, log = _session()
    log.begin("אל תזוז"); log.set(action="reject-neg-guard"); log.commit()
    line = json.loads(open(os.path.join(d, "trace.jsonl")).readline())
    assert "negation" in (line["reject_reason"] or "")
    shutil.rmtree(d, ignore_errors=True)


def test_per_request_dir_and_passes():
    d, log = _session()
    log.begin("כמה גיטרות"); log.begin_request("count", "guitars", query="count guitars")
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    log.save_pass(frame, log.det_payload([{"conf": 0.9, "box": (1, 2, 3, 4), "label": "guitar"}]), 412)
    log.save_pass(frame, log.det_payload([{"conf": 0.8, "box": (5, 6, 7, 8), "label": "guitar"}]), 430)
    log.end_request({"n": 2})
    rd = glob.glob(os.path.join(d, "perception", "0000-count-*"))
    assert len(rd) == 1, rd
    rd = rd[0]
    assert os.path.isfile(os.path.join(rd, "pass_00000.jpg")) and os.path.isfile(os.path.join(rd, "pass_00001.json"))
    req = json.load(open(os.path.join(rd, "request.json")))
    assert req["kind"] == "count" and req["verdict"] == {"n": 2} and req["passes"] == 2
    p0 = json.load(open(os.path.join(rd, "pass_00000.json")))
    assert p0["raw_dets"][0]["box"] == [1, 2, 3, 4] and p0["forward_ms"] == 412
    log.commit()
    assert json.loads(open(os.path.join(d, "trace.jsonl")).readline())["perception_dir"] == os.path.relpath(rd, d)
    shutil.rmtree(d, ignore_errors=True)


def test_begin_request_supersedes_open_one():
    d, log = _session()
    log.begin("סמן כיסא"); log.begin_request("highlight", "chair")
    log.save_pass(np.zeros((8, 8, 3), np.uint8), {"raw_dets": []})
    log.begin_request("highlight", "table")      # new request must close the chair one
    chair = glob.glob(os.path.join(d, "perception", "0000-highlight-chair"))[0]
    assert json.load(open(os.path.join(chair, "request.json")))["verdict"] == "superseded"
    shutil.rmtree(d, ignore_errors=True)


class _FakeBackend:
    def __init__(self): self.calls = 0
    def detect(self, frame, phrase, conf=0.3, topk=8):
        self.calls += 1; return [{"label": phrase, "conf": 0.9, "box": (1, 2, 3, 4)}]
    def mask_for_box(self, frame, box): return None


def test_detect_hook_saves_one_pass_per_fresh_forward():
    d, log = _session(); SO.SESSION = log
    log.begin("סמן גיטרה"); log.begin_request("highlight", "guitar")
    SO.OM["det"] = None
    detect, _mask, th = SO.build_highlight("sam3", eyes=None, loader=_FakeBackend); th.join(5)
    fr = np.zeros((16, 16, 3), np.uint8)
    detect(fr, "guitar", 0.1)                 # FRESH forward -> 1 pass
    detect(fr, "guitar", 0.1)                 # within SAM3_PERIOD -> cached, NO new pass
    rd = glob.glob(os.path.join(d, "perception", "0000-highlight-guitar"))[0]
    assert len(glob.glob(os.path.join(rd, "pass_*.jpg"))) == 1, os.listdir(rd)
    SO.OM["det"] = None; SO.SESSION = None
    shutil.rmtree(d, ignore_errors=True)


def test_ask_thread_saves_gemma_pass_and_closes():
    d, log = _session(); SO.SESSION = log
    SO.vlm.ask = lambda fr, q, h: ("a room with chairs", None, None, "a room")
    log.begin("מה אתה רואה"); log.begin_request("describe", "what do you see", query="what do you see")
    SO.TextHandler(None, voice=None)._ask_thread(np.zeros((16, 16, 3), np.uint8), "what do you see")
    rd = glob.glob(os.path.join(d, "perception", "0000-describe-*"))[0]
    assert os.path.isfile(os.path.join(rd, "pass_00000.jpg"))
    assert json.load(open(os.path.join(rd, "pass_00000.json")))["answer"] == "a room with chairs"
    assert json.load(open(os.path.join(rd, "request.json")))["verdict"]["spoken"] == "a room"
    SO.SESSION = None; shutil.rmtree(d, ignore_errors=True)
