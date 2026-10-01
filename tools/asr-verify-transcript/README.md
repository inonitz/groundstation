# asr-verify-transcript: label the recorded clips

A local web page to give each of the 139 recorded clips (datasets/asr) its confirmed sentence and
expected result. The result, datasets/asr/recordings.json, is the input of path B of the
recognizer benchmark (bench/recognizer/). It replaced bench/recognizer/confirm.py (owner UI1,
2026-09-29: "The UI is not intuitive at all").

| section | content |
|---|---|
| Run it | the one command |
| The page | what each part does, the keys |
| Files | what each file is |
| Tests | how to run them |

## Run it
```
python3 /root/groundstation/tools/asr-verify-transcript/server.py
```
It prints `open http://127.0.0.1:8766/`; VS Code forwards the port. Python's standard library
only; it listens on 127.0.0.1 only. `--port P` picks another port; `--out PATH` writes another
file (for a test, a copy). Never run it while another tool writes the same recordings file.

## The page
- One clip at a time: "Clip N / 139", Saved or New, a play button (it plays when the clip opens).
- "Whisper heard": the ASR's text. Under it, what the app did live.
- "The sentence that was said": a right-to-left text box. It starts as whisper's EXACT text,
  marked "whisper's text"; once changed it is marked "edited" (a link goes back). What the box
  holds is what is saved. Clips 63-100 have no whisper text: type the sentence.
- "What the drone should do" (owner UI1 (3)): step rows, each an action (fly forward / back /
  left / right, go up / down, turn right / left / either way, take off, land, wait) and a
  number (m, degrees or s; empty = any amount in that direction), with add and remove; or one
  of the buttons "Nothing flies", "Halt", "Vision request". The signs are the benchmark's:
  forward dx+, right dy+, up dz+, turn right (clockwise) = +degrees. "In words" shows what will
  be saved. The live-list notation or JSON stays as a folded "Advanced" field.
- "Vision request" (owner UI1 (4)): the kind (Highlight, Count, Describe, Any kind) and the
  target in English, what Gemma must name: a comma between words, a slash between synonyms
  ("red, chair / seat"). It starts from the nearest known vision request. The kind is saved
  in its own field, `vision` (owner SC1, 2026-09-30), and the target as the scorer's keyword
  groups; a request of another kind fails. "Any kind" saves no `vision`.
- "Nothing was said" (Alt+N): an empty sentence, nothing flies, saved.
- "Remove from the set" (owner B4 (8)): asks for the reason, then saves the clip with
  `"removed": true`, `removed_reason` and a review plan; the clip stays on disk, path B skips
  it, and the page shows "Removed: <reason>". Saving the clip again puts it back.
- When whisper wrote nothing (clips 63-100), the nearest sentences follow what you type.
- "Nearest known sentences": the 5 closest cases of datasets/recognizer/, with their plan and
  similarity: offers only ("use this sentence", "use this plan", "use both").
- Accept saves and opens the next clip. "Not gradable" saves the clip as review. Back and Skip
  move without saving. "Go to clip" opens any clip; a saved clip shows what was saved, and
  Accept replaces it.
- Keys: Enter accept, Alt+P play, Alt+1..5 use that sentence and plan, Alt+Left back, Alt+Right skip,
  Alt+R not gradable.
- Every save rewrites the whole file at once (atomically), in clip order. The page opens at the
  first clip not saved.

## Files
| file | role |
|---|---|
| `server.py` | the web server and its JSON API (/api/state, /api/clip/N, /api/parse, /api/rows, /api/vision, /api/save, /audio/N) |
| `labels.py` | the proposal (nearest case), the step rows and their signs, the plan in plain words, the typed plan, the recordings file |
| `index.html` | the page (one file: markup, style, script) |
| `test_labels.py`, `test_server.py`, `test_page.py` | the tests (test_page.py: a real browser) |
| `install-browser.sh`, `screenshots.py` | the headless browser, and a screenshot of every state |

## Tests
```
python3 -m pytest -q -p no:cacheprovider /root/groundstation/tools/asr-verify-transcript/
```
test_page.py drives the page in a real headless Chromium; it is skipped until the browser is
installed (its own folder, never the main environment):
```
bash /root/groundstation/tools/asr-verify-transcript/install-browser.sh
PYTHONPATH=/root/.venvs/asr-verify-browser python3 -m pytest -q -p no:cacheprovider /root/groundstation/tools/asr-verify-transcript/
PYTHONPATH=/root/.venvs/asr-verify-browser python3 /root/groundstation/tools/asr-verify-transcript/screenshots.py
```
screenshots.py saves every card state (desktop and phone width) on a copy of the file and
prints every browser error.
They run on copies in pytest's tmp folder, never on datasets/asr/recordings.json. The server
tests use a real local HTTP server.
