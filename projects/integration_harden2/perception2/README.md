# perception2

SAM3 twin of the `perception` package. Same interface, one model instead of two: SAM3 does
open-vocab detection AND masks in a single forward, replacing OmDet + SAM2.1. It is now the DEFAULT highlight backend (config `SEGMENTER=sam3`, i.e. `SCENE_SEG=sam3`); `perception` (OmDet+SAM2.1) is the legacy path behind `SCENE_SEG=omdet`.

| File | What it is |
|------|-----------|
| `__init__.py` | Public interface. Same names as `perception`, plus `build_engine`. |
| `engine.py` / `vlm_client.py` / `detectors.py` | Copied verbatim from `perception` (migration). The engine is pure logic; models are injected. |
| `sam3_backend.py` | `Sam3Backend`: `detect` + `mask_for_box` from one SAM3-nf4 forward, box->mask cached. `python3 sam3_backend.py` = real smoke test. |
| `concept.py` | Concept front-end: user phrase -> bare SAM3 concepts (+ class synonyms), VLM or offline. `python3 concept.py` = self-test. |

## Interface

`perception2` is SELF-CONTAINED: it imports nothing from `perception`, so a consumer swaps by
changing one import, and `perception` can then be deleted. This is the single swap point.

engine.py, vlm_client.py and detectors.py are copies from `perception`; sam3_backend.py and
concept.py are new. The highlight path runs on SAM3; detectors.OmDet stays only for background
parity and is pruned in a later revision.

## Wiring the SAM3 path

```python
import perception2
from perception import vlm_client as vlm
engine = perception2.build_engine(vlm_ask=vlm.ask)      # loads SAM3-nf4, wires the engine
```

At highlight time, turn the user phrase into concepts once (never per frame):

```python
from perception2 import extract_concepts, make_vlm_asker
ask = make_vlm_asker()                                  # text-only Gemma call
concepts = extract_concepts(phrase, ask=ask)            # 'the vehicles' -> 'car, van, truck, bus, ...'
# store `concepts` as the engine target; the per-frame detect() grounds it with SAM3
```

## Why the concept front-end

SAM3 is a concept segmenter. It wants bare nouns and does not generalize one class to another
(ask for `car` and vans stay unmarked). The front-end expands a phrase into an explicit synonym
set before it reaches SAM3. Evidence: `bench/sam3-mask-bench/RESULTS.md`.

## Precision + speed

`Sam3Backend(precision=..., compile=...)` and `build_engine(precision=..., compile=...)`:

| precision | compile | fwd p50 | VRAM | note |
|-----------|:------:|--------:|-----:|------|
| `nf4` (default) | no | 452 ms | 1054 MiB | smallest VRAM, fast load, no compile |

The live app fixes precision to `nf4` (config `SAM3_PRECISION`, a load-time constant, no env
override). The `precision=`/`compile=` arguments below are for the bench, which sweeps the other rows.
| `bf16` | yes | 265 ms | 2219 MiB | lossless |
| `fp8` | yes | 202 ms | 1710 MiB | fastest; needs `compile=True` (torchao fp8 kernels) |

`compile=True` builds on the first call (~1-3 min, one-time per process): use it for a long-running
service, not short CLI runs. Full table + method: `bench/sam3-mask-bench/results/2026-09-03-sam3-quant-latency.md`.

## Open findings

- The VLM presence gate suppresses collective/plural targets. On "all the vehicles" the gate prompt
  becomes "the all the vehicles" and the VLM returns no single HIGHLIGHT target, so `present=False`
  and a valid highlight is dropped. SAM3 has its own per-detection scores, so for the SAM3 path the
  gate may run on a singular representative concept, or be replaced by a score threshold. OWNER
  DECISION, not yet made.

## Wired into mvd (2026-09-07)

`mvd.py` selects the highlight backend with `SCENE_SEG`: `sam3` (DEFAULT, `Sam3Backend`, one
model) or the legacy `omdet` (OmDet+SAM2.1). `build_highlight()` in mvd owns the switch; with
`sam3` OmDet and SAM2.1 never load. The live path turns the user phrase
into SAM3 concepts with `phrase_concepts()` (attribute-preserving, no model call): `the red
backpack` -> `red backpack`, `all the vehicles` -> the synonym set. The VLM front-end
(`extract_concepts`) stays available but is not on the live path, because its prompt drops
colours and would highlight every car when the user asked for the white one (SAM3 discriminates
attributes: `bench/sam3-mask-bench/RESULTS.md`, Web candidates, finding 2). Per-frame
SAM3 forwards are rate-limited by `SCENE_SAM3_PERIOD` (default 1.0 s) so the highlight loop does
not hog the GPU the VLM and whisper share. Boot the desk stack with
`VIDEO=webcam SCENE_TTS=off bash tools/desk-test/up.sh` (sam3 is the default; no translator knob).
The default flip to `sam3` is DONE. OUTSTANDING: delete `perception/` and rename this package
(`engine.py`, `vlm_client.py`, `detectors.py` here are still verbatim copies).

## Status

`chain_demo.py` runs the full instruction -> concept -> SAM3 -> masks path.
Measured comparison lives in `bench/sam3-mask-bench/`.
