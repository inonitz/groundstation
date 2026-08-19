"""Real-time eyes. YOLO26-seg draws always-on background detections; YOLOE-26 localizes a phrase
on demand (open-vocab). SAM2 is LAZY (loaded only the first time a mask is actually requested, so
it costs no VRAM unless you turn it on). The highlight model is lock-guarded: set_target() runs on
the ASR thread, highlight() on the perception worker."""
import threading
import config

class Eyes:
    def __init__(self):
        from ultralytics import YOLO, YOLOE
        self._bg = YOLO(config.BG_SEG_MODEL)          # closed-set YOLO26-seg: background
        self._hl = YOLOE(config.OPENVOCAB_MODEL)      # YOLOE-26 open-vocab: on-demand highlight
        self._sam = None                              # lazy
        self._lock = threading.Lock()
        self.device = config.resolve_device()
        print(f"[llm_cv_scene] eyes device={self.device} bg={config.BG_SEG_MODEL} ov={config.OPENVOCAB_MODEL}")
        self.target = None

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
        with self._lock:
            self.target = phrase
            if phrase:
                try:
                    try:
                        self._hl.set_classes([phrase], self._hl.get_text_pe([phrase]))
                    except (TypeError, AttributeError):
                        self._hl.set_classes([phrase])
                except Exception as e:
                    print("set_classes error:", e); self.target = None

    def highlight(self, frame, want_mask=True):
        """-> (dets, mask). mask (bool HxW) only when want_mask and SAM2 is available."""
        with self._lock:
            if not self.target:
                return [], None
            try:
                r = self._hl.predict(frame, verbose=False, device=self.device, imgsz=config.DETECT_IMGSZ)
                dets = self._dets(r, config.CONF_HL)
            except Exception as e:
                print("highlight error:", e); return [], None
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
