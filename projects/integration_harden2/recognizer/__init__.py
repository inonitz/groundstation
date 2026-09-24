"""The Recognizer module: every sentence in, a Routed out. recognizer.py is its API; the
parser (parse.py) and its steps (fast_path, bypass, guards, rewrites, numbers, lexicon)
are its internals. The benchmark lives in bench/hebrew-command-bench."""
from .fast_path import emergency
from .guards import numbers_vs_mission
from .parse import recognize_direct
from .recognizer import Recognizer, Routed, reject_why

__all__ = [
    "Recognizer",
    "Routed",
    "emergency",
    "numbers_vs_mission",
    "recognize_direct",
    "reject_why",
]
