#!/usr/bin/env python3
"""Per-session recorder + perception capture for the live window. Crash-safe by
design: each finished utterance is appended to trace.jsonl as ONE flushed + fsynced
JSON line, so an interrupt (Ctrl-C, power loss) keeps every finished utterance and
at worst drops the in-flight one -- never a half-written line. Vision is captured
per request as raw frames + json (model-agnostic; the replayer draws boxes). Audio
clips are renamed into place (atomic). sessions/ is gitignored.

Errors (owner ruling 2026-09-23): the record only writes to the laptop's own
disk, so it has no status row and no recovery. At start-up the session folder
must be creatable and writable, or the app dies at once (principle 2). A
write that fails later means the disk itself is broken: the app dies with the
reason. A missing audio clip is not a disk failure: it is logged and skipped.
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
from system.fatal import die
from util.guarded import append_line, atomic_write, rename


def _written(ok, what):
    """A failed write means the laptop's disk is
    broken: die with the reason. Returns ok."""
    if not ok:
        die(
            f"the session record could not write {what}: "
            "the laptop disk refused a write"
        )
    return ok


def _writable_folder(path):
    """True when `path` exists and is writable, or its nearest existing parent is (so
    makedirs will succeed). A plain permission check: nothing throws."""
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    return os.path.isdir(probe) and os.access(probe, os.W_OK | os.X_OK)


def _atomic_json(path, obj, indent=1):
    """Write JSON atomically (util.guarded.atomic_write: the old file or the new one,
    never a truncated mix). A failed write dies (_written)."""
    data = json.dumps(obj, ensure_ascii=False, indent=indent).encode("utf-8")
    return _written(atomic_write(path, data), os.path.basename(path))


def _atomic_imwrite(path, frame):
    """The same guarantee for a JPEG frame: a kill mid-encode cannot leave a truncated
    image. cv2.imencode reports a failed encode as False, never a throw."""
    ok, jpeg = cv2.imencode(".jpg", frame)
    if not ok:
        print(f"[session] image encode failed: {path}", flush=True)
        return _written(False, os.path.basename(path))
    return _written(atomic_write(path, jpeg.tobytes()), os.path.basename(path))


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40]


def latest_session():
    """The newest session folder under config.SESSIONS_ROOT; die when there is none. The
    read-only tools (show.py, score.py) use this."""
    found = sorted(glob.glob(os.path.join(config.SESSIONS_ROOT, "session-*")))
    if not found:
        die(f"no session folder under {config.SESSIONS_ROOT}")
    return found[-1]


def _now():
    """The record's timestamp format."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def trace_file(root):
    """A session's per-utterance log: trace.jsonl (since 2026-09-12), else an older
    utterances.jsonl layout. The read-only tools (show.py, score.py) use this."""
    for name in ("trace.jsonl", "asr/utterances.jsonl", "utterances.jsonl"):
        path = os.path.join(root, *name.split("/"))
        if os.path.exists(path):
            return path
    return os.path.join(root, "trace.jsonl")


