#!/usr/bin/env python3
"""Per-session recorder + perception capture for the live scene window. Crash-safe by design: each
completed utterance is appended to trace.jsonl as one fsync-free but flushed JSON line, so an interrupt
(Ctrl-C, power loss) keeps every utterance that finished and at worst drops the in-flight one -- never a
half-written line. Vision is captured per request as raw frames + json (model-agnostic; the replayer
draws boxes). Audio clips are renamed into place (atomic). sessions/ is gitignored."""
import os, time, json, threading
import cv2


def reject_why(action):
    """Plain reason for a rejection, so the operator can judge whether it was valid (owner 2026-09-12)."""
    a = action or ""
    if a.startswith("reject-neg-guard"):     return "negation with no action (e.g. 'do not move')"
    if a.startswith("reject-numbers"):       return "a number in the command did not match the plan"
    if a.startswith("reject-planner-echo"):  return "the model echoed a built-in example, not a real plan"
    return "the model could not turn this into an action (drone-state question / greeting / out of scope)"


def _atomic_json(path, obj, indent=1):
    """Write JSON so a crash leaves either the old file or the new one, never a truncated mix:
    write a temp file, fsync it, then rename over the target (rename is atomic on one filesystem)."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_imwrite(path, frame):
    """Same guarantee for a JPEG frame: a kill mid-encode cannot leave a truncated image."""
    tmp = path + ".tmp.jpg"
    if cv2.imwrite(tmp, frame):
        os.replace(tmp, path)


class SessionLog:
    """ONE line per utterance in trace.jsonl (retires utterances.jsonl): transcript, post-processed
    Hebrew, routing, verdict, spoken text, action + reject reason, and timings. Audio clips live in
    asr_clips/ -- the C++ ASR node writes them, and on each transcript we causal-claim the newest and
    rename it to utt_<seq>.wav. Vision is captured per REQUEST under perception/<seq>-<kind>-<slug>/ as
    one RAW frame + json per SAM3/Gemma pass (no burned-in boxes; the replayer draws them)."""

    def __init__(self, root=None):
        import socket
        host = socket.gethostname()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        exact = os.environ.get("MVD_SESSION_DIR")
        self.dir = exact or os.path.join(root or os.path.join(os.path.dirname(__file__), "..", "..", "logs", "sessions"),
                                         f"session-{stamp}-{host}")
        os.makedirs(self.dir, exist_ok=True)
        self.clips_dir = os.path.join(self.dir, "asr_clips"); os.makedirs(self.clips_dir, exist_ok=True)
        self.perc_dir  = os.path.join(self.dir, "perception"); os.makedirs(self.perc_dir, exist_ok=True)
        self.tracepath = os.path.join(self.dir, "trace.jsonl")
        self._lock = threading.Lock()
        self._tl = threading.local()
        self._seq = -1
        self._claimed = set()
        self._req = None                 # current perception request: {"dir","i","seq"}
        try:
            _atomic_json(os.path.join(self.dir, "meta.json"),
                         {"session": os.path.basename(self.dir), "host": host,
                          "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                          "asr_backend": os.environ.get("ASR_BACKEND", ""),
                          "asr_language": os.environ.get("ASR_LANGUAGE", ""),
                          "asr_model": os.environ.get("ASR_MODEL_PATH", ""),
                          "segmenter": os.environ.get("SCENE_SEG", "sam3"),
                          "planner": os.environ.get("MVD_PLANNER", "gemma4")}, indent=2)
        except Exception:
            pass
        print(f"[mvd] session -> {self.dir}", flush=True)

    # ---------- per-utterance trace ----------
    def begin(self, heard, source="local"):
        with self._lock:
            self._seq += 1; seq = self._seq
        clip = self._claim_clip(seq)
        self._tl.rec = {"seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "epoch": round(time.time(), 3),
                        "source": source, "audio_clip": clip, "heard_he": heard, "he2": None, "flags": None,
                        "kind": None, "target_en": None, "mission": None, "vision_query": None,
                        "perception_dir": None, "verdict": None, "spoken": None, "action": None,
                        "reject_reason": None, "timings": {}}

    def cur_seq(self):
        rec = getattr(self._tl, "rec", None)
        return rec["seq"] if rec is not None else -1

    def set(self, **kw):
        rec = getattr(self._tl, "rec", None)
        if rec is None:
            return
        if "action" in kw and "reject_reason" not in kw:
            a = str(kw["action"])
            kw["reject_reason"] = reject_why(a) if a.startswith("reject") else None
        rec.update(kw)

    def commit(self):
        rec = getattr(self._tl, "rec", None)
        if rec is None:
            return
        self._tl.rec = None
        try:
            with self._lock:
                with open(self.tracepath, "a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush(); os.fsync(f.fileno())
        except Exception as e:
            print("[mvd] trace write failed:", e, flush=True)

    def _claim_clip(self, seq):
        """Causal claim: the C++ node writes+closes the clip before it publishes the transcript, so the
        newest unclaimed .wav in asr_clips/ is THIS utterance's. Rename to utt_<seq>.wav. Orphans (a failed
        transcription leaves an audio_*.wav) stay un-renamed and visible."""
        import glob
        try:
            cand = [w for w in sorted(glob.glob(os.path.join(self.clips_dir, "*.wav")), key=os.path.getmtime)
                    if not os.path.basename(w).startswith("utt_") and w not in self._claimed]
            if not cand:
                return None
            newest = cand[-1]
            dst = os.path.join(self.clips_dir, "utt_%04d.wav" % seq)
            os.rename(newest, dst); self._claimed.add(dst)
            return os.path.relpath(dst, self.dir)
        except Exception as e:
            print("[mvd] clip claim failed:", e, flush=True); return None

    # ---------- per-request / per-pass perception ----------
    def begin_request(self, kind, target, he2=None, query=None):
        """Open a perception request dir (closes any still-open one). seq = the current utterance's."""
        import re as _re
        self.end_request("superseded")
        try:
            seq = self.cur_seq()
            slug = _re.sub(r"[^a-z0-9]+", "_", (target or kind or "").lower()).strip("_")[:40] or kind
            d = os.path.join(self.perc_dir, "%04d-%s-%s" % (seq, kind, slug))
            os.makedirs(d, exist_ok=True)
            with self._lock:
                self._req = {"dir": d, "i": 0, "seq": seq}
            _atomic_json(os.path.join(d, "request.json"),
                         {"seq": seq, "kind": kind, "target_en": target, "he2": he2, "query": query,
                          "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": None})
            rec = getattr(self._tl, "rec", None)
            if rec is not None:
                rec["perception_dir"] = os.path.relpath(d, self.dir); rec["vision_query"] = query
                rec["kind"] = kind; rec["target_en"] = target
            return os.path.relpath(d, self.dir)
        except Exception as e:
            print("[mvd] begin_request failed:", e, flush=True); return None

    def save_pass(self, frame, payload, ms=None):
        """One RAW frame + json for a single SAM3 forward or Gemma VLM call, under the open request."""
        try:
            with self._lock:
                req = self._req
                if req is None:
                    return
                i = req["i"]; req["i"] = i + 1; d = req["dir"]
            if frame is not None:
                _atomic_imwrite(os.path.join(d, "pass_%05d.jpg" % i), frame)
            body = {"t": round(time.time(), 3), "forward_ms": ms}
            body.update(payload or {})
            _atomic_json(os.path.join(d, "pass_%05d.json" % i), body)
        except Exception as e:
            print("[mvd] save_pass failed:", e, flush=True)

    def end_request(self, verdict=None):
        try:
            with self._lock:
                req = self._req; self._req = None
            if req is None:
                return
            rp = os.path.join(req["dir"], "request.json")
            try:
                j = json.load(open(rp))
            except Exception:
                j = {}
            j["verdict"] = verdict; j["passes"] = req["i"]
            _atomic_json(rp, j)
        except Exception as e:
            print("[mvd] end_request failed:", e, flush=True)

    @staticmethod
    def det_payload(raw_dets, kept_dets=None, present=None):
        """Model-agnostic detection serialization for a pass (conf/box/label)."""
        def _d(ds):
            return [{"conf": round(float(x.get("conf", 0.0)), 4), "box": [int(v) for v in x["box"]],
                     "label": x.get("label")} for x in (ds or [])]
        p = {"raw_dets": _d(raw_dets)}
        if kept_dets is not None:
            p["kept_dets"] = _d(kept_dets)
        if present is not None:
            p["present"] = bool(present)
        return p
