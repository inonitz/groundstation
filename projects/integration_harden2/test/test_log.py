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
    """REWRITTEN 2026-09-28 (owner D6 a): through SessionLog's own writes, not the
    underscore helper of log/disk.py. A request's JSON (Hebrew included) and a pass's
    JPEG + JSON are whole files, and no temp file stays behind."""
    d, log = _session()
    log.begin("סמן את הכוס")
    rel = log.begin_request("highlight", "cup", query="שלום")
    log.save_pass(np.zeros((8, 8, 3), np.uint8), {"n": 1})
    log.end_request({"present": True})
    req = os.path.join(d, rel)
    assert json.load(open(os.path.join(req, "request.json")))["query"] == "שלום"
    assert json.load(open(os.path.join(req, "pass_00000.json")))["n"] == 1
    assert open(os.path.join(req, "pass_00000.jpg"), "rb").read(2) == b"\xff\xd8"
    assert json.load(open(os.path.join(d, "meta.json")))["session"]
    assert glob.glob(os.path.join(d, "**", "*.tmp"), recursive=True) == []


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


# ==================== perf.py and perf_report.py ====================
def _perf_rows(folder):
    return [json.loads(line) for line in open(os.path.join(folder, "perf.jsonl"))]


def test_perf_buffers_every_event_and_writes_it_on_close(tmp_path):
    """REWRITTEN 2026-09-28 (owner ruling C.1, R7): events go to a memory buffer, not
    straight to disk. Was: test_perf_records_one_line_per_event_and_times_a_mark."""
    from log.perf import Perf
    perf = Perf(str(tmp_path))
    perf.record("gemma", 12.34, label="plan")
    perf.mark("ptt_release")
    assert perf.take_since("ptt_release") >= 0
    assert perf.take_since("ptt_release") is None          # a mark is used once
    assert not (tmp_path / "perf.jsonl").exists()          # buffered, not written yet
    perf.close()
    rows = _perf_rows(tmp_path)
    assert rows[0]["stage"] == "gemma" and rows[0]["ms"] == 12.3
    assert rows[0]["label"] == "plan"


def test_a_mark_moves_and_ends_with_its_fields(tmp_path):
    """C2: mark(ago_ms) starts a timing in the past (the push-to-talk release);
    move_mark hands it on (a highlight -> its box); end() records it once."""
    from log.perf import Perf
    perf = Perf(str(tmp_path))
    perf.mark("e2e", ago_ms=500, start="ptt")
    perf.move_mark("e2e", "e2e_box")
    perf.end("e2e", "e2e", end="command")                 # moved: nothing to end
    perf.end("e2e_box", "e2e", end="box")
    perf.end("e2e_box", "e2e", end="box")                 # a mark ends once
    perf.move_mark("nothing", "e2e_box")
    perf.close()
    rows = _perf_rows(tmp_path)
    assert [(r["stage"], r["start"], r["end"]) for r in rows] == [("e2e", "ptt", "box")]
    assert 500 <= rows[0]["ms"] < 1500


def test_the_writer_thread_writes_the_buffer_every_period(tmp_path, monkeypatch):
    import config
    from log.perf import Perf
    monkeypatch.setattr(config, "PERF_FLUSH_SECONDS", 0.05)
    perf = Perf(str(tmp_path))
    for i in range(3):
        perf.record("frame", i, read_ms=0, draw_ms=0, show_ms=0)
    deadline = time.monotonic() + 5
    while not (tmp_path / "perf.jsonl").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert [r["ms"] for r in _perf_rows(tmp_path)] == [0, 1, 2]   # in order, no close
    perf.record("frame", 3, read_ms=0, draw_ms=0, show_ms=0)
    perf.close()
    assert [r["ms"] for r in _perf_rows(tmp_path)] == [0, 1, 2, 3]


