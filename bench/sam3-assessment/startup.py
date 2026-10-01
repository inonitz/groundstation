"""What SAM3 costs at start (T8, R10): the torch and transformers imports, the model
load, and the first (cold) detect. Every repeat is a fresh Python process, so nothing is
cached in memory; the OS file cache stays warm, as on a second app start.
imports: CPU only. load: GPU ~1 min.
Run: python3 bench/sam3-assessment/startup.py [imports|load|all]"""
import json
import re
import subprocess
import sys

import common

REPEATS = 3
IMPORTS = {
    "torch": "import torch",
    "transformers Sam3Model": "from transformers import Sam3Model, Sam3Processor",
    "perception2 (the app's import)": "import perception2",
}
LOAD = """
import json, sys, time
t0 = time.perf_counter()
sys.path.insert(0, %r)
import common
from sam3.model import Sam3Backend
t_import = time.perf_counter()
sam3 = Sam3Backend()
t_load = time.perf_counter()
frame = common.frames(1)[0]
sam3.detect(frame, common.PHRASE_ONE, conf=0.3)
t_first = time.perf_counter()
sam3.detect(frame, common.PHRASE_ONE, conf=0.3)
t_second = time.perf_counter()
print(json.dumps({
    "import_ms": (t_import - t0) * 1000,
    "load_ms": (t_load - t_import) * 1000,
    "first_detect_ms": (t_first - t_load) * 1000,
    "second_detect_ms": (t_second - t_first) * 1000,
}))
"""


def import_ms(statement):
    """Cumulative microseconds of the statement's top module, from -X importtime."""
    done = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", statement],
        cwd=common.HARDEN,
        capture_output=True,
        text=True
    )
    total = 0
    cumulative = 0

    for line in done.stderr.splitlines():
        match = re.match(r"import time:\s+\d+ \|\s+(\d+) \| (\S.*)$", line)
        if match is None:
            continue
        cumulative = int(match.group(1))
        if not match.group(2).startswith(" "):
            total += cumulative              # a top-level module of the statement
    return total / 1000


def imports():
    out = {}
    for name, statement in IMPORTS.items():
        out[name] = common.stats([import_ms(statement) for _ in range(REPEATS)])
        print(f"import {name:32s} {out[name]}", flush=True)
    return out


def loads():
    rows = []
    done = None
    for _ in range(REPEATS):
        done = subprocess.run(
            [sys.executable, "-c", LOAD % common.HERE],
            cwd=common.HARDEN,
            capture_output=True,
            text=True
        )
        rows.append(json.loads(done.stdout.strip().splitlines()[-1]))
    out = {}
    for key in rows[0]:
        out[key] = common.stats([row[key] for row in rows])
        print(f"{key:18s} {out[key]}", flush=True)
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {"repeats": REPEATS}
    if mode in ("imports", "all"):
        results["imports_ms"] = imports()
    if mode in ("load", "all"):
        results["load"] = loads()
    common.write_result(f"startup-{mode}", results)
    return


if __name__ == "__main__":
    main()
