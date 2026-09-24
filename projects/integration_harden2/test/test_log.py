"""Tests for log/: session.py (the recording). Crash safety (a SIGKILL never
leaves a torn file), the trace line per utterance with its audio clip, and the
per-request perception dirs with their passes."""
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import log.session as SL

HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


def _session():
    d = tempfile.mkdtemp()
    return d, SL.SessionLog(d)


def test_committed_utterances_are_durable_and_complete():
    d, log = _session()
    for i in range(5):
        log.begin(f"heard {i}")
        log.set(kind="describe", action="perception(describe)")
        log.commit()
    lines = open(os.path.join(d, "trace.jsonl")).read().splitlines()
    assert len(lines) == 5
    seqs = [json.loads(ln)["seq"] for ln in lines]   # every line must parse
    assert seqs == [0, 1, 2, 3, 4]


def test_atomic_json_leaves_no_tmp_and_valid_file():
    d, _ = _session()
    p = os.path.join(d, "x.json")
    SL._atomic_json(p, {"a": 1, "ב": "שלום"})
    assert json.load(open(p))["ב"] == "שלום"
    assert not os.path.exists(p + ".tmp")           # temp renamed away, not left behind


def test_perception_pairing_after_clean_request():
    d, log = _session()
    log.begin("heard")
    log.begin_request("highlight", "outlet", query="highlight outlet")
    log.save_pass(
        np.zeros((8, 8, 3), "uint8"),
        log.det_payload([{"conf": 0.9, "box": (1, 2, 3, 4), "label": "x"}])
    )
    log.save_pass(
        np.zeros((8, 8, 3), "uint8"),
        log.det_payload([{"conf": 0.8, "box": (5, 6, 7, 8), "label": "y"}])
    )
    log.end_request({"present": True})
    log.commit()
    rdir = glob.glob(os.path.join(d, "perception", "*"))[0]
    req = json.load(open(os.path.join(rdir, "request.json")))
    jpgs = sorted(glob.glob(os.path.join(rdir, "pass_*.jpg")))
    jsons = sorted(glob.glob(os.path.join(rdir, "pass_*.json")))
    assert req["passes"] == 2 and len(jpgs) == 2 and len(jsons) == 2


def test_sigkill_mid_session_leaves_no_partial_or_corrupt_file(tmp_path):
    """Spawn a writer, SIGKILL it mid-flight, then prove the recording is
    readable: every trace line parses, and every meta/request/pass json parses. A
    lingering *.tmp is fine (it is never read)."""
    sdir = str(tmp_path / "sess")
    child = f'''
import os, sys, time
sys.path.insert(0, {HARDEN2!r})
import numpy as np
from log.session import SessionLog
log = SessionLog({sdir!r})
i = 0
while True:
    log.begin("heard %d" % i)
    log.set(kind="highlight", target_en="obj%d" % i, action="highlight")
    log.begin_request("highlight", "obj%d" % i, query="highlight obj%d" % i)
    det = {{"conf": 0.9, "box": (1, 2, 3, 4), "label": "x"}}
    log.save_pass(np.zeros((8, 8, 3), "uint8"), log.det_payload([det]))
    log.end_request({{"present": True}})
    log.commit()
    i += 1
    time.sleep(0.003)
'''
    proc = subprocess.Popen([sys.executable, "-c", child])
    tp = os.path.join(sdir, "trace.jsonl")
    # a loaded machine can take seconds to import the child
    deadline = time.time() + 20.0
    while not os.path.exists(tp) and time.time() < deadline:
        time.sleep(0.05)
    # then let it write a batch of utterances mid-flight
    time.sleep(0.3)
    proc.send_signal(signal.SIGKILL)     # hardest possible interrupt -- no cleanup runs
    proc.wait(timeout=5)

    assert os.path.exists(tp), "no trace written at all"
    lines = open(tp).read().splitlines()
    assert len(lines) >= 1
    for ln in lines:
        # MUST parse -- a half-written tail line would raise here
        json.loads(ln)
    # every real metadata file must be valid JSON (atomic write
    # guarantees old-or-new, never torn)
    for jf in glob.glob(os.path.join(sdir, "**", "*.json"), recursive=True):
        if jf.endswith(".tmp"):
            continue
        json.load(open(jf))


def test_trace_line_and_causal_clip_claim():
    d, log = _session()
    # a clip exists in asr_clips before the transcript arrives
    # (the C++ node wrote it first)
    open(os.path.join(d, "asr_clips", "audio_000000_x.wav"), "wb").close()
    log.begin("סמן את הגיטרות")
    assert log.cur_seq() == 0
    log.set(
        kind="highlight", target_en="guitars", action="perception(highlight: guitars)"
    )
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
    """The recognizer passes the reason (it words its own rejects); the log records
    it."""
    d, log = _session()
    log.begin("אל תזוז")
    log.set(action="reject-neg-guard", reject_reason="negation with no action")
    log.commit()
    line = json.loads(open(os.path.join(d, "trace.jsonl")).readline())
    assert "negation" in (line["reject_reason"] or "")
    shutil.rmtree(d, ignore_errors=True)


