# Go-live wiring — implementation report (2026-09-03)

Author: groundstation-d4 (go-live implementer). Manager: groundstation-0c. Live tester: groundstation-f0.
This document stands alone.

## Objective

Wire the Recognizer into the live app. Before this change the app never ran the Recognizer.
`scene_omdet.py` sent COMPLEX text straight to perception. `run_mvd.sh` never started DictaLM.
The Recognizer was measured and E2E-verified against the mock. Only the production assembly was missing.

The ruled shape (set by the manager, not redesigned here):
- `scene_omdet.py` builds `pipe = Pipeline(wire, vlm_query=<the perception path with the live frame>, say=<voice, print fallback>)`.
- The Router uses `pipe.handle` as its `on_complex`.
- `run_mvd.sh` gains a DictaLM pane. Its output goes to a log file, never `/dev/null`.
- The README data-flow and run sections show the new path.

## Setup

- Tree: clean; the structure pass (commit 9dca582) is already committed. This work is separate and additive.
- All gates ran on the mock or on CPU. No real drone. No GPU bench. The GPU is coordinated by 0c.
- DictaLM runs on CPU with `-ngl 0` (zero VRAM). It does not contend with the GPU.

## Changes

### scene_omdet.py (+30 -17)
1. `main()` reorder. The code builds `voice` first, then `on_text = TextHandler(None, voice)`, then the
   `MVD_DRONE` branch. This order breaks the wiring cycle (handler needs the router, the router needs the
   pipe, the pipe needs `on_text.perceive`).
2. `MVD_DRONE` branch. It builds `wire`, a `_say` helper (append to chat, then speak or print), a
   `Pipeline(wire, vlm_query=on_text.perceive, say=_say)`, and `Router(wire, on_complex=pipe.handle)`,
   then assigns `on_text.router`. On any failure it prints "drone router DISABLED" and leaves the router None.
3. `TextHandler.perceive(text)`. This is the former perception dispatch, now a named method. The Pipeline
   reuses it as `vlm_query`, so a translated English see-question lands on the same ask/highlight path as today.
4. `TextHandler.__call__`. After `_handle_drone`, it calls `self.perceive(text)`.
5. `TextHandler._handle_drone`. With a router present it now consumes every turn (returns True). COMPLEX is
   handled inside `router.handle` by the Pipeline, so it no longer falls through. With no router it returns
   False and `perceive` runs directly — the no-drone path is unchanged.

### run_mvd.sh (+1)
6. A new `dicta` tmux window runs `recognizer/run_dicta_server.sh`. Its output is teed to
   `${TMPDIR:-/tmp}/mvd_dicta.log`. The pane sits right after the `vlm` pane.

### README.md (+13 -2)
7. The data-flow now shows COMPLEX -> `recognizer/pipeline.py` -> {mission | perception | reject}, plus the
   two model servers (DictaLM CPU :18091, Qwen3-VL :18090).
8. A new "Panes" line lists the tmux windows, including `dicta`.
9. The wiring-test count is updated from 26 to 32.

### test/test_scene_wiring.py (new, 6 tests)
10. A scene-level, faked-model wiring test. It locks the new assembly that `test_recognizer.py` does not
    cover: COMPLEX is consumed by the router and routed through the Pipeline, a see-question reaches
    `TextHandler.perceive`, a Hebrew command becomes a mission on the wire, a reject is spoken, emergency
    halts via the router tier, and the no-router path calls `perceive` directly.

## Verification

Every gate is green. Each ran on the mock or on CPU. No real drone. No GPU bench.

| # | Gate | Command (from projects/integration_harden unless noted) | Result |
|---|---|---|---|
| 1 | Unit + wiring tests | `python3 -m pytest test/ -q` | 32 passed |
| 2 | App imports | `python3 -c "import scene_omdet"` | import OK |
| 3 | Live mock smoke (real HTTP vs mock :8080) | `cd projects && python3 integration_harden/test/live_mock_smoke.py` | LIVE MOCK SMOKE PASSED |
| 4 | Real DictaLM translate (CPU, no GPU, no drone) | dicta on :18091, then `chat(18091, TRANSLATE_SYS, 'עלה עשרה מטרים', …)` | `translate -> Ascend ten meters` |
| 5 | parse_highlight English-safety | `parse_highlight('highlight the red backpack' \| 'clear' \| 'what do you see')` | `'red backpack'` / `''` / `None` |

Gate 1 detail: 26 prior tests plus 6 new wiring tests. The 6 new tests all pass.

Gate 4 detail: the DictaLM server bound :18091, returned a correct English line for "עלה עשרה מטרים"
("go up ten meters"), and was then stopped. The port is released. No `llama-server` process remains.

