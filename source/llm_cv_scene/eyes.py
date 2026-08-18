"""Real-time eyes. YOLOE draws always-on background detections every frame and, on demand,
localizes a phrase the brain asked to highlight. SAM2 (optional) turns that box into a
crisp mask so you can compare the two selection methods. The highlight model is guarded by
a lock because set_target() runs on the ASR thread while highlight() runs on the video thread."""
import threading
import config

class Eyes:
    def __init__(self, use_sam2=True):
        from ultralytics import YOLOE
        self._bg = YOLOE(config.YOLOE_BACKGROUND)   # prompt-free: always-on background
        self._hl = YOLOE(config.YOLOE_PROMPT)       # promptable : on-demand highlight
        self._lock = threading.Lock()
        self.device = config.resolve_device()
        print(f"[llm_cv_scene] eyes compute device: {self.device}")
        self._sam = None
        if use_sam2:
            try:
                from ultralytics import SAM
                self._sam = SAM(config.SAM2_WEIGHTS)
            except Exception as e:
                print("SAM2 unavailable, continuing without it:", e)
        self.target = None

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
            res = self._bg.predict(frame, verbose=False, device=self.device)
            return self._dets(res, config.CONF_BG)
        except Exception as e:
            print("bg detect error:", e); return []

    def set_target(self, phrase):
        with self._lock:
            self.target = phrase
            if phrase:
                try:
                    self._hl.set_classes([phrase], self._hl.get_text_pe([phrase]))
                except Exception as e:
                    print("set_classes error:", e); self.target = None

    def highlight(self, frame):
        """-> (dets, mask). mask is a bool HxW from SAM2, or None."""
        with self._lock:
            if not self.target:
                return [], None
            try:
                res = self._hl.predict(frame, verbose=False, device=self.device)
                dets = self._dets(res, config.CONF_HL)
            except Exception as e:
                print("highlight error:", e); return [], None
        mask = None
        if dets and self._sam is not None:
            x1, y1, x2, y2 = dets[0]["box"]
            try:
                res = self._sam(frame, bboxes=[[x1, y1, x2, y2]], verbose=False, device=self.device)
                if res and res[0].masks is not None:
                    mask = res[0].masks.data[0].cpu().numpy().astype(bool)
            except Exception as e:
                print("sam2 error:", e)
        return dets, mask
