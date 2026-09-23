# perception2

The vision layer of harden2. SAM3 gives open-vocab boxes AND masks in one forward. One consumer
thread runs every SAM3 call; the rest of the package is pure logic around it.

## Sections

| section | content |
|---|---|
| Files | what each module does |
| Threading | who may call SAM3 |
| Tests | where each module is tested |

## Files

| file | role |
|---|---|
| `backend.py` | The backend contract: `detect -> (status, hits)`, `mask_for_box`, the `DETECT_*` status codes, the `BACKENDS` registry. Spec: docs/spec-perception2-backend-contract.md. |
| `sam3_backend.py` | `Sam3Backend`: SAM3-nf4 detect + masks in one forward, box->mask cached. A GPU OOM calls die(). `python3 -m perception2.sam3_backend` = real smoke test. |
| `engine.py` | `PerceptionEngine`: relative-confidence gate, mask hygiene, VLM fallback, presence gate. Models are injected. |
| `task_queue.py` | `TaskQueue`: the ONE SAM3 consumer. Condition variable (no poll), priority, delayed tasks, a cap (`config.VISION_MAX_TASKS`). |
| `text_parse.py` | `parse_highlight`, `parse_count`, `ascii_only`. Pure string parsing. |
| `concept.py` | `phrase_concepts`: a user phrase -> the bare SAM3 concepts, with class synonyms. |
| `counting.py` | `count_instances` (dedup contained boxes), `median_count`. |
| `verify.py` | Split-and-verify for relation phrases ("backpack held by a child"). |
| `lexicon.py` | The HE->EN target correction net under Gemma. |

## Threading

Only the `TaskQueue` consumer thread (named `sam3-worker` in mvd) calls SAM3 and writes highlight
state. Producers submit tasks. Evidence that more threads or batching do not help:
bench/sam3-concurrency-bench/RESULTS.md.

## Tests

One test file per module (owner ruling 2026-09-22): `test/test_<module>.py`. Done so far:
`test_text_parse.py`, `test_task_queue.py`, `test_verify.py`, `test_lexicon.py`, `test_count.py`.
The engine and concept tests still sit in `test_perception.py` until the consolidation pass.
