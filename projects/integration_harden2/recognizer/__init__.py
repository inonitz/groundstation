"""The Recognizer module: every sentence in, a Routed out. recognizer.py is its API; the
parser (parse.py) and its steps (fast_path, bypass, guards, rewrites, numbers, lexicon)
are its internals. The benchmark lives in bench/recognizer."""
from .fast_path import emergency
from .guards import numbers_vs_mission
from .parse import recognize_direct
from .recognizer import Decision, Recognizer, Routed, reject_why

__all__ = [
    "Decision",
    "Recognizer",
    "Routed",
    "emergency",
    "numbers_vs_mission",
    "recognize_direct",
    "reject_why",
]
