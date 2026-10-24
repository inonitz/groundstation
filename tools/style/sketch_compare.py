#!/usr/bin/env python3
"""Compare a drawing with its design document: every SVG text of the page must appear verbatim
in the document, and every path of the page must appear in the document's inventory. Then compare
two pages: the same set of texts and paths. Usage: sketch_compare.py DOC.md PAGE.html [OTHER.html]"""
import re
import sys


def inventory(path):
    html = open(path, encoding="utf-8").read()
    svg = html[html.index("<svg"):html.index("</svg>") + 6]
    texts = [t for t in re.findall(r'<text[^>]*>([^<]*)</text>', svg) if t.strip()]
    paths = re.findall(r'<path class="(l-[a-z]+)" d="([^"]+)"', svg)
    return texts, paths


doc = open(sys.argv[1], encoding="utf-8").read()
texts, paths = inventory(sys.argv[2])
missing = [t for t in texts if t not in doc]
missing_paths = [f"{c}: {d}" for c, d in paths if f"{c}: {d}" not in doc]
print(f"{sys.argv[2]}: {len(texts)} texts, {len(paths)} paths; missing in the document: {len(missing)} texts, {len(missing_paths)} paths")
for m in missing[:20]:
    print("  text not in the document:", m)
if len(sys.argv) > 3:
    t2, p2 = inventory(sys.argv[3])
    same = sorted(texts) == sorted(t2) and sorted(paths) == sorted(p2)
    print(f"{sys.argv[2]} against {sys.argv[3]}: {'IDENTICAL' if same else 'DIFFERENT'} "
          f"({len(set(texts) ^ set(t2))} texts differ, {len(set(paths) ^ set(p2))} paths differ)")
    sys.exit(0 if same and not missing and not missing_paths else 1)
sys.exit(1 if missing or missing_paths else 0)