def test_die_writes_the_perf_buffer_before_every_other_cleanup(tmp_path):
    """C.1: a crash keeps its timings; perf goes first, even when the supervisor
    registered its cleanup earlier."""
    import textwrap
    code = textwrap.dedent(f'''
        import os, sys; sys.path.insert(0, {HARDEN2!r})
        from runtime.fatal import die, on_die
        from log.perf import Perf
        path = os.path.join({str(tmp_path)!r}, "perf.jsonl")
        on_die(lambda: print("WRITTEN BEFORE", os.path.exists(path), flush=True))
        perf = Perf({str(tmp_path)!r})
        perf.record("turn", 7.0, kind="flight")
        die("boom")
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 1 and "FATAL: boom" in r.stderr
    assert "WRITTEN BEFORE True" in r.stdout
    assert _perf_rows(tmp_path)[0]["kind"] == "flight"


def test_startup_records_each_row_when_it_is_first_up(tmp_path, monkeypatch):
    import config
    from log.perf import Perf
    from runtime.status import STARTING, UP
    monkeypatch.setattr(config, "PERF_STARTUP_POLL_SECONDS", 0.01)
    states = {"gemma": STARTING, "sam3": STARTING}
    perf = Perf(str(tmp_path))
    perf.watch_startup(lambda: [(n, s, "") for n, s in states.items()], time.monotonic())
    time.sleep(0.05)
    states["sam3"] = UP
    time.sleep(0.05)
    states["sam3"] = STARTING                  # a later restart is not a start-up
    states["gemma"] = UP
    time.sleep(0.05)
    states["sam3"] = UP
    time.sleep(0.05)
    perf.close()
    rows = [r["row"] for r in _perf_rows(tmp_path) if r["stage"] == "startup"]
    assert rows == ["sam3", "gemma", "every row"]


def test_the_gpu_sampler_records_memory_and_load(tmp_path, monkeypatch):
    import config
    import pytest
    from log.perf import Perf
    if shutil.which("nvidia-smi") is None:
        pytest.skip("no NVIDIA driver: no GPU samples by design")
    monkeypatch.setattr(config, "PERF_GPU_SAMPLE_SECONDS", 0.02)
    perf = Perf(str(tmp_path))
    perf.start_gpu_sampler()
    time.sleep(0.2)
    perf.close()
    gpu = [r for r in _perf_rows(tmp_path) if r["stage"] == "gpu"]
    assert gpu and gpu[0]["mem_mib"] > 0 and 0 <= gpu[0]["load_pct"] <= 100


def test_no_perf_records_nothing(tmp_path):
    from log.perf import NO_PERF
    NO_PERF.record("gemma", 1.0)
    NO_PERF.flush()
    assert list(tmp_path.iterdir()) == []


def test_the_perf_report_gives_percentiles_per_stage(tmp_path):
    """REWRITTEN 2026-09-28 (owner ruling C.1: n, min, P25, P50, P75, P95, P99, max; the
    frame is one event per frame): the frame row and the header changed."""
    from log.perf import Perf
    from log.perf_report import percentile, report
    perf = Perf(str(tmp_path))
    for ms in range(1, 101):
        perf.record("sam3", ms, wait_ms=ms / 2, priority=0)
    perf.record("frame", 30, read_ms=1, draw_ms=20, show_ms=9)
    perf.close()
    assert percentile(list(range(1, 101)), 50) == 50
    assert percentile(list(range(1, 101)), 95) == 95
    lines = report(str(tmp_path))
    text = "\n".join(lines)
    assert "min" in lines[1] and "P25" in lines[1] and "P99" in lines[1]
    sam3 = next(line for line in lines if line.startswith("sam3"))
    assert sam3.split() == ["sam3", "100", "1.0", "25.0", "50.0", "75.0", "95.0", "99.0",
                            "100.0"]
    assert "waiting for the lock" in text and "  draw" in text


def test_the_perf_report_lists_the_slowest_frames(tmp_path):
    """REWRITTEN 2026-09-28 (owner ruling V1 a: the 20 slowest frames with their times,
    no fps threshold). Was: test_the_perf_report_lists_the_slow_seconds."""
    from log.perf import Perf
    from log.perf_report import report
    perf = Perf(str(tmp_path))
    for gap in range(1, 31):
        perf.record("frame", gap, read_ms=gap / 2, draw_ms=1, show_ms=2)
    perf.record("frame", 270, read_ms=250, draw_ms=6, show_ms=7)
    perf.close()
    lines = report(str(tmp_path), slowest=20)
    at = next(i for i, line in enumerate(lines) if "slowest frames" in line)
    assert "the 20 slowest frames of 31" in lines[at]
    frames = lines[at + 2:]
    assert len(frames) == 20
    assert frames[0].split()[1:] == ["270.0", "250.0", "6.0", "7.0"]
    assert frames[-1].split()[1] == "12.0"            # 30 .. 12 follow the 270 ms one


def test_the_scripted_run_reads_sentences_and_waits(tmp_path):
    from scripted_e2e_run import read_script
    script = tmp_path / "s.txt"
    script.write_text("# a comment\nמה אתה רואה?\nwait 2.5\n\nטוס קדימה # inline\n")
    assert read_script(str(script)) == [
        ("say", "מה אתה רואה?"),
        ("wait", 2.5),
        ("say", "טוס קדימה"),
    ]


def test_the_scripted_run_refuses_anything_but_the_mock():
    """SAFETY: its sentences become commands. With CONTROL=real it dies before it
    waits for Gemma or publishes anything. The IP is a documentation address."""
    env = dict(os.environ, CONTROL="real", PHONE_IP="203.0.113.1")
    script = os.path.join(HARDEN2, "test", "scripted_e2e_run.py")
    r = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 1
    assert "it runs only with CONTROL=mock" in r.stderr
    assert "[feed]" not in r.stdout

