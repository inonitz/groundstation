"""The Recognizer module. Functional code only; the benchmark lives in
tools/bench/hebrew-command-bench and is the development home (sync rule in README.md)."""
from .recognizer import recognize, route, emergency, selftest
from .pipeline import Pipeline
