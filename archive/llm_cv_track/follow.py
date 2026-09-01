#!/usr/bin/env python3
"""Voice-driven TRACKED highlighting = the fusion of the two prototypes.

  track.py  -> BoT-SORT tracker only (fast per-frame IDs, no brain).  Phase-2 detector playground.
  ../llm_cv_scene/app.py -> VLM brain + ASR, but the highlight is a STATIC one-shot box (no tracking).
  follow.py -> THIS: say who to follow, the VLM resolves the referent ONCE, we hand that track ID to
               BoT-SORT, and it follows in real time (camera-motion compensated + Re-ID).

Why the referent is resolved on a SNAPSHOT, not the live frame: a Qwen3-VL call is ~seconds, during
which the target keeps moving. So at command time we freeze (frame, tracked-boxes-with-IDs), let the
VLM point at the referent in THAT frame, IoU-match it to a track ID there, then follow that ID forward.
BoT-SORT IDs persist, so the lock stays valid (and survives brief occlusion via Re-ID).

  python3 follow.py --source 0 --command "the person in the red shirt"   # test w/o ASR (webcam)
  python3 follow.py                                                       # drone RTSP + live ASR
  python3 follow.py --classes person,car                                 # limit the tracker's classes
Live voice (needs the ROS2 asr_node running): "follow the person on the left" / "clear".
Window: q or Esc quit | c clear the lock.
"""
import os, sys, re, time, threading, collections, textwrap, argparse, subprocess
import cv2, numpy as np

SCENE = "/root/groundstation/source/llm_cv_scene"   # reuse the frozen brain + weights, touch nothing
REID_TRACKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "botsort_reid.yaml")
sys.path.insert(0, SCENE)
import config, vlm                                   # noqa: E402  (frozen modules)
try:
    from ears import Ears                            # ROS2 ASR subscriber (optional for webcam tests)
    _HAVE_EARS = True
except Exception as _e:                              # noqa: E402
    _HAVE_EARS, _EARS_ERR = False, _e

FONT = cv2.FONT_HERSHEY_SIMPLEX

# --- transcript -> intent (mirror of app.parse_highlight, + follow/lock verbs) ---
_CLEAR_RE  = re.compile(r"\b(?:stop (?:follow\w*|highlight\w*|track\w*)|clear|reset|deselect|unlock|never ?mind)\b", re.I)
_FIND_RE   = re.compile(r"\b(?:follow|track|lock (?:on|onto)|highlight|locate|mark|find|show me|point (?:at|to)|where(?:'s| is| are))\s+(?:the |a |an |that |my )?(.+)", re.I)
_FILLER_RE = re.compile(r"\b(?:please|for me|in the (?:frame|image|scene|room|camera)|right now|thank you|thanks)\b.*$", re.I)

def parse_command(text):
    """-> phrase to follow, '' to clear the lock, or None if the sentence has no follow intent."""
    if _CLEAR_RE.search(text):
        return ""
    m = _FIND_RE.search(text)
    if not m:
        return None
    phrase = _FILLER_RE.sub("", m.group(1)).strip().strip(".?! ,")
    return phrase or None


def _iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua > 0 else 0.0

def _center(b):
    return ((b[0]+b[2]) * 0.5, (b[1]+b[3]) * 0.5)

def _ascii(s):
    return (s or "").encode("ascii", "ignore").decode("ascii")

REACQ_SIM = 0.45                    # min HSV-hist correlation to re-lock a lost target to a track

