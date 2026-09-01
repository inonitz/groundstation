#!/usr/bin/env python3
"""
notify.py -- "tell me when a person matching <attributes> enters the scene" (integration_notify).

The background detector already emits COCO 'person' boxes every frame. This module sits on top:
  persons -> [tracker -> STABLE ids] -> a NEW confirmed id -> ONE cropped VLM attribute query
  (async) -> match -> notify (chat + TTS + highlight).

Why stable ids, not person-count: count misses simultaneous swaps, flickers under occlusion, and
can't localize or dedup the new entrant. A stable id catches swaps, rides occlusion, crops the VLM
to the right person, and dedups (fire once per id). The tracker is SWAPPABLE (NOTIFY_TRACKER=iou|osnet);
OSNet adds appearance embeddings so a person keeps their id across occlusion + re-entry (the true
"new person" semantic). IoU is the dependency-free fallback that is guaranteed to run.

No flight control here -- perception only.
"""
import os, threading
import numpy as np


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0: return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _l2(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class _Track:
    __slots__ = ("id", "box", "hits", "misses", "fired")
    def __init__(self, tid, box):
        self.id = tid; self.box = box; self.hits = 1; self.misses = 0; self.fired = False


class IoUTracker:
    """Greedy IoU association, no appearance. A track becomes a 'new entrant' once it survives
    >= min_hits frames (debounce vs detector flicker). Re-entry after a track dies gets a NEW id --
    the exact limitation OSNetTracker removes."""
    def __init__(self, iou_thr=0.3, min_hits=3, max_misses=15):
        self.iou_thr = float(os.environ.get("NOTIFY_IOU_THR", iou_thr))
        self.min_hits = int(os.environ.get("NOTIFY_MIN_HITS", min_hits))
        self.max_misses = int(os.environ.get("NOTIFY_MAX_MISSES", max_misses))
        self.tracks = {}; self._next = 1

    def update(self, boxes, frame=None):
        tracks = list(self.tracks.values())
        used_t, used_b = set(), set()
        pairs = []
        for ti, t in enumerate(tracks):
            for bi, b in enumerate(boxes):
                v = _iou(t.box, b)
                if v >= self.iou_thr: pairs.append((v, ti, bi))
        pairs.sort(reverse=True, key=lambda p: p[0])
        for v, ti, bi in pairs:
            if ti in used_t or bi in used_b: continue
            used_t.add(ti); used_b.add(bi)
            t = tracks[ti]; t.box = boxes[bi]; t.hits += 1; t.misses = 0
        for ti, t in enumerate(tracks):
            if ti not in used_t:
                t.misses += 1
                if t.misses > self.max_misses: self.tracks.pop(t.id, None)
        for bi, b in enumerate(boxes):
            if bi not in used_b:
                self.tracks[self._next] = _Track(self._next, b); self._next += 1
        out = []
        for t in self.tracks.values():
            out.append((t.id, t.box, (not t.fired) and t.hits >= self.min_hits))
        return out

    def mark_fired(self, tid):
        t = self.tracks.get(tid)
        if t: t.fired = True


class OSNetTracker:
    """IoU association + OSNet appearance embeddings + a persistent gallery, so a person who leaves
    and RE-ENTERS is re-identified (same id, not a false 'new person') and id survives occlusion
    crossings. Lazy-loads torchreid only when selected. Measured cost: ~9MB VRAM, ~0.7ms/person --
    negligible next to the ~1.2s VLM. reid_thr is tunable (NOTIFY_REID_THR)."""
    def __init__(self, iou_thr=0.3, min_hits=3, max_misses=30, reid_thr=0.6, device=None):
        self.base = IoUTracker(iou_thr, min_hits, max_misses)
        self.reid_thr = float(os.environ.get("NOTIFY_REID_THR", reid_thr))
        self.gallery = {}
        self._device = device
        self._load()

    def _load(self):
        import torch, torchreid, cv2  # noqa
        self._torch = torch; self._cv2 = cv2
        self._device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        name = os.environ.get("NOTIFY_REID_MODEL", "osnet_x1_0")
        pre = os.environ.get("NOTIFY_REID_PRETRAINED", "1") != "0"
        self._model = torchreid.models.build_model(name, num_classes=1, pretrained=pre).to(self._device).eval()
        print(f"[notify] OSNet '{name}' loaded (device={self._device}, pretrained={pre})", flush=True)

    def _embed(self, frame, boxes):
        torch, cv2 = self._torch, self._cv2
        crops = []
        for (x1, y1, x2, y2) in boxes:
            x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), int(x2), int(y2)
            c = frame[y1:y2, x1:x2]
            if c.size == 0: c = np.zeros((256, 128, 3), np.uint8)
            crops.append(cv2.resize(c, (128, 256))[:, :, ::-1])
        if not crops: return None
        t = torch.from_numpy(np.ascontiguousarray(np.stack(crops))).permute(0, 3, 1, 2).float().div_(255.0).to(self._device)
        with torch.no_grad():
            f = torch.nn.functional.normalize(self._model(t), dim=1)
        return f.cpu().numpy()

    def update(self, boxes, frame):
        out = self.base.update(boxes, frame)
        if frame is None or not out: return out
        embs = self._embed(frame, [o[1] for o in out])
        if embs is None: return out
        result = []
        for i, (tid, box, is_new) in enumerate(out):
            emb = embs[i]
            g = self.gallery.get(tid)
            self.gallery[tid] = emb if g is None else _l2(0.7 * g + 0.3 * emb)
            if is_new:
                best_sim = 0.0
                for oid, gv in self.gallery.items():
                    if oid == tid: continue
                    s = float(np.dot(emb, gv))
                    if s > best_sim: best_sim = s
                if best_sim >= self.reid_thr:
                    is_new = False  # appearance seen before -> re-entry, not a new entrant
            result.append((tid, box, is_new))
        return result

    def mark_fired(self, tid):
        self.base.mark_fired(tid)


