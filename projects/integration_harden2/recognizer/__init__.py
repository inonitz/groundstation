"""The Recognizer module. Functional code only; the benchmark lives in
tools/bench/hebrew-command-bench and is the development home (sync rule in README.md)."""
from .recognizer import recognize, _nums_en, route, emergency, selftest
from .pipeline import Pipeline

from .recognizer import register_imperative, recognize_direct, numbers_vs_mission  # noqa: E402,F401 -- exported for the tests (2026-09-08)
