"""Real-time eyes. YOLO26-seg draws always-on background detections (subtle, every worker tick).
The on-demand HIGHLIGHT is an open-vocab PHRASE grounder -- LLMDet-tiny, loaded through the
transformers MM-Grounding-DINO implementation. That path is pure-PyTorch: the multi-scale
deformable-attention CUDA kernel is optional and transformers falls back to a portable version, so
the SAME code runs on ROCm, CUDA, or CPU -- no vendor lock-in. SAM2 is LAZY (loaded only when a mask
is first requested). set_target() runs on the ASR thread; highlight() on the perception worker."""
import threading
import config


class Grounder:
    """Open-vocab phrase grounding via transformers (LLMDet / MM-Grounding-DINO). Takes free text at
    call time (no per-target re-encode) and returns boxes for what matches. Portable across GPU
    vendors -- the deformable-attention custom CUDA op is not required."""
    def __init__(self, repo, device):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        self._torch = torch
        self.device = device
        self.proc = AutoProcessor.from_pretrained(repo)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(repo).to(device).eval()

    def detect(self, frame_bgr, phrase):
        torch = self._torch
        from PIL import Image
        pil = Image.fromarray(frame_bgr[:, :, ::-1])            # BGR(np) -> RGB(PIL)
        cap = phrase.lower().strip().rstrip(".") + "."           # grounder wants a lowercase caption
        inp = self.proc(images=pil, text=cap, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model(**inp)
        kw = dict(threshold=config.GND_BOX_THR, target_sizes=[(pil.height, pil.width)])
        try:
            res = self.proc.post_process_grounded_object_detection(out, text_threshold=config.GND_TEXT_THR, **kw)[0]
        except TypeError:                                        # some processors omit text_threshold
            res = self.proc.post_process_grounded_object_detection(out, **kw)[0]
        boxes, scores = res["boxes"], res["scores"]
        dets = []
        for i in range(len(scores)):
            x1, y1, x2, y2 = (int(v) for v in boxes[i].tolist())
            dets.append({"label": phrase, "conf": float(scores[i]), "box": (x1, y1, x2, y2)})
        dets.sort(key=lambda d: -d["conf"])
        return dets[:config.GND_TOPK]


class Eyes:
    def __init__(self):
        from ultralytics import YOLO
        self._bg = YOLO(config.BG_SEG_MODEL)                    # closed-set YOLO26-seg: fast background
        self.device = config.resolve_device()                   # ultralytics device string ("0"/"cpu"/"mps")
        self.tdevice = config.resolve_torch_device()            # torch device string ("cuda"/"cpu"/"mps")
        self._grounder = Grounder(config.GROUNDER_REPO, self.tdevice)   # open-vocab highlight
        self._sam = None                                        # lazy
        self._lock = threading.Lock()
        self.target = None
        print(f"[llm_cv_scene] eyes bg={config.BG_SEG_MODEL} grounder={config.GROUNDER_REPO} "
              f"dev={self.device}/{self.tdevice}")
        if config.WARMUP:
            self._warmup()

    def _warmup(self):
        """Front-load the one-time ROCm/MIOpen kernel compile (for the fixed camera frame size) so the
        FIRST live highlight is fast instead of stalling. One bg + one grounder pass on a blank frame."""
        import numpy as np
        print("[llm_cv_scene] warming up detectors (one-time GPU kernel compile)...", flush=True)
        blank = np.zeros((config.CAM_H, config.CAM_W, 3), dtype="uint8")
        try: self.background(blank)
        except Exception as e: print("warmup bg:", e)
        try: self._grounder.detect(blank, "object")
        except Exception as e: print("warmup grounder:", e)
        print("[llm_cv_scene] warmup done.", flush=True)

    def _ensure_sam(self):
        if self._sam is None:
            try:
                from ultralytics import SAM
                self._sam = SAM(config.SAM2_WEIGHTS)
            except Exception as e:
                print("SAM2 load failed:", e)
        return self._sam

    @staticmethod
    def _dets(results, conf):
        out, r = [], results[0]
        if r.boxes is None:
            return out
        for b in r.boxes:
            c = float(b.conf[0])
            if c < conf:
                continue
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0])
            out.append({"label": r.names[int(b.cls[0])], "conf": c, "box": (x1, y1, x2, y2)})
        return out

    def background(self, frame):
        try:
            r = self._bg.predict(frame, verbose=False, device=self.device, imgsz=config.DETECT_IMGSZ)
            return self._dets(r, config.CONF_BG)
        except Exception as e:
            print("bg detect error:", e); return []

    def set_target(self, phrase):
        """Store the phrase only -- the grounder consumes free text at detect time (no re-encode)."""
        with self._lock:
            self.target = phrase or None

    def highlight(self, frame, want_mask=True):
        """-> (dets, mask). Grounds the current target phrase; mask only when want_mask + SAM2 up."""
        with self._lock:
            target = self.target
        if not target:
            return [], None
        try:
            dets = self._grounder.detect(frame, target)         # heavy call OUTSIDE the lock
        except Exception as e:
            print("grounder error:", e); return [], None
        mask = None
        if dets and want_mask and self._ensure_sam() is not None:
            x1, y1, x2, y2 = dets[0]["box"]
            try:
                r = self._sam(frame, bboxes=[x1, y1, x2, y2], verbose=False, device=self.device)
                if r and r[0].masks is not None:
                    mask = r[0].masks.data[0].cpu().numpy().astype(bool)
            except Exception as e:
                print("sam2 error:", e)
        return dets, mask
