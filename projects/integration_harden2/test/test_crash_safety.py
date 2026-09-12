"""Crash safety (2026-09-12): a hard interrupt outdoors (Ctrl-C, power loss, force-quit) must never
leave the recording corrupt. The contract: every COMMITTED utterance is durable, every line in
trace.jsonl is complete valid JSON, and no metadata file (meta/request/pass) is ever a truncated mix.
At worst one in-flight utterance is lost -- that is the design limit, not corruption."""
import os, sys, json, glob, time, signal, tempfile, subprocess
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import session_log as SL

HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


def _session():
    d = tempfile.mkdtemp(); os.environ["MVD_SESSION_DIR"] = d
    return d, SL.SessionLog()


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
    log.begin("heard"); log.begin_request("highlight", "outlet", query="highlight outlet")
    log.save_pass(np.zeros((8, 8, 3), "uint8"), log.det_payload([{"conf": 0.9, "box": (1, 2, 3, 4), "label": "x"}]))
    log.save_pass(np.zeros((8, 8, 3), "uint8"), log.det_payload([{"conf": 0.8, "box": (5, 6, 7, 8), "label": "y"}]))
    log.end_request({"present": True}); log.commit()
    rdir = glob.glob(os.path.join(d, "perception", "*"))[0]
    req = json.load(open(os.path.join(rdir, "request.json")))
    jpgs = sorted(glob.glob(os.path.join(rdir, "pass_*.jpg")))
    jsons = sorted(glob.glob(os.path.join(rdir, "pass_*.json")))
    assert req["passes"] == 2 and len(jpgs) == 2 and len(jsons) == 2


def test_sigkill_mid_session_leaves_no_partial_or_corrupt_file(tmp_path):
    """Spawn a writer, SIGKILL it mid-flight, then prove the recording is readable: every trace line
    parses, and every meta/request/pass json parses. A lingering *.tmp is fine (it is never read)."""
    sdir = str(tmp_path / "sess")
    child = f'''
import os, sys, time
sys.path.insert(0, {HARDEN2!r})
os.environ["MVD_SESSION_DIR"] = {sdir!r}
import numpy as np
from session_log import SessionLog
log = SessionLog()
i = 0
while True:
    log.begin("heard %d" % i)
    log.set(kind="highlight", target_en="obj%d" % i, action="highlight")
    log.begin_request("highlight", "obj%d" % i, query="highlight obj%d" % i)
    log.save_pass(np.zeros((8,8,3),"uint8"), log.det_payload([{{"conf":0.9,"box":(1,2,3,4),"label":"x"}}]))
    log.end_request({{"present": True}})
    log.commit()
    i += 1
    time.sleep(0.003)
'''
    proc = subprocess.Popen([sys.executable, "-c", child])
    time.sleep(0.6)                      # let it write a batch of utterances
    proc.send_signal(signal.SIGKILL)     # hardest possible interrupt -- no cleanup runs
    proc.wait(timeout=5)

    tp = os.path.join(sdir, "trace.jsonl")
    assert os.path.exists(tp), "no trace written at all"
    lines = open(tp).read().splitlines()
    assert len(lines) >= 1
    for ln in lines:
        json.loads(ln)                   # MUST parse -- a half-written tail line would raise here
    # every real metadata file must be valid JSON (atomic write guarantees old-or-new, never torn)
    for jf in glob.glob(os.path.join(sdir, "**", "*.json"), recursive=True):
        if jf.endswith(".tmp"):
            continue
        json.load(open(jf))


if __name__ == "__main__":
    test_committed_utterances_are_durable_and_complete()
    test_atomic_json_leaves_no_tmp_and_valid_file()
    test_perception_pairing_after_clean_request()
    import pytest; raise SystemExit(pytest.main([__file__, "-q"]))
