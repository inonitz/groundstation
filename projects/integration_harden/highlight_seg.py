#!/usr/bin/env python3
"""integration -- integration's smart voice loop, but the open-vocab HIGHLIGHT uses a proper real-time
detector (OmDet-Turbo, Apache) instead of the broken YOLOE-2026/LLMDet, feeding clean boxes to SAM2.1.
This is the detection + segmentation + masking core.

  voice "highlight the guitar case" -> OmDet finds it EVERY frame (box follows it) -> SAM2 masks it
  voice "what do you see"           -> Qwen3-VL describes the scene
  voice "clear"                     -> drop the highlight
Specific-object TRACKING (persistent through occlusion) is a later add.

  python3 highlight_seg.py --source 0 --target "guitar case"   # webcam, no ASR (test)
  python3 highlight_seg.py                                       # drone RTSP + live ASR
Keys: q/Esc quit | c clear | t SAM2 masks on/off | b background on/off
"""
import os, sys, re, time, threading, textwrap, argparse, subprocess
os.environ.setdefault("SCENE_HL_BACKEND", "vlm")   # keep Eyes from loading YOLOE; we supply OmDet
import cv2, numpy as np, torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # self-contained: import only local modules
import config, vlm                                  # frozen: VLM brain, endpoints, colours
from eyes import Eyes                               # frozen: background YOLO + SAM2 mask_for_box
try:
    from ears import Ears; _HAVE_EARS = True
except Exception as _e:
    _HAVE_EARS = False

FONT = cv2.FONT_HERSHEY_SIMPLEX
_CLEAR_RE = re.compile(r"\b(?:stop (?:highlight\w*|track\w*)|clear|reset|deselect|never ?mind)\b", re.I)
_LEAD_VERB_RE = re.compile(r"^(?:highlight|locate|track|mark|find|show me|point (?:at|to))\s+(?:the |a |an |that |my )?", re.I)
_FIND_RE  = re.compile(r"\b(?:highlight|locate|track|mark|find|show me|point (?:at|to)|where(?:'s| is| are))\s+(?:the |a |an |that |my )?(.+)", re.I)
_FILLER_RE= re.compile(r"\b(?:please|for me|in the (?:frame|image|scene|room|camera)|right now|thank you|thanks)\b.*$", re.I)

def parse_highlight(text):
    if _CLEAR_RE.search(text): return ""
    m=_FIND_RE.search(text)
    if not m: return None
    ph=_FILLER_RE.sub("", m.group(1)).strip().strip(".?! ,")
    ph=_LEAD_VERB_RE.sub("", ph).strip() if ph else ph   # strip a second "highlight/mark the ..." prefix
    return ph or None

def _ascii(s): return (s or "").encode("ascii","ignore").decode("ascii")


