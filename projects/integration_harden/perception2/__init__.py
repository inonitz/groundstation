"""perception2 -- the SAM3 successor to the `perception` package. It is SELF-CONTAINED: it imports
nothing from `perception`, so `perception` can be deleted once scene_omdet points here. This is the
single swap point.

Same public interface as `perception` (engine + parsing + vlm_client + detectors), plus:
  - sam3_backend.Sam3Backend : one SAM3-nf4 forward does detection AND masks (replaces OmDet+SAM2.1)
  - concept.extract_concepts : user phrase -> bare SAM3 concepts + class synonyms (SAM3 needs concepts)
  - build_engine             : wire a PerceptionEngine on the SAM3 backend in one call

engine.py, vlm_client.py and detectors.py are copied verbatim from `perception` for the migration.
The highlight path now runs on Sam3Backend; detectors.OmDet is retained only for background parity
and is pruned in a later revision.
"""
from .engine import (PerceptionEngine, parse_highlight, ascii_only,
                     scale_vlm_box, selftest)
from .sam3_backend import Sam3Backend
from .concept import extract_concepts, make_vlm_asker

__all__ = ["PerceptionEngine", "parse_highlight", "ascii_only", "scale_vlm_box", "selftest",
           "Sam3Backend", "extract_concepts", "make_vlm_asker", "build_engine"]


def build_engine(vlm_ask, backend=None, precision="nf4", compile=False,
                 floor=0.12, draw_conf=0.30, rel=0.65, **kw):
    """Wire a PerceptionEngine on the SAM3 backend. `backend` injects a pre-loaded Sam3Backend
    (or a fake for tests); otherwise one is loaded. Same knobs as scene_omdet."""
    be = backend or Sam3Backend(precision=precision, compile=compile)
    return PerceptionEngine(detect=be.detect, mask_for_box=be.mask_for_box, vlm_ask=vlm_ask,
                            floor=floor, draw_conf=draw_conf, rel=rel, **kw)
