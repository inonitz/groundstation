#!/usr/bin/env python3
"""Per-session recorder + perception capture for the live window. Crash-safe by design: each finished
utterance is appended to trace.jsonl as ONE flushed + fsynced JSON line, so an interrupt (Ctrl-C, power
loss) keeps every finished utterance and at worst drops the in-flight one -- never a half-written line.
Vision is captured per request as raw frames + json (model-agnostic; the replayer draws boxes). Audio
clips are renamed into place (atomic). sessions/ is gitignored.

Errors (phase 5 rewrite, 2026-09-22): every write returns a status. A failed write is logged and turns
the `recording` row red on the status pane; the next good write turns it green again. Once running, a
recording failure never crashes a live drone session, and it is never silent. At start-up the session
folder is required: an unwritable one dies (principle 2).
"""
import glob
import json
import os
import re
import socket
import threading
import time

import cv2

import config
from system.status import BOARD, FAILED, UP


def reject_why(action):
    """Plain reason for a rejection, so the operator can judge whether it was valid (owner 2026-09-12)."""
    a = action or ""
    if a.startswith("reject-neg-guard"):
        return "negation with no action (e.g. 'do not move')"
    if a.startswith("reject-numbers"):
        return "a number in the command did not match the plan"
    if a.startswith("reject-planner-echo"):
        return "the model echoed a built-in example, not a real plan"
    return "the model could not turn this into an action (drone-state question / greeting / out of scope)"


def _written(ok, what):
    """Report one write's status on the pane; log a failure. Returns ok."""
    if ok:
        BOARD.report("recording", UP)
    else:
        BOARD.report("recording", FAILED, f"could not write {what}")
    return ok