class OmDet:
    """OmDet-Turbo open-vocab detector (Apache, transformers). Stateless: pass the phrase each call.
    Loads from a LOCAL, offline copy (/root/models/omdet-turbo-swin-tiny) in ~1s -- see README 'OmDet
    offline' -- so it never hangs fetching the Swin backbone from the HF Hub."""
    LOCAL = "/root/models/vision/omdet-turbo-swin-tiny"
    def __init__(self, device):
        import os, inspect, timm
        from transformers import AutoProcessor, OmDetTurboForObjectDetection
        if os.path.isdir(self.LOCAL):                       # baked config + weights -> fully offline
            os.environ["HF_HUB_OFFLINE"] = "1"; os.environ["TRANSFORMERS_OFFLINE"] = "1"
            r, lo = self.LOCAL, True
        else:
            r, lo = "omlab/omdet-turbo-swin-tiny-hf", False   # fallback: fetch from the hub (needs net)
        # transformers 5.x probes the hub (backbone_utils.consolidate_backbone_kwargs_to_config ->
        # HfApi.repo_exists) to decide timm-vs-hub backbone. With no internet (phone hotspot) that call
        # resets/raises and is NOT caught -> OmDet load fails. Make the probe fail-safe to False so
        # transformers uses the timm backbone (builds fully offline). Mirrors the desk-with-internet 404.
        try:
            import huggingface_hub as _hh
            if not getattr(_hh.HfApi.repo_exists, "_mvd_safe", False):
                _re = _hh.HfApi.repo_exists
                def _safe_repo_exists(self, *a, **k):
                    try: return _re(self, *a, **k)
                    except Exception: return False
                _safe_repo_exists._mvd_safe = True
                _hh.HfApi.repo_exists = _safe_repo_exists
        except Exception:
            pass
        _o = timm.create_model                              # backbone weights are in the checkpoint;
        timm.create_model = lambda *a, **k: _o(*a, **{**k, "pretrained": False})  # don't fetch ImageNet ones
        try:
            self.proc = AutoProcessor.from_pretrained(r, local_files_only=lo)
            self.model = OmDetTurboForObjectDetection.from_pretrained(r, local_files_only=lo).to(device).eval()
        finally:
            timm.create_model = _o
        self.device = device
        self._sig = inspect.signature(self.proc.post_process_grounded_object_detection).parameters
    def detect(self, frame_bgr, phrase, conf=0.30, topk=8):
        if not phrase: return []
        from PIL import Image
        pil=Image.fromarray(frame_bgr[:,:,::-1])
        prompts=[p.strip() for p in phrase.split(",") if p.strip()] or [phrase]
        inp=self.proc(pil, text=prompts, return_tensors="pt").to(self.device)
        with torch.no_grad(): out=self.model(**inp)
        kw={"target_sizes":[(pil.height,pil.width)]}
        if "text_labels" in self._sig: kw["text_labels"]=prompts
        elif "classes" in self._sig: kw["classes"]=[prompts]
        if "threshold" in self._sig: kw["threshold"]=conf
        elif "score_threshold" in self._sig: kw["score_threshold"]=conf
        if "nms_threshold" in self._sig: kw["nms_threshold"]=0.5
        res=self.proc.post_process_grounded_object_detection(out, **kw)[0]
        labels=res.get("text_labels", res.get("labels"))
        dets=[]
        for sc,lb,bx in zip(res["scores"],labels,res["boxes"]):
            lab=lb if isinstance(lb,str) else (prompts[int(lb)] if int(lb)<len(prompts) else str(lb))
            x1,y1,x2,y2=(int(v) for v in bx)
            dets.append({"label":str(lab),"conf":float(sc),"box":(x1,y1,x2,y2)})
        dets.sort(key=lambda d:-d["conf"])
        return dets[:topk]


class S:
    lock=threading.Lock()
    frame=None; bg_dets=[]; hl_dets=[]; hl_masks=[]
    target=None; answer=""; thinking=False
    use_sam=True; show_bg=True; conf=0.30; mask_k=3
    fps=0.0; running=True

OM={"det":None}


def open_capture(src):
    src=str(src)
    if src in ("ros","camera_stream","camera/stream"):
        from camera_stream import CameraStream
        return CameraStream()
    if src.isdigit():
        c=cv2.VideoCapture(int(src)); c.set(cv2.CAP_PROP_FRAME_WIDTH,config.CAM_W); c.set(cv2.CAP_PROP_FRAME_HEIGHT,config.CAM_H); return c
    if "!" in src: return cv2.VideoCapture(src, cv2.CAP_GSTREAMER)
    return cv2.VideoCapture(src)


MASK_MAX_FRAC = 0.85   # room-scale objects (windows, whiteboards) are legitimately large   # a SAM2 mask covering more of the frame than this = garbage -> drop it
BOX_MAX_FRAC  = 0.90   # a near-full-frame box with no clean mask = not a useful highlight -> drop it