def _hist(frame, box):
    """HSV hue-sat histogram of a box crop = a lightweight appearance fingerprint (clothing colour)."""
    x1, y1, x2, y2 = (int(v) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(h, h, 0, 1, cv2.NORM_MINMAX)
    return h

def _hist_sim(a, b):
    if a is None or b is None:
        return 0.0
    return float(cv2.compareHist(a, b, cv2.HISTCMP_CORREL))

def _reacquire(frame, idb, target_hist, last_box):
    """Re-lock a lost target to a current track by appearance; fall back to nearest to last-seen spot.
    -> (id, label, box, why) or None."""
    if not idb:
        return None
    if target_hist is not None:
        best_sim, best = REACQ_SIM, None
        for tid, box, lab in idb:
            sim = _hist_sim(target_hist, _hist(frame, box))
            if sim >= best_sim:
                best_sim, best = sim, (tid, lab, box, f"appearance {sim:.2f}")
        if best is not None:
            return best
    if last_box is not None:                       # no appearance match -> nearest to where we lost them
        lc = _center(last_box)
        tid, box, lab = min(idb, key=lambda t: (_center(t[1])[0]-lc[0])**2 + (_center(t[1])[1]-lc[1])**2)
        diag = (frame.shape[0]**2 + frame.shape[1]**2) ** 0.5
        d = ((_center(box)[0]-lc[0])**2 + (_center(box)[1]-lc[1])**2) ** 0.5
        if d < 0.20 * diag:
            return (tid, lab, box, "nearest")
    return None


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.id_boxes = []                 # [(track_id, (x1,y1,x2,y2), label), ...] this frame
        self.locked_id = None
        self.locked_label = ""
        self.answer = ""                   # VLM's reasoning, shown on screen
        self.cmd = ""
        self.status = "say who to follow"
        self.trail = collections.deque(maxlen=48)
        self.last_box = None               # last box of the locked target (for 'last seen' marker)
        self.missing_since = None          # wall-clock when the locked target left frame, else None
        self.locked_hist = None            # HSV appearance fingerprint of the locked target
        self.pending = None                # (phrase, frame_snapshot, id_boxes_snapshot)
        self.ev = threading.Event()
        self.running = True

S = State()


def _dispatch(phrase):
    """Freeze (frame, tracked boxes) NOW and queue the VLM resolution against that snapshot."""
    with S.lock:
        frame = None if S.frame is None else S.frame.copy()
        snap = list(S.id_boxes)
        if frame is not None:
            S.pending = (phrase, frame, snap)
            S.cmd = phrase
            S.status = f"resolving: {phrase}"
    if frame is not None:
        S.ev.set()


def on_text(text):
    """ASR/keyboard entry point."""
    text = (text or "").strip()
    if not text:
        return
    print(f"[follow] you: {text}", flush=True)
    cmd = parse_command(text)
    if cmd == "":                          # explicit clear
        with S.lock:
            S.locked_id = None; S.locked_label = ""; S.answer = ""; S.cmd = ""
            S.status = "cleared"; S.trail.clear(); S.last_box = None; S.missing_since = None; S.locked_hist = None
        return
    if cmd is None:                        # no follow verb -> ignore (this app only follows)
        return
    _dispatch(cmd)


def resolver():
    """One worker: pop a pending phrase, ask the VLM which detection is the referent, lock its ID."""
    vlm.ensure_server(wait=240)
    while S.running:
        if not S.ev.wait(timeout=0.3):
            continue
        S.ev.clear()
        with S.lock:
            job = S.pending; S.pending = None
        if not job:
            continue
        phrase, frame, snap = job
        desc, dets = vlm.analyze(frame, f"In one short sentence: which one is the {phrase}, and where is it? If it is not visible, say so.")
        chosen, why = None, ""
        if dets:
            vbox = dets[0]["box"]
            best_iou, best_id = 0.0, None
            for tid, tb, _lab in snap:
                j = _iou(vbox, tb)
                if j > best_iou:
                    best_iou, best_id = j, tid
            if best_iou >= 0.05:
                chosen, why = best_id, f"IoU {best_iou:.2f}"
            elif snap:                     # VLM saw it but boxes didn't overlap -> nearest center
                vc = _center(vbox)
                best_id = min(snap, key=lambda s: (_center(s[1])[0]-vc[0])**2 + (_center(s[1])[1]-vc[1])**2)[0]
                chosen, why = best_id, "nearest"
        with S.lock:
            S.answer = _ascii(desc); S.cmd = phrase
            if chosen is not None:
                S.locked_id = chosen; S.trail.clear(); S.missing_since = None; S.last_box = None; S.locked_hist = None
                S.locked_label = next((l for i, b, l in snap if i == chosen), "")
                S.status = f"LOCKED #{chosen} {S.locked_label} ({why})"
            elif not dets:
                S.status = f"'{phrase}' not visible"
            else:
                S.status = f"'{phrase}' found but no matching track (class not detected)"
        print(f"[follow] {S.status} | {S.answer}", flush=True)


def _wrap(text, px_w):
    lines = textwrap.wrap(_ascii(text), max(20, px_w // 11))
    if len(lines) > 4:
        lines = lines[:4]; lines[-1] = lines[-1] + " ..."
    return lines

def _dashed_box(img, box, col, dash=12):
    x1, y1, x2, y2 = box
    for x in range(x1, x2, dash * 2):
        cv2.line(img, (x, y1), (min(x + dash, x2), y1), col, 2)
        cv2.line(img, (x, y2), (min(x + dash, x2), y2), col, 2)
    for y in range(y1, y2, dash * 2):
        cv2.line(img, (x1, y), (x1, min(y + dash, y2)), col, 2)
        cv2.line(img, (x2, y), (x2, min(y + dash, y2)), col, 2)

def _draw_bottom(img, lines):
    if not lines:
        return
    h, w = img.shape[:2]
    lh, pad = 22, 10
    bh = pad * 2 + lh * len(lines)
    ov = img.copy()
    cv2.rectangle(ov, (0, h - bh), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.55, img, 0.45, 0, img)
    y = h - bh + pad + 15
    for txt, col in lines:
        cv2.putText(img, txt, (pad, y), FONT, 0.55, col, 1, cv2.LINE_AA); y += lh

def render(frame, idb, locked):
    disp = frame.copy()
    with S.lock:
        answer, cmd, status = S.answer, S.cmd, S.status
        trail, last_box, missing_since = list(S.trail), S.last_box, S.missing_since
    present = False
    for tid, box, lab in idb:
        x1, y1, x2, y2 = box
        if locked is not None and tid == locked:
            present = True
            cv2.rectangle(disp, (x1, y1), (x2, y2), (60, 220, 60), 3)
            cv2.putText(disp, f"LOCK #{tid} {lab}", (x1, max(y1 - 8, 15)), FONT, 0.6, (60, 220, 60), 2, cv2.LINE_AA)
        else:
            col = (110, 110, 110) if locked is not None else (0, 200, 255)   # dim others once locked
            cv2.rectangle(disp, (x1, y1), (x2, y2), col, 1)
            cv2.putText(disp, f"#{tid} {lab}", (x1, max(y1 - 6, 12)), FONT, 0.45, col, 1, cv2.LINE_AA)
    if len(trail) >= 2:
        cv2.polylines(disp, [np.array([(int(x), int(y)) for x, y in trail], np.int32)], False, (255, 255, 0), 2)
    lost = locked is not None and not present and missing_since is not None
    if lost and last_box is not None:
        _dashed_box(disp, last_box, (0, 165, 255))
        cv2.putText(disp, "last seen", (last_box[0], max(last_box[1] - 8, 15)), FONT, 0.5, (0, 165, 255), 2, cv2.LINE_AA)
    lines = []
    if cmd:
        lines.append(("CMD: " + cmd, (0, 215, 255)))
    for wl in _wrap(answer, disp.shape[1]):
        lines.append((wl, (235, 235, 235)))
    if lost:
        lines.append((f"TARGET #{locked} OUT OF FRAME - searching {time.time() - missing_since:.0f}s", (0, 165, 255)))
    else:
        lines.append((status, (60, 220, 60) if locked is not None else (170, 170, 170)))
    _draw_bottom(disp, lines)
    return disp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("SCENE_INPUT", "rtsp://127.0.0.1:8554/live"))
    ap.add_argument("--command", default=None, help="seed a target for testing without ASR")
    ap.add_argument("--open", default=None, help="open-vocab tracker phrase -> YOLOE-26x")
    ap.add_argument("--classes", default=None, help="comma COCO class names -> YOLO26 (default: all)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--tracker", default=REID_TRACKER, help="tracker yaml (default: BoT-SORT + Re-ID)")
    ap.add_argument("--no-ears", action="store_true")
    ap.add_argument("--keep-llama", action="store_true", help="do not kill llama-server on exit (fast iteration)")
    a = ap.parse_args()
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    src = int(a.source) if str(a.source).isdigit() else a.source

    classes = None
    if a.open:
        from ultralytics import YOLOE
        model = YOLOE(a.model or f"{SCENE}/yoloe-26x-seg.pt")
        try: model.set_classes([a.open], model.get_text_pe([a.open]))
        except Exception: model.set_classes([a.open])
        print(f"[follow] tracker: open-vocab YOLOE-26x {a.open!r}")
    else:
        from ultralytics import YOLO
        model = YOLO(a.model or f"{SCENE}/yolo26n-seg.pt")
        if a.classes:
            names = {v: k for k, v in model.names.items()}
            classes = [names[c.strip()] for c in a.classes.split(",") if c.strip() in names]
        print(f"[follow] tracker: YOLO26 {a.classes or 'all COCO classes'}")

    # own llama-server only if WE start it -> clean it up on exit (no lingering VRAM)
    we_started_llama = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode != 0
    threading.Thread(target=resolver, daemon=True).start()

    ears = None
    if _HAVE_EARS and not a.no_ears:
        try: ears = Ears(on_text); print("[follow] ASR live (say 'follow the ...').")
        except Exception as e: print("[follow] Ears unavailable:", e)
    elif not _HAVE_EARS:
        print("[follow] no ROS2/ears -> voice off; use --command.")

    if a.command:
        def seed():
            for _ in range(300):
                with S.lock:
                    ready = S.frame is not None
                if ready:
                    break
                time.sleep(0.1)
            _dispatch(a.command)
        threading.Thread(target=seed, daemon=True).start()

    win = "llm_cv_track:follow"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print(f"[follow] source={src}  tracker=BoT-SORT  -- q/Esc quit, c clear lock", flush=True)
    gen = model.track(source=src, tracker=a.tracker, persist=True, stream=True,
                      conf=a.conf, imgsz=a.imgsz, classes=classes, verbose=False)
    try:
        for result in gen:
            frame = result.orig_img
            idb, b = [], result.boxes
            if b is not None and b.id is not None:
                ids = b.id.int().cpu().tolist()
                xy = b.xyxy.cpu().numpy()
                cls = b.cls.int().cpu().tolist()
                for i, tid in enumerate(ids):
                    x1, y1, x2, y2 = (int(v) for v in xy[i])
                    idb.append((tid, (x1, y1, x2, y2), result.names[cls[i]]))
            with S.lock:
                S.frame = frame; S.id_boxes = idb
                locked = S.locked_id
                if locked is not None:
                    lb = next((bx for i, bx, l in idb if i == locked), None)
                    if lb is not None:
                        S.trail.append(_center(lb)); S.last_box = lb; S.missing_since = None
                        h = _hist(frame, lb)
                        if h is not None:
                            S.locked_hist = h                      # keep the fingerprint fresh
                    else:
                        if S.missing_since is None:
                            S.missing_since = time.time()
                        rid = _reacquire(frame, idb, S.locked_hist, S.last_box)
                        if rid is not None:                        # re-lock to the returned target
                            S.locked_id = locked = rid[0]
                            S.locked_label = rid[1]; S.missing_since = None
                            S.trail.append(_center(rid[2])); S.last_box = rid[2]
                            S.status = f"RE-ACQUIRED #{rid[0]} ({rid[3]})"
            cv2.imshow(win, render(frame, idb, locked))
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord('q')):
                break
            if k == ord('c'):
                with S.lock:
                    S.locked_id = None; S.locked_label = ""; S.status = "cleared"; S.trail.clear()
                    S.last_box = None; S.missing_since = None; S.locked_hist = None
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        S.running = False
        try: gen.close()                      # unwind the ultralytics track generator
        except Exception: pass
        try:                                  # THE core-dump fix: join the LoadStreams grabber thread +
            p = getattr(model, "predictor", None)   # release the VideoCapture, else C++ std::terminate on exit
            if p is not None and getattr(p, "dataset", None) is not None:
                p.dataset.close()
        except Exception: pass
        cv2.destroyAllWindows(); cv2.waitKey(1)
        if ears:
            ears.shutdown()
        if we_started_llama and not a.keep_llama:
            print("[follow] stopping llama-server we launched...", flush=True)
            subprocess.run(["pkill", "-f", "llama-server"], check=False)
        os._exit(0)   # bypass torch/ROCm interpreter-teardown crash -> clean exit code 0, no core dump


if __name__ == "__main__":
    main()