def _atomic_json(path, obj, indent=1):
    """Write JSON so a crash leaves either the old file or the new one, never a truncated mix: a temp
    file, fsync, then rename over the target (atomic on one filesystem). -> True when written."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:                          # the filesystem reports a failed write only by a throw
        print(f"[session] write failed: {path}: {e}", flush=True)
        return _written(False, os.path.basename(path))
    return _written(True, "")


def _atomic_imwrite(path, frame):
    """Same guarantee for a JPEG frame: a kill mid-encode cannot leave a truncated image. -> status."""
    tmp = path + ".tmp.jpg"
    if not cv2.imwrite(tmp, frame):               # cv2 reports a failed encode/write as False
        print(f"[session] image write failed: {path}", flush=True)
        return _written(False, os.path.basename(path))
    try:
        os.replace(tmp, path)
    except OSError as e:
        print(f"[session] image rename failed: {path}: {e}", flush=True)
        return _written(False, os.path.basename(path))
    return _written(True, "")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40]


class SessionLog:
    """ONE line per utterance in trace.jsonl: transcript, post-processed Hebrew, routing, verdict, spoken
    text, action + reject reason, timings. Audio clips: the C++ ASR node writes them into asr_clips/; on
    each transcript the newest unclaimed one is renamed utt_<seq>.wav. Vision: per REQUEST under
    perception/<seq>-<kind>-<slug>/, one RAW frame + json per SAM3 / Gemma pass.

    Threads: ASR callbacks (phone, ROS) call begin/set/commit; the vision thread and the Gemma thread call
    begin_request/save_pass/end_request, each in its OWN slot ("vision" / "describe") so they never close
    or write into each other's request (review R26). @_lock guards in-memory state (the sequence number,
    the slots, the claimed clips) and the one trace append; nothing inside it can throw past it. The
    current utterance is per-thread (@_tl): each ASR callback runs one utterance end to end."""

    def __init__(self, root=None):
        """The folder: MVD_SESSION_DIR when set (tests set it late), a new session-* folder under `root`
        when given, else config.SESSION_DIR -- the ONE folder the ASR server records into (review R9)."""
        exact = os.environ.get("MVD_SESSION_DIR")
        if exact:
            self.dir = exact
        elif root:
            self.dir = os.path.join(root, f"session-{time.strftime('%Y%m%d-%H%M%S')}-{socket.gethostname()}")
        else:
            self.dir = config.SESSION_DIR
        self.clips_dir = os.path.join(self.dir, "asr_clips")
        self.perc_dir = os.path.join(self.dir, "perception")
        self.tracepath = os.path.join(self.dir, "trace.jsonl")
        os.makedirs(self.clips_dir, exist_ok=True)       # creates self.dir too
        os.makedirs(self.perc_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._tl = threading.local()
        self._seq = -1
        self._claimed = set()
        self._reqs = {"vision": None, "describe": None}   # the open request per slot: {"dir", "i", "fields"}
        _atomic_json(os.path.join(self.dir, "meta.json"),
                     {"session": os.path.basename(self.dir), "host": socket.gethostname(),
                      "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "asr_backend": config.ASR_BACKEND, "asr_language": config.ASR_LANGUAGE,
                      "asr_model": config.ASR_MODEL_PATH, "segmenter": config.SEG, "planner": config.PLANNER},
                     indent=2)
        print(f"[mvd] session -> {self.dir}", flush=True)

    # ---------- per-utterance trace ----------
    def begin(self, heard, source="mic"):
        """Open this thread's utterance. Only a MIC utterance claims an audio clip: a phone transcript has
        none, and must not steal the mic's (review R27). The claim runs under the lock: no two claim one file."""
        with self._lock:
            self._seq += 1
            seq = self._seq
            clip = self._claim_clip(seq) if source == "mic" else None
        self._tl.rec = {"seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "epoch": round(time.time(), 3),
                        "source": source, "audio_clip": clip, "heard_he": heard, "he2": None, "flags": None,
                        "kind": None, "target_en": None, "mission": None, "vision_query": None,
                        "perception_dir": None, "verdict": None, "spoken": None, "action": None,
                        "reject_reason": None, "timings": {}}
        return

    def current(self):
        """This thread's open utterance record, or None."""
        return getattr(self._tl, "rec", None)

    def cur_seq(self):
        rec = self.current()
        return rec["seq"] if rec is not None else -1

    def set(self, **kw):
        rec = self.current()
        if rec is None:
            return
        if "action" in kw and "reject_reason" not in kw:
            action = str(kw["action"])
            kw["reject_reason"] = reject_why(action) if action.startswith("reject") else None
        rec.update(kw)
        return

    def commit(self):
        """Append this thread's utterance as ONE flushed + fsynced line. -> True when written."""
        rec = self.current()
        if rec is None:
            return True
        self._tl.rec = None
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with self._lock:
            ok = self._append(line)
        return _written(ok, "trace.jsonl")

    def _append(self, line):
        try:
            with open(self.tracepath, "a") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:                      # the filesystem reports a failed write only by a throw
            print(f"[session] trace write failed: {e}", flush=True)
            return False
        return True

    def _claim_clip(self, seq):
        """Causal claim: the C++ node writes+closes the clip before it publishes the transcript, so the
        newest unclaimed .wav in asr_clips/ is THIS utterance's. Rename it utt_<seq>.wav. Orphans (a failed
        transcription leaves an audio_*.wav) stay un-renamed and visible. -> the clip path, or None."""
        wavs = sorted(glob.glob(os.path.join(self.clips_dir, "audio_*.wav")), key=os.path.getmtime)
        cand = [w for w in wavs if w not in self._claimed]
        if not cand:
            return None
        dst = os.path.join(self.clips_dir, "utt_%04d.wav" % seq)
        try:
            os.rename(cand[-1], dst)
        except OSError as e:                      # the clip vanished or the disk refused the rename
            print(f"[session] clip claim failed: {e}", flush=True)
            _written(False, "the audio clip")
            return None
        self._claimed.add(dst)
        return os.path.relpath(dst, self.dir)

    # ---------- per-request / per-pass perception ----------
    @staticmethod
    def _slot(kind):
        return "describe" if kind == "describe" else "vision"

    def begin_request(self, kind, target, query=None):
        """Open a perception request dir in its slot (a still-open one in that slot closes as superseded).
        -> its relative path."""
        slot = self._slot(kind)
        self.end_request("superseded", slot=slot)
        seq = self.cur_seq()
        d = os.path.join(self.perc_dir, "%04d-%s-%s" % (seq, kind, _slug(target or kind) or kind))
        fields = {"seq": seq, "kind": kind, "target_en": target, "query": query,
                  "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": None}
        os.makedirs(d, exist_ok=True)
        with self._lock:
            self._reqs[slot] = {"dir": d, "i": 0, "fields": fields}
        _atomic_json(os.path.join(d, "request.json"), fields)
        rec = self.current()
        if rec is not None:
            rec.update(perception_dir=os.path.relpath(d, self.dir), vision_query=query, kind=kind, target_en=target)
        return os.path.relpath(d, self.dir)

    def save_pass(self, frame, payload, ms=None, slot="vision"):
        """One RAW frame + json for a single SAM3 forward or Gemma call, under the slot's open request."""
        with self._lock:
            req = self._reqs[slot]
            if req is None:
                return
            i = req["i"]
            req["i"] = i + 1
        if frame is not None:
            _atomic_imwrite(os.path.join(req["dir"], "pass_%05d.jpg" % i), frame)
        body = {"t": round(time.time(), 3), "forward_ms": ms}
        body.update(payload or {})
        _atomic_json(os.path.join(req["dir"], "pass_%05d.json" % i), body)
        return

    def end_request(self, verdict=None, slot="vision"):
        """Close the slot's open request: record its verdict and pass count (kept in memory, no re-read)."""
        with self._lock:
            req = self._reqs[slot]
            self._reqs[slot] = None
        if req is None:
            return
        fields = dict(req["fields"], verdict=verdict, passes=req["i"])
        _atomic_json(os.path.join(req["dir"], "request.json"), fields)
        return

    @staticmethod
    def det_payload(raw_dets):
        """Model-agnostic detection serialization for a pass (conf/box/label)."""
        return {"raw_dets": [{"conf": round(float(x.get("conf", 0.0)), 4), "box": [int(v) for v in x["box"]],
                              "label": x.get("label")} for x in (raw_dets or [])]}
