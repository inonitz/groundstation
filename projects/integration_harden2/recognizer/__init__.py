"""The Recognizer module. Functional code only; the benchmark lives in
bench/hebrew-command-bench and is the development home (sync rule in README.md)."""
from .recognizer import _nums_en, emergency, numbers_vs_mission, recognize_direct, register_imperative
from .selftest import selftest
from .pipeline import Pipeline

__all__ = ["_nums_en", "emergency", "numbers_vs_mission", "recognize_direct", "register_imperative",
           "selftest", "Pipeline"]
