"""perception2 -- the SAM3 highlight backend plus the concept and counting helpers mvd uses.
Sam3Backend does detection AND masks in one forward. The engine/vlm_client/detectors copies (and the
build_engine helper) were removed 2026-09-11: mvd uses the `perception` engine and
perception.vlm_client, and the highlight runs on Sam3Backend."""
from .sam3_backend import Sam3Backend
from .concept import extract_concepts, make_vlm_asker, phrase_concepts
from .counting import count_instances, median_count

__all__ = ["Sam3Backend", "extract_concepts", "make_vlm_asker", "phrase_concepts",
           "count_instances", "median_count"]