Gate 5 detail (manager-flagged, verify-don't-assume): with this wiring, perception text now reaches
`TextHandler.perceive` as the Recognizer's ENGLISH output, not the raw ASR text. The perception engine's
regexes (`CLEAR_RE`, `FIND_RE`, `LEAD_VERB_RE`, `FILLER_RE`) are all English-keyed. English input is handled
correctly and the highlight/clear/ask UX is preserved. There is no Hebrew-keyed path, so the ruled shape
introduces no bug. Escalation to 0c was not needed.

## Analysis

1. Perception behaviour is preserved. A see-question produces the same ask/highlight UX as today. The only
   change is the entry point: perception now runs through `TextHandler.perceive`, which the Pipeline calls
   with translated English.
2. The Hebrew command path is additive. A Hebrew movement command now becomes a planned mission on the wire.
   Before this change that text went to perception and never flew.
3. Emergency, override, resume and basic verbs are unchanged. The router still handles them on the wire
   before the Pipeline is reached. The Pipeline's own emergency branch is a backup net only.
4. The no-drone path is unchanged. Without `MVD_DRONE`, the Pipeline is never built and `perceive` runs
   directly. No DictaLM, no recognizer.
5. Frame handling is unchanged. The perception threads still snapshot the frame under `S.lock`. No VLM work
   moved onto the ASR callback thread.
6. Reject is a runtime guard outcome, not a bench-case category. No case in `cases_commands.py` is labeled
   "reject". Reject fires only when DictaLM drops or invents a number that the guard cannot reconcile.

## Changed files

- `projects/integration_harden/scene_omdet.py`
- `projects/integration_harden/run_mvd.sh`
- `projects/integration_harden/README.md`
- `projects/integration_harden/test/test_scene_wiring.py` (new)

## Suggested commit (house style; the human runs all git)

The tree holds only these four go-live files plus this report and the handoff doc. The structure pass is
already committed (9dca582). Do not bundle anything else.

```
git add projects/integration_harden/scene_omdet.py \
        projects/integration_harden/run_mvd.sh \
        projects/integration_harden/README.md \
        projects/integration_harden/test/test_scene_wiring.py \
        docs/active/2026-09-03-golive-wiring-report.md \
        docs/active/2026-09-03-golive-wiring-handoff.md

git commit -m "feat(golive): wire the Recognizer into the live app | scene_omdet builds Pipeline(wire, vlm_query=perceive, say) as Router.on_complex, so COMPLEX Hebrew becomes missions on the wire, see-questions route back to perception, rejects are spoken | run_mvd gains a dicta CPU pane (:18091, log to mvd_dicta.log) | README data-flow + panes updated | perception UX preserved (English-keyed, gate 5), Hebrew command path additive | gates green: pytest 32, import, live_mock_smoke, real DictaLM translate 'Ascend ten meters', parse_highlight English-safety

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Live-test handoff (for the desk tester who boots the full app on the mock)

### (1) What changed in the live app
- `scene_omdet.py`: COMPLEX text now runs the Recognizer (Pipeline as `Router.on_complex`) instead of
  going straight to perception.
- `scene_omdet.py`: the perception dispatch is now `TextHandler.perceive`, reused as the Pipeline's `vlm_query`.
- `run_mvd.sh`: a new `dicta` tmux pane runs DictaLM on CPU :18091, output to `${TMPDIR:-/tmp}/mvd_dicta.log`.
- `README.md`: the data-flow and panes sections are updated.

### (2) Live verification points the wiring adds
Boot the app on the mock:
```bash
# start the mock control server in one shell (mock, loopback, safe):
python3 /root/groundstation/tools/dji_mock/mock_apiserver.py 127.0.0.1 8079
# then boot the full app (webcam video + mock control):
bash /root/groundstation/projects/integration_harden/run_mvd.sh webcam mock
```
- Dicta pane healthy: the tmux window `dicta` is present. `ss -tln | grep 127.0.0.1:18091` shows LISTEN.
  Tail `${TMPDIR:-/tmp}/mvd_dicta.log` for the llama-server ready line and no errors.
- Hebrew command -> planned mission on the MOCK wire: after a Hebrew movement command the mock ApiServer
  receives `POST /c/fly` with a mission. The chat pane does NOT show a perception answer.
- Perception phrase behaves exactly as before: a Hebrew see-question -> a VLM answer in the chat pane.
- Reject spoken or printed: an unresolved-number Hebrew utterance -> the "לא הבנתי, שמעתי: ..." line is
  spoken (or printed) and appears in chat.

### (3) Suggested Hebrew test sentences, one per outcome kind
- mission (bypass, no model): `עלה עשרה מטרים`  (go up 10 meters)
- command (translate + planner): `טוס קדימה חמישה מטרים ואז הסתובב תשעים מעלות`  (a chain -> a planned mission)
- perception (VLM): `מה אתה רואה עכשיו?`  (what do you see now?)
- reject: no bench case is labeled "reject". Reject is a runtime guard outcome — it fires only when DictaLM
  drops or invents a number. The repo's verified reject example is
  `תעלה לי בעדינות עשרים מעלות ועוד שלושים`. Live, it rejects only if the translate mismatches a number;
  on a clean translate the same sentence plans normally. Watch the chat for the "לא הבנתי, שמעתי:" line on
  any number-heavy command.
- emergency (router tier-4, not the Pipeline): `עצור`  -> `wire.halt()` = `POST /c/fly [{delay:0}]`, NOT `/c/stop`.

### (4) Gotchas a live run can trip on
- Startup ORDER: DictaLM (:18091) and Qwen VLM (:18090) must be UP before the first COMPLEX Hebrew
  utterance, or the Pipeline's translate/plan call errors. `run_mvd` starts both panes. Give them a few
  seconds. Watch the logs.
- PORTS: `run_mvd` mock control = 127.0.0.1:8079 (`MVD_WIRE_PORT`). Qwen = 18090. Dicta = 18091. Do not
  confuse 8079 with `live_mock_smoke`'s 8080.
- ENV: `MVD_DRONE=1` must be set (`run_mvd` sets it), or the Pipeline is never built and Hebrew commands do
  not fly. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` (run_mvd sets both) so OmDet loads from the
  /root/models cache.
- First DictaLM call is slower (CPU warmup). This is not an error. In this gate run the first translate
  returned a correct line well within the timeout.
