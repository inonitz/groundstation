# sam3

The SAM3 service: one model that gives open-vocab boxes AND masks in one forward pass. The
app builds the loader once at start; the vision system (perception2/) calls it through the
contract. Importing the package loads no model: torch arrives on the loader's thread.

| file | role |
|---|---|
| `contract.py` | The backend contract: `detect -> (status, hits)`, `mask_for_box`, `DETECT_OK` / `DETECT_NOT_READY`. |
| `loader.py` | `BackendLoader`: loads the backend on its own thread at start; the "sam3" status row; `BACKENDS`. |
| `save_nf4.py` | Saves SAM3 once in nf4 form to `config.SAM3_NF4_DIR`; the install script runs it when the folder is missing. |
| `model.py` | `Sam3Backend`: SAM3-nf4 (loaded ready from `SAM3_NF4_DIR`) detect + masks; one image encoding per detect, then text + detector per concept; box->mask cached; `_dedup_overlaps`. A GPU out-of-memory calls die(). |

API: docs/api-harden2/sam3.h. Tests: test/test_sam3.py (the real model: HARDEN2_GPU_TESTS=1).
