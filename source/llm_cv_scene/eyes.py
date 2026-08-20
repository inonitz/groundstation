"""Real-time eyes. YOLO26-seg draws always-on background detections. The on-demand HIGHLIGHT has two
selectable backends (SCENE_HL_BACKEND):
  - "yoloe" (DEFAULT, demo-safe): YOLOE-2026 open-vocab, confidence-GATED -- when the prompted thing
    isn't there it shows NOTHING instead of hallucinating a box. This is what you want live.
  - "grounder": LLMDet/MM-Grounding-DINO via transformers. Higher recall on esoteric ground-level
    objects, but as a phrase grounder it returns a box even when absent -> can look confidently-wrong
    on out-of-distribution (e.g. aerial/blurry) footage. Opt-in for tuned/ground-level use.
The highlighter is LOADED + WARMED on a BACKGROUND THREAD so the video window opens in seconds; until
it is ready, background detection + VLM chat work and highlight is a quiet no-op. SAM2 is lazy."""
import threading
import config


class Grounder:
    """LLMDet / MM-Grounding-DINO (transformers), opt-in. Portable across GPU vendors (pure-PyTorch
    deformable-attention path -> ROCm/CUDA/CPU). Grounds the stored phrase; may fire on absent objects."""
    def __init__(self, repo, device):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        self._torch = torch
        self.device = device
        self._phrase = None
        self.proc = AutoProcessor.from_pretrained(repo)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(repo).to(device).eval()

    def set_target(self, phrase):
        self._phrase = phrase or None

    def detect(self, frame_bgr):
        if not self._phrase:
            return []
        torch = self._torch
        from PIL import Image
        pil = Image.fromarray(frame_bgr[:, :, ::-1])
        cap = self._phrase.lower().strip().rstrip(".") + "."
        inp = self.proc(images=pil, text=cap, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model(**inp)
        kw = dict(threshold=config.GND_BOX_THR, target_sizes=[(pil.height, pil.width)])
        try:
            res = self.proc.post_process_grounded_object_detection(out, text_threshold=config.GND_TEXT_THR, **kw)[0]
        except TypeError:
            res = self.proc.post_process_grounded_object_detection(out, **kw)[0]
        boxes, scores = res["boxes"], res["scores"]
        dets = []
        for i in range(len(scores)):
            x1, y1, x2, y2 = (int(v) for v in boxes[i].tolist())
            dets.append({"label": self._phrase, "conf": float(scores[i]), "box": (x1, y1, x2, y2)})
        dets.sort(key=lambda d: -d["conf"])
        return dets[:config.GND_TOPK]


class YoloeHighlighter:
    """YOLOE-2026 open-vocab highlight (Ultralytics). DEMO DEFAULT: confidence-gated, so an absent
    prompt yields NO box rather than a hallucinated one. set_classes re-encodes the phrase; do it on
    target change (ASR thread), predict on the worker thread -- lock-guarded so they don't overlap."""
    def __init__(self, weights, device):
        from ultralytics import YOLOE
        self.m = YOLOE(weights)
        self.device = device
        self._lock = threading.Lock()

    def set_target(self, phrase):
        with self._lock:
            if phrase:
                try:
                    self.m.set_classes([phrase], self.m.get_text_pe([phrase]))
                except (TypeError, AttributeError):
                    self.m.set_classes([phrase])

    def detect(self, frame_bgr):
        with self._lock:
            r = self.m.predict(frame_bgr, verbose=False, device=self.device, imgsz=config.DETECT_IMGSZ)[0]
        out = []
        if r.boxes is not None:
            for b in r.boxes:
                c = float(b.conf[0])
                if c < config.CONF_HL:
                    continue
                x1, y1, x2, y2 = (int(v) for v in b.xyxy[0])
                out.append({"label": r.names[int(b.cls[0])], "conf": c, "box": (x1, y1, x2, y2)})
        out.sort(key=lambda d: -d["conf"])
        return out[:config.GND_TOPK]


class Eyes:
    def __init__(self):
        from ultralytics import YOLO
        self._bg = YOLO(config.BG_SEG_MODEL)                    # closed-set YOLO26-seg: fast background
        self.device = config.resolve_device()                   # ultralytics device ("0"/"cpu"/"mps")
        self.tdevice = config.resolve_torch_device()            # torch device ("cuda"/"cpu"/"mps")
        self._hl = None                                         # highlighter, loaded off-thread
        self._sam = None                                        # lazy
        self._lock = threading.Lock()
        self.target = None
        print(f"[llm_cv_scene] eyes bg={config.BG_SEG_MODEL} highlight={config.HIGHLIGHT_BACKEND} "
              f"dev={self.device}/{self.tdevice}", flush=True)
        threading.Thread(target=self._init_highlighter, daemon=True).start()

    def _init_highlighter(self):
        """Load + warm the chosen highlight backend off the critical path (first GPU kernel compile is
        the slow part). Until this sets self._hl, highlight() is a quiet no-op."""
        try:
            b = config.HIGHLIGHT_BACKEND.lower()
            if b == "vlm":
                print("[llm_cv_scene] highlight backend 'vlm' (Qwen3-VL grounding); no detector to load, SAM2 lazy.", flush=True)
                return
            print(f"[llm_cv_scene] highlight backend '{b}' loading in background...", flush=True)
            if b == "grounder":
                hl = Grounder(config.GROUNDER_REPO, self.tdevice)
            else:
                hl = YoloeHighlighter(config.OPENVOCAB_MODEL, self.device)
            if config.WARMUP:
                import numpy as np
                blank = np.zeros((config.CAM_H, config.CAM_W, 3), dtype="uint8")
                try:
                    hl.set_target("object"); hl.detect(blank); hl.set_target(None)
                except Exception as e:
                    print("warmup highlight:", e)
            with self._lock:
                t = self.target
            if t:                                               # target set while we were loading
                try: hl.set_target(t)
                except Exception: pass
            self._hl = hl
            print("[llm_cv_scene] highlight READY.", flush=True)
        except Exception as e:
            print("highlight init failed:", e)

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

    def mask_for_box(self, frame, box):
        """SAM2 mask for a given box (used by the VLM-grounded highlight). None-safe."""
        if self._ensure_sam() is None:
            return None
        x1, y1, x2, y2 = box
        try:
            r = self._sam(frame, bboxes=[x1, y1, x2, y2], verbose=False, device=self.device)
            if r and r[0].masks is not None and len(r[0].masks.data) > 0:
                return r[0].masks.data[0].cpu().numpy().astype(bool)
        except Exception as e:
            print("sam2 error:", e)
        return None

    def background(self, frame):
        try:
            r = self._bg.predict(frame, verbose=False, device=self.device, imgsz=config.DETECT_IMGSZ)
            return self._dets(r, config.CONF_BG)
        except Exception as e:
            print("bg detect error:", e); return []

    def set_target(self, phrase):
        with self._lock:
            self.target = phrase or None
        if self._hl is not None:
            try:
                self._hl.set_target(phrase or None)
            except Exception as e:
                print("set_target error:", e)

    def highlight(self, frame, want_mask=True):
        """-> (dets, mask). Uses the current backend; mask only when want_mask + SAM2 up."""
        with self._lock:
            target = self.target
        if not target or self._hl is None:
            return [], None
        try:
            dets = self._hl.detect(frame)                       # heavy call OUTSIDE the lock
        except Exception as e:
            print("highlight error:", e); return [], None
        mask = None
        if dets and want_mask and self._ensure_sam() is not None:
            x1, y1, x2, y2 = dets[0]["box"]
            try:
                r = self._sam(frame, bboxes=[x1, y1, x2, y2], verbose=False, device=self.device)
                if r and r[0].masks is not None and len(r[0].masks.data) > 0:
                    mask = r[0].masks.data[0].cpu().numpy().astype(bool)
            except Exception as e:
                print("sam2 error:", e)
        return dets, mask
