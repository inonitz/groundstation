"""SAM3 backend: one model that does BOTH open-vocab detection and masks. It replaces the
OmDet (detect) + SAM2.1 (mask) pair with a single forward per phrase.

The perception engine injects `detect` and `mask_for_box` as SEPARATE callables, but SAM3
produces boxes AND masks together. So detect() runs SAM3 once, caches every box->mask,
and mask_for_box() returns the cached mask. There is no second inference.

Model: facebook/sam3 (transformers-native), loaded int4-nf4
(bitsandbytes). Measured on an RTX 5070 (8 GiB Blackwell): ~918 MiB peak,
~0.4 s per phrase. Detection is on-demand (the 'highlight' keyword),
never per background frame. Evidence: bench/sam3-mask-bench/RESULTS.md.

SAM3 is a CONCEPT segmenter. It wants bare nouns ('person','window','car'),
not instructions, and it does NOT generalize one class to another ('car'
will not return a van). Feed it explicit concepts; the concept front-end
(concept.py) builds those. A comma-separated phrase is treated as several
concepts and their results are unioned -- the same convention OmDet uses.
"""
import threading

import torch
from PIL import Image

import config
from runtime.fatal import die
from sam3.contract import DETECT_OK
from util.boxes import inside, iou


def _by_conf(d):
    return -d["conf"]


def _dedup_overlaps(dets, iou_thr=0.5, contain_thr=0.7):
    """One box per object. Drop a lower-conf det that overlaps a kept det of
    the SAME label by IoU>iou_thr, or sits mostly (>contain_thr) inside it.
    `dets` must be sorted by conf, high first. SAM3 returns several nested
    boxes for one object; this collapses them. Distinct objects survive."""
    drop = False
    keep = []

    for d in dets:
        drop = False
        for k in keep:
            if k["label"] != d["label"]:
                continue
            if (
                iou(d["box"], k["box"]) > iou_thr
                or inside(d["box"], k["box"]) > contain_thr
            ):
                drop = True
                break
        if not drop:
            keep.append(d)
    return keep


def default_dir(precision, quantize):
    """The ready nf4 folder for the app's nf4 load; the bf16 checkpoint for anything
    else (bf16, fp8, or quantizing it to nf4)."""
    if precision == "nf4" and not quantize:
        return config.SAM3_NF4_DIR
    return config.SAM3_MODEL_DIR


