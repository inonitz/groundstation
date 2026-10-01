"""perception2 -- the vision system: the vision service (vision.py), the engine, the
dispatcher, the SAM3 priority lock, and the text, concept, counting and verify helpers.
It uses the SAM3 service (sam3/) through its contract. See README.md for the file map."""
from .concept import phrase_concepts
from .counting import count_instances, median_count

__all__ = ["phrase_concepts", "count_instances", "median_count"]
