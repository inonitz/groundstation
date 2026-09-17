"""The concept front-end: turn a user phrase into the bare concept(s) SAM3 needs.

Why this exists (measured): SAM3 is a CONCEPT segmenter. It wants bare nouns and does NOT
generalize one class to another. Ask it for 'car' and it returns cars only -- the vans stay
unmarked (proven on the OCR street scene, RESULTS.md). So a user phrase must become an explicit
set of class synonyms before it reaches SAM3.

Two paths, same output -- a comma-separated concept string SAM3 can ground:
  1. VLM path: a Qwen3-VL text call extracts the object noun(s) from the phrase, returned as
     'CONCEPTS: a, b, c'. This runs ONCE per highlight request, never per frame.
  2. Offline path: a deterministic head-noun + synonym table. No server, so tests and the
     no-VLM fallback both work.

The VLM asker is an INJECTED callable ask(question)->text, mirroring the engine's injected
models. Pass a fake in tests; pass make_vlm_asker() in production.
"""
import re

# Class synonym sets. A user concept on the left expands to every SAM3 noun on the right, because
# SAM3 will not cross classes on its own. Kept small and evidence-driven; extend as cases appear.
SYNONYMS = {
    "vehicle": ["car", "van", "truck", "bus", "motorcycle", "scooter", "bicycle"],
    "car": ["car", "van", "truck"],
    "person": ["person"],
    "people": ["person"],
    "bike": ["bicycle", "motorcycle"],
    # room objects (live 2026-09-09 block B: SAM3 scored 'screens' 0.25 while 'monitor' is a strong SAM3 noun)
    "screen": ["monitor", "television", "screen"], "monitor": ["monitor", "screen"],
    "television": ["television", "tv"], "tv": ["television", "tv"],
    "cabinet": ["cabinet", "cupboard", "wardrobe"], "cupboard": ["cupboard", "cabinet"],
    "closet": ["closet", "wardrobe", "cabinet"], "wardrobe": ["wardrobe", "closet", "cabinet"],
    "drawer": ["drawer", "dresser"], "dresser": ["dresser", "chest of drawers", "cabinet"],
    "window pane": ["window"],
}

# Positional words SAM3 cannot use ('top left window' scored NOTHING live 2026-09-09); the concept keeps the noun.
_POS = re.compile(r"\b(?:top|bottom|left|right|upper|lower|leftmost|rightmost|middle|center|centre|central|nearest|"
                  r"closest|farthest|furthest|far|near|first|second|third|last)(?:-(?:left|right|most))?\b\s*", re.I)
_ONSIDE = re.compile(r"\s+(?:on|at|to|in) the (?:top|bottom|left|right|middle|center|centre|back|front)\b.*$", re.I)
_LEAD = re.compile(r"^(?:(?:the|a|an|that|this|my|some|all|any|these|those)\s+)+", re.I)
_COLOR = re.compile(r"^(?:red|green|blue|yellow|black|white|grey|gray|orange|purple|pink|brown|"
                    r"dark|light)\s+", re.I)
_CONCEPT_LINE = re.compile(r"CONCEPTS?:\s*(.+)", re.I)

CONCEPT_PROMPT = (
    "You control an image segmenter that only understands bare object nouns and cannot generalize "
    "one class to another. From the user's request, list the concrete object nouns to segment. "
    "If the target is a broad category, expand it to the specific object classes that belong to it "
    "(for example a request for vehicles becomes car, van, truck, bus, motorcycle). Drop colours, "
    "sizes and other adjectives. Reply with ONE line, nothing else:\n"
    "CONCEPTS: <noun>, <noun>, ...\n\n"
    'User request: "{phrase}"'
)


def _head_noun(phrase):
    """Strip leading article and one colour adjective; keep the rest as the concept."""
    p = phrase.strip().strip(".?! ,").lower()
    p = _LEAD.sub("", p)
    p = _COLOR.sub("", p)
    return p.strip()


def _singular(w):
    """Naive singularizer so plural user words hit the synonym table ('vehicles' -> 'vehicle')."""
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("ses"):
        return w[:-2]                       # buses -> bus
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _expand(concepts):
    """Apply the synonym table (plural-tolerant); drop duplicates, keep first-seen order. When a
    word is in no table entry, keep it verbatim -- never emit an over-stripped singular."""
    out = []
    for c in concepts:
        c = c.strip().lower()
        if not c:
            continue
        if c in SYNONYMS:
            syns = SYNONYMS[c]
        elif _singular(c) in SYNONYMS:
            syns = SYNONYMS[_singular(c)]
        else:
            syns = [c]
        for syn in syns:
            if syn not in out:
                out.append(syn)
    return out


def _offline(phrase):
    concept = _head_noun(phrase)
    if not concept:
        return ""
    return ", ".join(_expand([concept]))


def _parse_vlm(txt):
    m = _CONCEPT_LINE.search(txt or "")
    if not m:
        return []
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


# Learned cache: a well-formed VLM extraction is image-independent, so memoize it and skip the
# VLM on repeat phrases. In-process by default; load_learned/save_learned persist it across runs.
_LEARNED = {}


def _norm(phrase):
    return " ".join(phrase.lower().strip().strip(".?! ,").split())


def load_learned(path):
    """Seed the learned cache from a JSON file (missing file is fine)."""
    import json, os
    if os.path.exists(path):
        try:
            _LEARNED.update(json.load(open(path)))
        except Exception as e:
            print("[perception2] load_learned failed:", e, flush=True)
    return len(_LEARNED)