def test_per_request_dir_and_passes():
    d, log = _session()
    log.begin("כמה גיטרות")
    log.begin_request("count", "guitars", query="count guitars")
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    log.save_pass(
        frame,
        log.det_payload([{"conf": 0.9, "box": (1, 2, 3, 4), "label": "guitar"}]),
        412
    )
    log.save_pass(
        frame,
        log.det_payload([{"conf": 0.8, "box": (5, 6, 7, 8), "label": "guitar"}]),
        430
    )
    log.end_request({"n": 2})
    rd = glob.glob(os.path.join(d, "perception", "0000-count-*"))
    assert len(rd) == 1, rd
    rd = rd[0]
    assert (
        os.path.isfile(os.path.join(rd, "pass_00000.jpg"))
        and os.path.isfile(os.path.join(rd, "pass_00001.json"))
    )
    req = json.load(open(os.path.join(rd, "request.json")))
    assert req["kind"] == "count" and req["verdict"] == {"n": 2} and req["passes"] == 2
    p0 = json.load(open(os.path.join(rd, "pass_00000.json")))
    assert p0["raw_dets"][0]["box"] == [1, 2, 3, 4] and p0["forward_ms"] == 412
    log.commit()
    assert (
        json.loads(open(os.path.join(d, "trace.jsonl")).readline())["perception_dir"]
        == os.path.relpath(rd, d)
    )
    shutil.rmtree(d, ignore_errors=True)


def test_begin_request_supersedes_open_one():
    d, log = _session()
    log.begin("סמן כיסא")
    log.begin_request("highlight", "chair")
    log.save_pass(np.zeros((8, 8, 3), np.uint8), {"raw_dets": []})
    log.begin_request("highlight", "table")      # new request must close the chair one
    chair = glob.glob(os.path.join(d, "perception", "0000-highlight-chair"))[0]
    assert (
        json.load(open(os.path.join(chair, "request.json")))["verdict"] == "superseded"
    )
    shutil.rmtree(d, ignore_errors=True)


def test_meta_json_is_written_at_start():
    """R14: the session's meta.json (host, ASR, model, planner) exists after start-up."""
    d, _ = _session()
    meta = json.load(open(os.path.join(d, "meta.json")))
    assert meta["host"] and meta["planner"] and meta["asr_model"]


# ==================== failures: start-up check, then die ====================
def _run_child(body, tmp_path):
    code = (f"import os, sys; sys.path.insert(0, {HARDEN2!r})\n"
            f"FOLDER = {str(tmp_path / 'sess')!r}\n" + body +
            "\nprint('STILL RUNNING', flush=True)\n")
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )


def test_an_uncreatable_session_folder_dies_at_start(tmp_path):
    """The folder cannot be made: its parent is a plain FILE
    (this fails for root too)."""
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    body = (f"FOLDER = {str(blocker / 'sess')!r}\n"
            "from log.session import SessionLog\nSessionLog(FOLDER)")
    r = _run_child(body, tmp_path)
    assert r.returncode != 0 and "STILL RUNNING" not in r.stdout
    assert "cannot be created or written" in r.stderr


def test_a_failed_write_later_means_a_broken_disk_and_dies(tmp_path):
    body = ("from log.session import SessionLog\nlog = SessionLog(FOLDER)\n"
            # a directory: the append must fail
            "log.tracepath = log.dir\n"
            "log.begin('heard')\nlog.commit()")
    r = _run_child(body, tmp_path)
    assert r.returncode != 0 and "STILL RUNNING" not in r.stdout
    assert "the session record could not write trace.jsonl" in r.stderr


def test_a_missing_audio_clip_is_skipped_not_fatal():
    d, log = _session()
    # no clip in asr_clips/: nothing to claim
    log.begin("heard")
    assert log.current()["audio_clip"] is None
    assert log.commit() is True


def test_end_request_records_verdict_and_passes_without_rereading():
    d, log = _session()
    log.begin("x")
    log.begin_request("count", "chairs")
    rd = os.path.join(d, log.current()["perception_dir"])
    os.remove(os.path.join(rd, "request.json"))          # nothing on disk to re-read
    log.save_pass(np.zeros((8, 8, 3), np.uint8), {"raw_dets": []})
    log.end_request({"n": 1})
    req = json.load(open(os.path.join(rd, "request.json")))
    assert (
        req["verdict"] == {"n": 1}
        and req["passes"] == 1
        and req["target_en"] == "chairs"
    )


def test_current_is_per_thread():
    import threading
    d, log = _session()
    log.begin("main thread")
    seen = []
    t = threading.Thread(target=lambda: seen.append(log.current()))
    t.start()
    t.join()
    assert seen == [None] and log.current()["heard_he"] == "main thread"


def test_vision_and_describe_requests_never_touch_each_other():
    """R26: the SAM3 thread and the Gemma thread each have their own open request."""
    d, log = _session()
    log.begin("x")
    log.begin_request("highlight", "cup")
    # must NOT supersede the highlight
    log.begin_request("describe", "what do you see")
    # a SAM3 refresh pass
    log.save_pass(np.zeros((8, 8, 3), np.uint8), {"raw_dets": []})
    # the Gemma pass
    log.save_pass(np.zeros((8, 8, 3), np.uint8), {"answer": "a cup"}, slot="describe")
    # the highlight gives up: vision slot only
    log.end_request({"gave_up": True})
    log.end_request({"answer": "a cup"}, slot="describe")
    hl = json.load(open(
        glob.glob(os.path.join(d, "perception", "*-highlight-cup", "request.json"))[0]
    ))
    ds = json.load(open(
        glob.glob(os.path.join(d, "perception", "*-describe-*", "request.json"))[0]
    ))
    assert hl["verdict"] == {"gave_up": True} and hl["passes"] == 1
    assert ds["verdict"] == {"answer": "a cup"} and ds["passes"] == 1


def test_only_a_mic_utterance_claims_the_audio_clip():
    """R27: a phone transcript has no audio and must not steal the mic's clip."""
    d, log = _session()
    open(os.path.join(d, "asr_clips", "audio_000001_x.wav"), "wb").close()
    log.begin("from the phone", source="phone")
    assert log.current()["audio_clip"] is None
    log.commit()
    log.begin("from the mic", source="mic")
    assert log.current()["audio_clip"] == "asr_clips/utt_0001.wav"