def make_tracker():
    kind = os.environ.get("NOTIFY_TRACKER", "iou").lower()
    if kind == "osnet":
        try:
            return OSNetTracker()
        except Exception as e:
            print(f"[notify] OSNet tracker unavailable ({e}) -> IoU fallback", flush=True)
    return IoUTracker()


class NotifyEngine:
    """tracker + attribute watch + VLM match + notify callbacks. Call on_persons(boxes, frame) each
    frame. A new confirmed id fires ONE async VLM query (fired-once-per-id dedups; no count flicker)."""
    def __init__(self, vlm_confirm, on_notify, on_highlight=None, attrs=None):
        self.tracker = make_tracker()
        self.vlm_confirm = vlm_confirm
        self.on_notify = on_notify           # (text) -> chat + TTS
        self.on_highlight = on_highlight     # (box, frame) -> SAM2 mark
        self.attrs = (attrs if attrs is not None else os.environ.get("NOTIFY_ATTRS", "")).strip()
        self.enabled = bool(self.attrs)
        self._lock = threading.Lock()

    def set_attrs(self, attrs):
        with self._lock:
            self.attrs = (attrs or "").strip(); self.enabled = bool(self.attrs)
        print(f"[notify] watch {'armed for: ' + repr(self.attrs) if self.enabled else 'cleared'}", flush=True)

    def on_persons(self, boxes, frame):
        if not self.enabled or frame is None: return
        for tid, box, is_new in self.tracker.update(boxes, frame):
            if is_new:
                self.tracker.mark_fired(tid)          # once per id, match or not
                self._query(tid, box, frame.copy())

    def _query(self, tid, box, frame):
        with self._lock: attrs = self.attrs
        def run():
            x1, y1, x2, y2 = [int(v) for v in box]
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            if crop.size == 0: return
            try:
                yes, raw = self.vlm_confirm(crop, attrs)
            except Exception as e:
                print(f"[notify] VLM err: {e}", flush=True); return
            print(f"[notify] id={tid} '{attrs}' -> {raw!r} match={yes}", flush=True)
            if yes:
                self.on_notify(f"\U0001F514 Person matching '{attrs}' entered.")
                if self.on_highlight:
                    try: self.on_highlight(box, frame)
                    except Exception as e: print(f"[notify] highlight err: {e}", flush=True)
        threading.Thread(target=run, daemon=True).start()


_ARM_RE = None
def parse_arm(text):
    """'notify me when someone in a red shirt shows up' -> 'in a red shirt'. None if not an arm cmd."""
    import re
    global _ARM_RE
    if _ARM_RE is None:
        _ARM_RE = re.compile(r"\b(?:notify|tell|alert|watch|let me know)\b.*?\b(?:when|if|for)\b\s+(.*)", re.I)
    m = _ARM_RE.search(text or "")
    if not m: return None
    p = m.group(1).strip().rstrip(".")
    p = re.sub(r"^(?:someone|somebody|a person|anyone|people|there is|there's)\s+(?:is\s+|who\s+is\s+)?", "", p, flags=re.I).strip()
    p = re.sub(r"\s+(?:shows? up|show up|appears?|enters?|comes? in|walks? in|is here|arrives?)\b.*$", "", p, flags=re.I).strip()
    return p or None
