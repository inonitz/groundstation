"""SAM3 backend: one model that does BOTH open-vocab detection and masks. It replaces the
OmDet (detect) + SAM2.1 (mask) pair with a single forward per phrase.

The perception engine injects `detect` and `mask_for_box` as SEPARATE callables, but SAM3
produces boxes AND masks together. So detect() runs SAM3 once, caches every box->mask, and
mask_for_box() returns the cached mask. There is no second inference.

Model: facebook/sam3 (transformers-native), loaded int4-nf4 (bitsandbytes). Measured on an
RTX 5070 (8 GiB Blackwell): ~918 MiB peak, ~0.4 s per phrase. Detection is on-demand (the
'highlight' keyword), never per background frame. Evidence: tools/bench/sam3-mask-bench/RESULTS.md.

SAM3 is a CONCEPT segmenter. It wants bare nouns ('person','window','car'), not instructions,
and it does NOT generalize one class to another ('car' will not return a van). Feed it explicit
concepts; the concept front-end (concept.py) builds those. A comma-separated phrase is treated as
several concepts and their results are unioned -- the same convention OmDet uses.
"""
import torch
from PIL import Image

MODEL_DIR = "/root/models/vision/sam3-official"


class Sam3Backend:
    """detect(frame_bgr, phrase, conf) -> [{"label","conf","box"} ...] sorted by conf desc.
    mask_for_box(frame_bgr, box) -> bool mask (HxW) or None. Both contracts match the engine's."""

    def __init__(self, model_dir=MODEL_DIR, precision="nf4", compile=False,
                 mask_threshold=0.5, lazy=False):
        """precision: 'nf4' (smallest VRAM, default, fast load), 'bf16' (lossless), or 'fp8'
        (torchao dynamic-activation). compile: torch.compile the model -- REQUIRED for fp8 to hit
        its 202 ms; adds ~1-3 min one-time build on the first call. Latency evidence:
        tools/bench/sam3-mask-bench/results/2026-09-03-sam3-quant-latency.md."""
        self.model_dir = model_dir
        self.precision = precision
        self.compile = compile
        self.mask_threshold = mask_threshold
        self.model = None
        self.proc = None
        self._cache = {}          # {box_tuple: bool mask} for the frame detect() last ran on
        if not lazy:
            self._load()

    def _load(self):
        from transformers import Sam3Model, Sam3Processor, BitsAndBytesConfig
        if self.precision == "nf4":
            q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
            self.model = Sam3Model.from_pretrained(self.model_dir, quantization_config=q,
                                                   dtype=torch.bfloat16).eval()   # bnb places it on GPU
        else:
            self.model = Sam3Model.from_pretrained(self.model_dir, dtype=torch.bfloat16).eval().to("cuda")
            if self.precision == "fp8":
                # transformers' TorchAoConfig converter is broken for Sam3Model, so quantize in place.
                from torchao.quantization import quantize_, Float8DynamicActivationFloat8WeightConfig
                quantize_(self.model, Float8DynamicActivationFloat8WeightConfig())
            elif self.precision != "bf16":
                raise ValueError(f"precision must be nf4|bf16|fp8, got {self.precision!r}")
        if self.compile:
            self.model = torch.compile(self.model)
        self.proc = Sam3Processor.from_pretrained(self.model_dir)
        print(f"[perception2] SAM3 ready ({self.precision}{'+compile' if self.compile else ''})", flush=True)

    def _run(self, pil, concept, conf):
        """One SAM3 forward for one bare concept. Returns (boxes, masks, scores) as numpy."""
        inputs = self.proc(images=pil, text=concept, return_tensors="pt").to("cuda")
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
        with torch.no_grad():
            out = self.model(**inputs)
        r = self.proc.post_process_instance_segmentation(
            out, threshold=conf, mask_threshold=self.mask_threshold,
            target_sizes=inputs.get("original_sizes").tolist())[0]
        if len(r["scores"]) == 0:
            return [], [], []
        boxes = r["boxes"].float().cpu().numpy()
        masks = r["masks"].cpu().numpy().astype(bool)      # (N,H,W) at original resolution
        scores = r["scores"].float().cpu().numpy()
        return boxes, masks, scores

    def detect(self, frame_bgr, phrase, conf=0.30, topk=8):
        """Run SAM3 on each comma-separated concept, union the results, cache box->mask."""
        if self.model is None:
            self._load()
        self._cache = {}
        if not phrase:
            return []
        concepts = [c.strip() for c in phrase.split(",") if c.strip()] or [phrase]
        pil = Image.fromarray(frame_bgr[:, :, ::-1])       # engine passes cv2 BGR; SAM3 wants RGB
        dets = []
        for concept in concepts:
            boxes, masks, scores = self._run(pil, concept, conf)
            for bx, mk, sc in zip(boxes, masks, scores):
                x1, y1, x2, y2 = (int(v) for v in bx)
                box = (x1, y1, x2, y2)
                self._cache[box] = mk
                dets.append({"label": concept, "conf": float(sc), "box": box})
        dets.sort(key=lambda d: -d["conf"])
        return dets[:topk]

    def mask_for_box(self, frame_bgr, box):
        """Return the mask SAM3 already produced for this box in the last detect(). None on miss."""
        return self._cache.get(tuple(box))


def _smoke():
    """Real smoke test (needs the GPU + model). `python3 sam3_backend.py`."""
    import cv2
    img = "/root/groundstation/tools/bench/sam3-mask-bench/candidates/img0.png"
    frame = cv2.imread(img)
    be = Sam3Backend()
    dets = be.detect(frame, "window", conf=0.30)
    ok = len(dets) > 0 and be.mask_for_box(frame, dets[0]["box"]) is not None
    m = be.mask_for_box(frame, dets[0]["box"]) if dets else None
    same = (m is not None and m.shape[:2] == frame.shape[:2])
    print(f"detect 'window' -> {len(dets)} dets; top conf {dets[0]['conf']:.2f}" if dets else "no dets")
    print(f"mask_for_box hit={ok} shape_matches_frame={same}")
    print("SAM3 backend smoke CLEAN" if (ok and same) else "SAM3 backend smoke FAILED")
    return 0 if (ok and same) else 1


if __name__ == "__main__":
    raise SystemExit(_smoke())
