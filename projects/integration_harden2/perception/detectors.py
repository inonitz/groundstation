"""Model-owning detector for the perception engine; engine.py stays model-free. harden2 keeps only the
background YOLO26-seg (Eyes). OmDet and the lazy SAM2 mask were deleted with the old highlight backend
on 2026-09-11; the live highlight is SAM3 (perception2.Sam3Backend, wired in mvd.build_highlight).
Eyes.background() is the closed-set detector kept for possible reuse (owner ruling 2026-09-11)."""
import config      # integration_harden2 root is on sys.path for every consumer of this package


class Eyes:
    def __init__(self):
        from ultralytics import YOLO
        self._bg = None if str(config.BG_SEG_MODEL).lower() in ("off", "none", "") else YOLO(config.BG_SEG_MODEL)   # SCENE_BG=off = no YOLO
        self.device = config.resolve_device()                   # ultralytics device ("0"/"cpu"/"mps")
        self.tdevice = config.resolve_torch_device()            # torch device ("cuda"/"cpu"/"mps")
        print(f"[integration] eyes bg={config.BG_SEG_MODEL} dev={self.device}/{self.tdevice}", flush=True)

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
            if self._bg is None:
                return []
            r = self._bg.predict(frame, verbose=False, device=self.device, imgsz=config.DETECT_IMGSZ)
            return self._dets(r, config.CONF_BG)
        except Exception as e:
            print("bg detect error:", e); return []