class Sam3Backend:
    """detect(frame_bgr, phrase, conf) -> (status, hits);
        hits = [{"label","conf","box"} ...] sorted by conf desc.
    mask_for_box(frame_bgr, box) -> bool mask (HxW) or None.
    Contract: docs/spec-perception2-backend-contract.md."""

    def __init__(
        self,
        model_dir=None,
        precision=config.SAM3_PRECISION,
        use_compile=False,
        mask_threshold=0.5,
        lazy=False,
        quantize=False
    ):
        """precision: 'nf4' (smallest VRAM, default, fast load), 'bf16' (lossless), or
        'fp8' (torchao dynamic-activation). use_compile: torch.compile the model --
        REQUIRED for fp8 to hit its 202 ms; adds ~1-3 min one-time build on the first
        call.
        nf4 loads the weights saved ready in config.SAM3_NF4_DIR (owner S7 c); with
        quantize=True it quantizes the bf16 checkpoint instead (sam3/save_nf4.py, which
        writes that folder). model_dir overrides the folder.
        Latency evidence:
        bench/sam3-mask-bench/results/2026-09-03-sam3-quant-latency.md."""
        self.mb_quantize = quantize
        self.model_dir = model_dir or default_dir(precision, quantize)
        self.precision = precision
        self.mb_compile = use_compile
        self.mask_threshold = mask_threshold
        self.model = None
        self.proc = None
        # {box_tuple: bool mask} for the frame detect() last ran on
        self._cache = {}
        # One SAM3 model is shared by the worker, the gate thread and the
        # count thread. Serialize detect() and mask_for_box() so two forwards
        # never run at once and the box->mask cache cannot be raced.
        self._lock = threading.Lock()

        if not lazy:
            self._load()
        return

    def _load(self):
        from transformers import Sam3Model, Sam3Processor, BitsAndBytesConfig
        if self.precision == "nf4" and not self.mb_quantize:
            # saved already quantized: its config holds the 4-bit settings
            self.model = Sam3Model.from_pretrained(
                self.model_dir,
                dtype=torch.bfloat16
            ).eval()
        elif self.precision == "nf4":
            q = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True
            )
            # bnb places it on GPU
            self.model = Sam3Model.from_pretrained(
                self.model_dir,
                quantization_config=q,
                dtype=torch.bfloat16
            ).eval()
        else:
            self.model = Sam3Model.from_pretrained(
                self.model_dir,
                dtype=torch.bfloat16
            ).eval().to("cuda")
            if self.precision == "fp8":
                # transformers' TorchAoConfig converter is broken for Sam3Model, so
                # quantize in place.
                from torchao.quantization import (
                    quantize_,
                    Float8DynamicActivationFloat8WeightConfig
                )
                quantize_(self.model, Float8DynamicActivationFloat8WeightConfig())
            elif self.precision != "bf16":
                die(f"precision must be nf4|bf16|fp8, got {self.precision!r}")
        suffix = ""
        if self.mb_compile:
            self.model = torch.compile(self.model)
            suffix = "+compile"
        self.proc = Sam3Processor.from_pretrained(self.model_dir)
        print(f"[sam3] SAM3 ready ({self.precision}{suffix})", flush=True)
        return

    def _run(self, pil, concept, conf):
        """The full model once for one bare concept (image encoder included). detect()
        no longer uses it (S1: the frame is encoded once per call); it stays as the
        reference path of the A/B benchmark (bench/perception/ab_shared_encoding.py).
        Returns (boxes, masks, scores) as numpy."""
        inputs = self.proc(images=pil, text=concept, return_tensors="pt").to("cuda")
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
        with torch.no_grad():
            out = self.model(**inputs)
        return self._post(out, inputs["original_sizes"].tolist(), conf)

    def _encode(self, pil):
        """The image encoder, once per frame. -> (vision embeddings, the frame size
        list post-processing needs)."""
        image = self.proc(images=pil, return_tensors="pt").to("cuda")
        with torch.no_grad():
            embeds = self.model.get_vision_features(
                image["pixel_values"].to(torch.bfloat16)
            )
        return embeds, image["original_sizes"].tolist()

    def _run_concept(self, embeds, sizes, concept, conf):
        """Only the text encoder and the detector, on an encoded frame. Returns
        (boxes, masks, scores) as numpy."""
        text = self.proc(text=concept, return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = self.model(
                vision_embeds=embeds,
                input_ids=text["input_ids"],
                attention_mask=text["attention_mask"]
            )
        return self._post(out, sizes, conf)

    def _post(self, out, sizes, conf):
        """The model output -> (boxes, masks, scores) as numpy, at the frame size."""
        r = self.proc.post_process_instance_segmentation(
            out,
            threshold=conf,
            mask_threshold=self.mask_threshold,
            target_sizes=sizes
        )[0]
        if len(r["scores"]) == 0:
            return [], [], []

        boxes = r["boxes"].float().cpu().numpy()
        masks = r["masks"].cpu().numpy().astype(bool)  # (N,H,W) at original resolution
        scores = r["scores"].float().cpu().numpy()
        return boxes, masks, scores

    def detect(self, frame_bgr, phrase, conf=0.30, topk=8):
        """Encode the frame ONCE (owner S1, 2026-09-29), then run the text and detector
        step for each comma-separated concept; union the results, cache box->mask.
        Returns (DETECT_OK, hits). A GPU out-of-memory is fatal (owner ruling
        2026-09-22): torch reports it only by a throw, nothing catches it, and the crash
        hook dies with the error. Serialized by self._lock: one forward at a time."""
        boxes = []
        masks = []
        scores = []
        box = None
        dets = []
        embeds = None
        sizes = None

        with self._lock:
            if self.model is None:
                self._load()
            self._cache = {}
            if not phrase:
                return DETECT_OK, []

            concepts = [c.strip() for c in phrase.split(",") if c.strip()] or [phrase]
            # engine passes cv2 BGR; SAM3 wants RGB
            pil = Image.fromarray(frame_bgr[:, :, ::-1])
            embeds, sizes = self._encode(pil)
            for concept in concepts:
                boxes, masks, scores = self._run_concept(embeds, sizes, concept, conf)
                for bx, mk, sc in zip(boxes, masks, scores):
                    box = tuple(int(v) for v in bx)
                    self._cache[box] = mk
                    dets.append({"label": concept, "conf": float(sc), "box": box})

            dets.sort(key=_by_conf)
            # SAM3 emits nested boxes per object; keep one each
            dets = _dedup_overlaps(dets)
            return DETECT_OK, dets[:topk]

    def mask_for_box(self, frame_bgr, box):
        """Return the mask SAM3 already produced for this box in the
        last detect(). None on miss. Under the same lock, so a read
        never races a concurrent detect() rebuilding the cache."""
        with self._lock:
            return self._cache.get(tuple(box))
