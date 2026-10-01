# perception2

The vision system of harden2. It uses two services: SAM3 (sam3/: open-vocab boxes AND masks
in one forward pass) and Gemma. `vision.py` runs every vision request as its own task thread;
the rest is pure logic around it.

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
| `engine.py` | `PerceptionEngine`: relative-confidence gate, mask hygiene, VLM fallback, presence gate. Models are injected. |
| `concept.py` | `phrase_concepts`: a user phrase -> the bare SAM3 concepts, with class synonyms. |
| `counting.py` | `count_instances` (dedup contained boxes), `median_count`. |
| `verify.py` | Split-and-verify for relation phrases ("backpack held by a child"). |
| `lexicon.py` | The HE->EN target correction net under Gemma. |
| `vlm_client.py` | The Gemma vision prompt: describe the frame, or say where a target is. |

The SAM3 model, its loader and the backend contract live in `sam3/` (owner D2, 2026-09-29).
The box overlap math is `util/boxes.py`.

## Threading

Owner design (2026-09-22/23): a count is fire and forget; a highlight thread lives until it is
cleared or gives up (HL_GIVEUP s without a hit), re-detecting every SAM3_PERIOD counted from
the START of each detect; one highlight at a time. Every SAM3 forward pass holds the priority
lock; tasks sleep outside it, so a waiting task never blocks another. More threads or batching
add no SAM3 speed (bench/sam3-concurrency-bench/RESULTS.md): this design is for clarity.

## Tests

`test/test_perception2.py` (one file per module). The vision tests run the REAL service,
dispatcher and lock on a stand-in backend (`test/support.py`); SAM3 itself needs the GPU.