def _apply_masks(raw, frame, mask_for_box, use_sam, mk):
    """For each detection: SAM2-mask it, drop whole-frame garbage masks, tighten the box to the mask,
    and drop full-frame boxes that never produced a clean mask. -> (hl_dets, masks)."""
    Hf, Wf = frame.shape[:2]; fa = float(Hf * Wf)
    hl_out, masks = [], []
    for d in raw[:mk]:
        box = d["box"]; bfrac = ((box[2]-box[0]) * (box[3]-box[1])) / fa
        m = None
        if use_sam:
            try: m = mask_for_box(frame, box)
            except Exception as e: print("sam err:", e)
        if m is not None and m.sum() > 0 and (m.sum() / fa) <= MASK_MAX_FRAC:
            ys, xs = np.where(m); d = dict(d)
            d["box"] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))  # tighten box to mask
            masks.append(m); hl_out.append(d)
        elif bfrac <= BOX_MAX_FRAC:                 # localized box, keep even without a clean mask
            hl_out.append(d)
        # else: full-frame box + no clean mask -> drop (no whole-frame garbage highlight)
    return hl_out, masks

def worker(eyes):
    while S.running:
        with S.lock:
            frame=None if S.frame is None else S.frame.copy()
            target=S.target; use_sam=S.use_sam; show_bg=S.show_bg; conf=S.conf; mk=S.mask_k
        if frame is None: time.sleep(0.005); continue
        bg=eyes.background(frame) if show_bg else []
        hl_out, masks = [], []
        det=OM["det"]
        if target and det is not None:
            try: raw=det.detect(frame, target, conf=conf)
            except Exception as e: raw=[]; print("omdet err:",e)
            hl_out, masks = _apply_masks(raw, frame, eyes.mask_for_box, use_sam, mk)
        with S.lock:
            S.bg_dets=bg
            if target: S.hl_dets=hl_out; S.hl_masks=masks
            else: S.hl_dets=[]; S.hl_masks=[]
        time.sleep(0.003)