def save_learned(path):
    """Persist the learned cache to a JSON file."""
    import json
    json.dump(_LEARNED, open(path, "w"))


def extract_concepts(phrase, ask=None):
    """phrase (a noun clause from parse_highlight) -> 'car, van, truck' for SAM3.
    ask: optional callable ask(question)->text (the VLM). None or failure -> offline table.
    A successful VLM extraction is cached so the same phrase never calls the VLM twice."""
    if not phrase:
        return ""
    key = _norm(phrase)
    if key in _LEARNED:                       # learned from an earlier VLM answer -> no VLM call
        return _LEARNED[key]
    if ask is not None:
        try:
            concepts = _parse_vlm(ask(CONCEPT_PROMPT.format(phrase=phrase)))
            if concepts:                      # only cache a clean parse, never a garbage reply
                out = ", ".join(_expand(concepts))
                _LEARNED[key] = out
                return out
        except Exception as e:
            print("[perception2] concept VLM err, offline fallback:", e, flush=True)
    return _offline(phrase)


_REL = re.compile(r"\s+(?:talking to|speaking to|next to|beside|behind|in front of|between|opposite|across from|to the (?:right|left) of|"
                  r"on the roof of|on top of|under|below|above|near|by|who|that|which|standing on|sitting on|leaning on|parked between|"
                  r"holding|carrying|walking|running|driving|toward|towards|going)\b.*$", re.I)


def phrase_concepts(phrase):
    """Attribute-PRESERVING concept string for the live highlight path (SCENE_SEG=sam3). Strips
    only the leading article and fans a bare category word out through the synonym table:
    'the red backpack' -> 'red backpack', 'all the vehicles' -> 'car, van, truck, ...'.
    Unlike _offline it KEEPS colours and other attributes: SAM3 discriminates attribute phrases
    (sam3-mask-bench RESULTS.md, 'Web candidates' finding 2), and dropping the colour would
    highlight every car when the user asked for the white one. No model call, zero latency."""
    p = (phrase or "").strip().strip(".?! ,").lower()
    p = _LEAD.sub("", p).strip()
    p = _REL.sub("", p).strip() or p        # 'man with glasses talking to woman in yellow shirt' -> 'man with glasses' (live 2026-09-08: the full phrase scored 0.2-0.5 and jittered)
    p = _ONSIDE.sub("", p).strip() or p     # 'window on the left' -> 'window'
    p = _POS.sub("", p).strip() or p        # 'top left window' -> 'window' (2026-09-09)
    if not p:
        return ""
    return ", ".join(_expand([p]))


def make_vlm_asker(url=None, timeout=15):
    """Build a text-only ask(question)->text bound to the resident llama-server. No image: concept
    extraction is a text task. Returns '' on any failure so extract_concepts falls back offline."""
    import requests
    import config
    base = url or config.LLAMA_URL

    def ask(question):
        body = {"messages": [{"role": "user", "content": question}],
                "temperature": 0.0, "max_tokens": 64}
        try:
            r = requests.post(base + "/v1/chat/completions", json=body, timeout=timeout)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""
    return ask


def selftest():
    bad = []
    _LEARNED.clear()
    calls = []
    def counting(q):
        calls.append(q); return "CONCEPTS: car"
    extract_concepts("the cars", ask=counting)
    extract_concepts("the cars", ask=counting)        # 2nd call must hit the learned cache
    if len(calls) != 1:
        bad.append(f"learned cache: VLM called {len(calls)}x for a repeated phrase")
    # Offline: article + colour stripped, head noun kept.
    if _offline("the red backpack") != "backpack":
        bad.append(f"offline: adjective/article not stripped -> {_offline('the red backpack')!r}")
    # Offline: broad category expands to the synonym set.
    if _offline("vehicles") != "car, van, truck, bus, motorcycle, scooter, bicycle":
        bad.append(f"offline: vehicle not expanded -> {_offline('vehicles')!r}")
    # Empty in, empty out.
    if extract_concepts("") != "" or extract_concepts(None) != "":
        bad.append("empty phrase must give empty concepts")
    # VLM path: a good CONCEPTS line is parsed and expanded (car -> car,van,truck).
    fake_ok = lambda q: "CONCEPTS: car, bus"
    if extract_concepts("the vehicles over there", ask=fake_ok) != "car, van, truck, bus":
        bad.append(f"vlm: parse/expand wrong -> {extract_concepts('the vehicles', ask=fake_ok)!r}")
    # VLM path: garbage reply -> offline fallback still yields a concept.
    fake_bad = lambda q: "I am not sure what you mean."
    if extract_concepts("a person", ask=fake_bad) != "person":
        bad.append("vlm garbage must fall back offline")
    # Live path: attributes kept, article stripped, bare category expanded, empty guarded.
    for phrase, want in (("the red backpack", "red backpack"),
                         ("all the vehicles", "car, van, truck, bus, motorcycle, scooter, bicycle"),
                         ("person in the black hat", "person in the black hat"),
                         ("people", "person"),
                         ("", "")):
        if phrase_concepts(phrase) != want:
            bad.append(f"phrase_concepts: {phrase!r} -> {phrase_concepts(phrase)!r}, want {want!r}")
    # VLM path: raising asker -> offline fallback, no crash.
    def fake_raise(q):
        raise RuntimeError("server down")
    if extract_concepts("backpack", ask=fake_raise) != "backpack":
        bad.append("vlm exception must fall back offline")
    return bad


if __name__ == "__main__":
    problems = selftest()
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("concept front-end self-test CLEAN: offline strip/expand, empty guard, "
          "VLM parse/expand, garbage + exception fallback all verified")
