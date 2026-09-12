"""Model-owning detectors for the perception engine. This file loads the vision models;
engine.py stays model-free. Contents moved from highlight_seg.py (OmDet) and eyes.py (Eyes) on
2026-09-02; the unreachable yoloe/grounder highlight backends were deleted on 2026-09-03.

  OmDet  open-vocab detector, the live highlight backend (stateless, phrase per call)
  Eyes   background YOLO26-seg + lazy SAM2 mask_for_box (the highlight decision lives in engine.py)
"""
import torch

import config      # integration_harden root is on sys.path for every consumer of this package


class OmDet:
    """OmDet-Turbo open-vocab detector (Apache, transformers). Stateless: pass the phrase each call.
    Loads from a LOCAL, offline copy (see LOCAL below) in ~1s -- see README 'OmDet offline' -- so it
    never hangs fetching the Swin backbone from the HF Hub."""
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


class Eyes:
    def __init__(self):
        from ultralytics import YOLO
        self._bg = YOLO(config.BG_SEG_MODEL)                    # closed-set YOLO26-seg: fast background
        self.device = config.resolve_device()                   # ultralytics device ("0"/"cpu"/"mps")
        self.tdevice = config.resolve_torch_device()            # torch device ("cuda"/"cpu"/"mps")
        self._sam = None                                        # lazy
        print(f"[integration] eyes bg={config.BG_SEG_MODEL} "
              f"dev={self.device}/{self.tdevice}", flush=True)

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
