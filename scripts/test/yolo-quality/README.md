# YOLO image-quality test (agent3)

Measures seg detection/classification quality and depth output across model
variants and degraded input. Answers ROADMAP question 4.1.5: is a smaller
INT4/INT8 seg/depth model worth adopting?

## Run

The seg/depth models live outside the repo at `/root/models/vision/`. The
harness needs `onnxruntime`, `numpy`, and `Pillow` (not repo deps — install into
a scratch target and point `PYTHONPATH` at it):

```
pip install --target /tmp/pylib onnxruntime onnx
PYTHONPATH=/tmp/pylib python3 yolo_quality.py
```

## Axes

- Resolution: 384 vs 480 (both baked into their own ONNX export).
- Precision: fp32 vs the `.int4` and `.int8` files.
- Input quality: original, JPEG q75/q50/q25/q10, and a 320x240 downscale
  roundtrip (the lean-dashboard camera path).

## Subjects

`person_standing` / `person_walking` thumbnails (the hat-follow target class)
and COCO `dog.jpg` (a small, real-photo object that exposes compression loss).
The `hatchback` thumbnail was dropped — it scored zero detections even at
baseline 384, so it carried no signal.

See the `## Report` section of `docs/active/sitl-agent3-qa-cleanups-spec.md` for
the numbers and the verdict.