class SessionLog:
    """ONE line per utterance in trace.jsonl: transcript, post-processed Hebrew, routing,
    verdict, spoken text, action + reject reason, timings. Audio clips: the C++ ASR node
    writes them into asr_clips/; on each transcript the newest unclaimed one is renamed
    utt_<seq>.wav. Vision: per REQUEST under perception/<seq>-<kind>-<slug>/, one RAW
    frame + json per SAM3 / Gemma pass.

    Threads: ASR callbacks (phone, ROS) call begin/set/commit, and begin_request (the
    vision on_start runs on that thread); the vision task threads call
    save_pass/end_request, each in its OWN slot (the task id), so tasks never touch each
    other's record (R26).
    @_lock guards in-memory state (the sequence number, the slots, the claimed clips) and
    the one trace append; nothing inside it can throw past it. The current utterance is
    per-thread (@_tl): each ASR callback runs one utterance end to end."""

    def __init__(self, folder):
        """@folder: the session folder (the app passes config.SESSION_DIR, the ONE
        folder the ASR server records into; review R9)."""
        self.dir = folder
        self.clips_dir = os.path.join(self.dir, "asr_clips")
        self.perc_dir = os.path.join(self.dir, "perception")
        self.tracepath = os.path.join(self.dir, "trace.jsonl")

        # the start-up check (owner 2026-09-23)
        if not _writable_folder(self.dir):
            die(
                f"the session folder {self.dir} cannot be created or written: "
                "check its permissions"
            )
        os.makedirs(self.clips_dir, exist_ok=True)       # creates self.dir too
        os.makedirs(self.perc_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._tl = threading.local()
        self._seq = -1
        self._claimed = set()
        # the open request per slot: {"dir", "i", "fields"}
        self._reqs = {}          # slot -> the open request; a slot per vision task

        self._write_meta()
        print(f"[mvd] session -> {self.dir}", flush=True)

    def _write_meta(self):
        """meta.json: which session, which host, and which models ran."""
        _atomic_json(
            os.path.join(self.dir, "meta.json"),
            {
                "session": os.path.basename(self.dir),
                "host": socket.gethostname(),
                "started": _now(),
                "asr_backend": config.ASR_BACKEND,
                "asr_language": config.ASR_LANGUAGE,
                "asr_model": config.ASR_MODEL_PATH,
                "segmenter": config.SEG,
                "planner": config.PLANNER,
            },
            indent=2
        )
        return

    def close(self):
        """Every record is written (and fsynced) when it is made: nothing is left to
        flush."""
        return

    # ---------- per-utterance trace ----------
    def begin(self, heard, source="mic"):
        """Open this thread's utterance. Only a MIC utterance claims an audio clip: a
        phone transcript has none, and must not steal the mic's (review R27). The claim
        runs under the lock: no two claim one file."""
        with self._lock:
            self._seq += 1
            seq = self._seq
            clip = self._claim_clip(seq) if source == "mic" else None

        self._tl.rec = {
            "seq": seq,
            "ts": _now(),
            "epoch": round(time.time(), 3),
            "source": source,
            "audio_clip": clip,
            "heard_he": heard,
            "he2": None,
            "flags": None,
            "kind": None,
            "target_en": None,
            "mission": None,
            "vision_query": None,
            "perception_dir": None,
            "verdict": None,
            "spoken": None,
            "action": None,
            "reject_reason": None,
            "timings": {},
        }
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
        rec.update(kw)
        return

    def commit(self):
        """Append this thread's utterance as ONE flushed
        + fsynced line. -> True when written."""
        rec = self.current()
        if rec is None:
            return True

        self._tl.rec = None
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with self._lock:
            ok = append_line(self.tracepath, line)
        return _written(ok, "trace.jsonl")

    def _claim_clip(self, seq):
        """Causal claim: the C++ node writes+closes the clip before it publishes the
        transcript, so the newest unclaimed .wav in asr_clips/ is THIS utterance's.
        Rename it utt_<seq>.wav. Orphans (a failed transcription leaves an audio_*.wav)
        stay un-renamed and visible. -> the clip path, or None."""
        wavs = sorted(
            glob.glob(os.path.join(self.clips_dir, "audio_*.wav")),
            key=os.path.getmtime
        )
        cand = [w for w in wavs if w not in self._claimed]
        if not cand:
            return None

        dst = os.path.join(self.clips_dir, "utt_%04d.wav" % seq)
        # the clip vanished or the disk refused the rename: keep the utterance
        if not rename(cand[-1], dst):
            print("[session] clip claim failed: the utterance is kept without it",
                  flush=True)
            return None

        self._claimed.add(dst)
        return os.path.relpath(dst, self.dir)

    # ---------- per-request / per-pass perception ----------
    @staticmethod
    def _slot(kind):
        return "describe" if kind == "describe" else "vision"

    def begin_request(self, kind, target, query=None, slot=None):
        """Open a perception request dir in its slot (a still-open one in that slot
        closes as superseded). @slot: the vision task id (one slot per task, so tasks
        that overlap never write into each other's record); None = the kind's default
        slot. -> its relative path."""
        slot = self._slot(kind) if slot is None else slot
        self.end_request("superseded", slot=slot)

        seq = self.cur_seq()
        d = os.path.join(
            self.perc_dir,
            "%04d-%s-%s" % (seq, kind, _slug(target or kind) or kind)
        )
        fields = {
            "seq": seq,
            "kind": kind,
            "target_en": target,
            "query": query,
            "started": _now(),
            "verdict": None,
        }
        os.makedirs(d, exist_ok=True)
        with self._lock:
            self._reqs[slot] = {"dir": d, "i": 0, "fields": fields}
        _atomic_json(os.path.join(d, "request.json"), fields)

        # the utterance record points at this request
        rec = self.current()
        if rec is not None:
            rec.update(
                perception_dir=os.path.relpath(d, self.dir),
                vision_query=query,
                kind=kind,
                target_en=target
            )
        return os.path.relpath(d, self.dir)

    def save_pass(self, frame, payload, ms=None, slot="vision"):
        """One RAW frame + json for a single SAM3 forward
        or Gemma call, under the slot's open request."""
        with self._lock:
            req = self._reqs.get(slot)
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
        """Close the slot's open request: record its verdict
        and pass count (kept in memory, no re-read)."""
        with self._lock:
            req = self._reqs.pop(slot, None)
        if req is None:
            return
        fields = dict(req["fields"], verdict=verdict, passes=req["i"])
        _atomic_json(os.path.join(req["dir"], "request.json"), fields)
        return

    @staticmethod
    def det_payload(raw_dets):
        """Model-agnostic detection serialization for a pass (conf/box/label)."""
        dets = []
        for x in raw_dets or []:
            dets.append({
                "conf": round(float(x.get("conf", 0.0)), 4),
                "box": [int(v) for v in x["box"]],
                "label": x.get("label"),
            })
        return {"raw_dets": dets}
