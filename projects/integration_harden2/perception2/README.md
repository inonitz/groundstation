# perception2

The vision module of harden2. SAM3 gives open-vocab boxes AND masks in one forward pass.
`vision.py` runs every vision request as its own task thread; the rest is pure logic around it.

## Sections

| section | content |
|---|---|
| Files | what each file does |
| Threading | the tasks, and who may call SAM3 |
| Tests | where it is tested |

## Files

| file | role |
|---|---|
| `vision.py` | `Vision`: count / highlight / clear / describe. One task thread each; results go to the app through `Sinks` callbacks. API: docs/api-harden2/perception.h. |
| `dispatcher.py` | `Dispatcher`: one thread on a condition variable starts one thread per task, at most `config.VISION_MAX_TASKS`; past that a request is refused (FULL). |
| `sam3_lock.py` | `PriorityLock`: one SAM3 forward pass at a time; a user command outranks a highlight refresh. |
| `backend.py` | The backend contract (`detect -> (status, hits)`, `mask_for_box`, `DETECT_*`), the `BACKENDS` registry, and `BackendLoader` (loads it on its own thread; the "sam3" status row). |
| `sam3_backend.py` | `Sam3Backend`: SAM3-nf4 detect + masks in one forward, box->mask cached. A GPU out-of-memory calls die(). |
| `engine.py` | `PerceptionEngine`: relative-confidence gate, mask hygiene, VLM fallback, presence gate. Models are injected. |
| `concept.py` | `phrase_concepts`: a user phrase -> the bare SAM3 concepts, with class synonyms. |
| `counting.py` | `count_instances` (dedup contained boxes), `median_count`. |
| `verify.py` | Split-and-verify for relation phrases ("backpack held by a child"). |
| `lexicon.py` | The HE->EN target correction net under Gemma. |
| `vlm_client.py` | The Gemma vision prompt: describe the frame, or say where a target is. |

## Threading

Owner design (2026-09-22/23): a count is fire and forget; a highlight thread lives until it is
cleared or gives up (HL_GIVEUP s without a hit), re-detecting every SAM3_PERIOD counted from
the START of each detect; one highlight at a time. Every SAM3 forward pass holds the priority
lock; tasks sleep outside it, so a waiting task never blocks another. More threads or batching
add no SAM3 speed (bench/sam3-concurrency-bench/RESULTS.md): this design is for clarity.

## Tests

`test/test_perception2.py` (one file per module). The vision tests run the REAL service,
dispatcher and lock on a stand-in backend (`test/support.py`); SAM3 itself needs the GPU.