def _wrap(t,w):
    L=textwrap.wrap(_ascii(t),max(20,w//11)); return (L[:4]+["..."]) if len(L)>4 else L

def draw(frame):
    with S.lock:
        bg=list(S.bg_dets); hl=list(S.hl_dets); masks=list(S.hl_masks)
        target=S.target; answer=S.answer; thinking=S.thinking; use_sam=S.use_sam; show_bg=S.show_bg; fps=S.fps
    disp=frame.copy()
    if show_bg:
        for d in bg:
            x1,y1,x2,y2=d["box"]; cv2.rectangle(disp,(x1,y1),(x2,y2),config.COL_BACKGROUND,1)
    if use_sam and masks:
        ov=disp.copy()
        for m in masks:
            if m.shape[:2]!=disp.shape[:2]:
                m=cv2.resize(m.astype("uint8"),(disp.shape[1],disp.shape[0]),interpolation=cv2.INTER_NEAREST).astype(bool)
            ov[m]=config.COL_SAM2_HL
        cv2.addWeighted(ov,0.45,disp,0.55,0,disp)
    for d in hl:
        x1,y1,x2,y2=d["box"]; cv2.rectangle(disp,(x1,y1),(x2,y2),config.COL_YOLOE_HL,2)
        cv2.putText(disp,f'{d["label"]} {d["conf"]:.2f}',(x1,max(y1-6,14)),FONT,0.55,config.COL_YOLOE_HL,2,cv2.LINE_AA)
    lines=[(f"target: {target or '(none)'}   [OmDet {'ready' if OM['det'] else 'loading...'}]   {fps:.1f} fps",(0,215,255))]
    if thinking: lines.append(("thinking...",(160,235,160)))
    for wl in _wrap(answer, disp.shape[1]): lines.append((wl,(235,235,235)))
    h,w=disp.shape[:2]; lh=22; bh=20+lh*max(len(lines),1)
    ov=disp.copy(); cv2.rectangle(ov,(0,h-bh),(w,h),(0,0,0),-1); cv2.addWeighted(ov,0.55,disp,0.45,0,disp)
    y=h-bh+25
    for t,c in lines: cv2.putText(disp,t,(10,y),FONT,0.55,c,1,cv2.LINE_AA); y+=lh
    return disp


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("SCENE_INPUT","rtsp://127.0.0.1:8554/live"))
    ap.add_argument("--target", default=None, help="seed a highlight phrase without ASR (testing)")
    ap.add_argument("--no-ears", action="store_true")
    ap.add_argument("--keep-llama", action="store_true")
    a=ap.parse_args()
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS","rtsp_transport;tcp")

    threading.Thread(target=vlm.ensure_server, daemon=True).start()
    eyes=Eyes()
    we_started_llama=subprocess.run(["pgrep","-f","llama-server"],capture_output=True).returncode!=0
    def _load(dev):
        try: OM["det"]=OmDet(dev); print("[hl] OmDet ready",flush=True)
        except Exception as e: print("[hl] OmDet load FAILED:",e,flush=True)
    threading.Thread(target=_load, args=(eyes.tdevice,), daemon=True).start()

    def on_text(text):
        text=(text or "").strip()
        if not text: return
        print("[hl] you:",text,flush=True)
        ph=parse_highlight(text)
        if ph=="":
            with S.lock: S.target=None; S.hl_dets=[]; S.hl_masks=[]
            return
        if ph is not None:
            with S.lock: S.target=ph
            return
        with S.lock:
            frame=None if S.frame is None else S.frame.copy(); S.thinking=True
        if frame is None:
            with S.lock: S.thinking=False
            return
        try: desc,_,_,_=vlm.ask(frame,text,[])
        except Exception as e: desc=f"[VLM err: {e}]"
        with S.lock: S.answer=desc; S.thinking=False
        print("[hl] scene:",desc,flush=True)

    ears=None
    if _HAVE_EARS and not a.no_ears:
        try: ears=Ears(on_text); print("[hl] ASR live",flush=True)
        except Exception as e: print("[hl] Ears unavailable:",e)
    if a.target:
        with S.lock: S.target=a.target

    cap=open_capture(a.source); t0=time.time()
    while not cap.isOpened() and time.time()-t0<config.OPEN_TIMEOUT:
        print("[hl] waiting for input",a.source,flush=True); time.sleep(1.5); cap.release(); cap=open_capture(a.source)
    if not cap.isOpened(): print("cannot open",a.source); return

    threading.Thread(target=worker, args=(eyes,), daemon=True).start()
    win="integration:highlight_seg"; cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    tprev=time.time(); readfail=0
    try:
        while True:
            ok,frame=cap.read()
            if not ok:
                readfail+=1
                if readfail>config.READ_RETRY: print("[hl] input ended"); break
                time.sleep(0.03); continue
            readfail=0
            with S.lock: S.frame=frame
            disp=draw(frame)
            now=time.time()
            with S.lock: S.fps=0.9*S.fps+0.1/max(now-tprev,1e-3)
            tprev=now
            cv2.imshow(win,disp)
            k=cv2.waitKey(1)&0xFF
            if k in (27,ord('q')): break
            elif k==ord('c'):
                with S.lock: S.target=None; S.hl_dets=[]; S.hl_masks=[]
            elif k==ord('t'):
                with S.lock: S.use_sam=not S.use_sam
            elif k==ord('b'):
                with S.lock: S.show_bg=not S.show_bg
            if cv2.getWindowProperty(win,cv2.WND_PROP_VISIBLE)<1: break
    finally:
        S.running=False; time.sleep(0.05)
        cap.release(); cv2.destroyAllWindows(); cv2.waitKey(1)
        if ears: ears.shutdown()
        if we_started_llama and not a.keep_llama:
            subprocess.run(["pkill","-f","llama-server"],check=False)
        sess = os.environ.get("SCENE_TMUX_SESSION")
        if sess:
            subprocess.run(["tmux", "kill-session", "-t", sess], check=False)
        os._exit(0)   # bypass torch/ROCm interpreter-teardown crash -> clean exit code 0, no core dump

if __name__=="__main__":
    main()
