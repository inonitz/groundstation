# Spec - perception2 vision-backend contract

Recovered 2026-09-21 from perception2/backend.py. The contract was defined as a C header in an earlier
session and never filed, so it was lost to compaction. This doc is the record, so it never vanishes again.

## Sections

| section | content |
|---|---|
| Objective | the one interface between the app and the vision model |
| Contract | the two methods a backend must provide |
| Registration | how a backend is chosen |
| Invariants | the rules a backend and its callers obey |

## Objective

Define the single interface between the app and the vision backend. The app reaches the vision model only
through this contract. No consumer reaches into a specific backend, and none reaches into the old
perception package.

## Contract

A vision backend is a class with two methods (perception2/backend.py, VisionBackend Protocol).

`detect(frame_bgr, phrase, conf=0.30, topk=8) -> (status, hits)`
- Input: a BGR frame, an English noun phrase, a confidence floor, a max hit count.
- Output: a status code and the hits. The codes live in perception2/backend.py:
  - `DETECT_OK`: the detection ran. hits may be empty when nothing matched.
  - `DETECT_NOT_READY`: the backend is still loading.
- hits is up to topk entries, each `{'label': str, 'conf': float, 'box': (x1, y1, x2, y2)}`.
- A GPU out-of-memory is fatal: the backend calls die() (owner ruling 2026-09-22). torch reports it
  only by a throw, so one narrow catch converts it to die().

`mask_for_box(frame_bgr, box) -> mask | None`
- The mask this backend cached for one box in the last detect().
- None is the status for a miss.

## Registration

`BACKENDS` maps a SCENE_SEG name to a zero-arg factory. Today it is `{"sam3": Sam3Backend}`.
The engine builds one backend at startup from SCENE_SEG. The pick is one-time, not a per-frame dispatch.
To add a backend: write a class with the two methods, then add one line to BACKENDS.

## Invariants

- detect never throws. It reports failure through its status code, or die() on a fatal error.
- The backend is chosen once, at startup, from SCENE_SEG. It is not swapped or reloaded while the app runs.
- The app talks to the backend only through these two methods.
- backend.py is the Python translation of the C header we defined.

## Change impact

detect returns (status, hits) since 2026-09-22. Every caller adopted it: the engine, the mvd wrapper and
tasks, verify, and the benches that read the return. mask_for_box is unchanged; None already carries its status.
