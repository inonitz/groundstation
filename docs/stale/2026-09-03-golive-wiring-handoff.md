# Go-live wiring — full handoff to the go-live IMPLEMENTER (written 2026-09-03 by groundstation-24)

Read top to bottom; this is COMPLETE and self-contained. The prior agent (me) did the ground-truth
reading and the design and made ZERO code edits. Nothing is half-applied. You implement from a clean
tree, run the gates, write the report (including the "Live-test handoff" section in sec 6b), and
report to the manager groundstation-0c.

## 0. Provenance and coordination
- ROUTING (manager 0c): this is an IMPLEMENTER brief -- it EDITS scene_omdet.py + run_mvd.sh + README, then
  writes the report. Do NOT send it to f0: f0 is the live-TESTER and the owner keeps its context clean until
  dev is done. The go-live IMPLEMENTER is a SEPARATE fresh session the owner will spawn; the manager (0c)
  hands this file to it. sec 6b below is the live-test material the implementer copies into the report for f0.
- Prior agent: groundstation-24 (ASR bench, then structure-closer). Handed off because its context is bloated.
- MANAGER: groundstation-0c (history 9b -> d9 -> 0c; first two dead). Report completion to 0c.
- CLAUDE.md binds you: rtk wrappers for reads/searches; NO git writes (suggest commit blocks, human runs them);
  NO real-drone commands, mock 127.0.0.1 only; do NOT edit recognizer/ (sync rule); do NOT run bench.py
  (GPU coordinated by 0c).

## 1. Task (manager brief, verbatim)
Today the live app never runs the Recognizer: scene_omdet.py sends COMPLEX text straight to the perception
handler, and run_mvd.sh never starts the DictaLM server. The Recognizer is measured and E2E-verified vs the
mock; only the production assembly is missing. RULED shape (do NOT redesign): scene_omdet builds
  pipe = Pipeline(wire, vlm_query=<the existing ask path with the live frame>, say=<Voice speaker, print fallback>)
and passes pipe.handle as the Router's on_complex. Perception-routed text behaves exactly as today
(ask/highlight UX); Hebrew commands become planned missions on the wire; rejects spoken/printed per the
reject ruling. run_mvd.sh gains a dicta pane running recognizer/run_dicta_server.sh with stderr to a LOG
FILE, never /dev/null. README data-flow + run sections updated. Report:
docs/active/2026-09-03-golive-wiring-report.md. When done: message groundstation-0c, 3 lines.
Read first: docs/active/2026-09-02-manager-handoff.md, docs/active/2026-09-02-state-and-next.md,
projects/integration_harden/recognizer/README.md, projects/integration_harden/README.md, scene_omdet.py TextHandler.

## 2. Current state — NOTHING done for this task
- Zero edits to scene_omdet.py, run_mvd.sh, README for go-live. Read + design only.
- Already in the working tree (uncommitted, NOT your task): the structure pass across integration_harden +
  docs/active/2026-09-03-structure-pass-report.md. config_pkg/ was deleted there; config.py is the single
  config. That work is closed/green; leave it for the human to commit. Do not bundle it with yours.

## 3. Ground truth I verified (do NOT re-derive)
### 3a. control/router.py ALREADY supports on_complex
Router.__init__(self, wire, on_complex=None, ...) -> self.on_complex = on_complex or (lambda text: None).
handle(text): EMERGENCY/OVERRIDE/RESUME/BASIC act on the wire and return Result; final branch:
    self.on_complex(cmd.text); return Result(cmd.tier, "complex->perception", True)
So COMPLEX calls on_complex(text) and IGNORES its return. Tier from control/commands.py: `from control.commands import Tier`.
### 3b. recognizer/pipeline.py — Pipeline
Pipeline(wire, vlm_query=None, say=print, dicta_port=18091, qwen_port=18090, plan_fn=None, trace_dir=None).
Default ports already correct. pipe.handle(text) runs recognize(text, self._translate) then routes:
  emergency->wire.halt() (backup; router tier-4 fires first) | mission->wire.fly_mission(payload) |
  reject->say(REJECT_PREFIX+payload)  REJECT_PREFIX="לא הבנתי, שמעתי: " | perception->vlm_query(payload) (payload=ENGLISH) |
  command->plan_fn(payload)->wire.fly_mission(mission) if non-empty (empty=refusal, no flight).
Records every utterance to trace.Trace (traces/ gitignored). STARTS NO servers; assumes DictaLM 18091 + Qwen 18090 up.
### 3c. scene_omdet.py current wiring (what you change)
- on_text = TextHandler(router, voice) is the ASR/phone callback.
- __call__(text): print "you:", append ("user",text) to S.chat, then `if self._handle_drone(text): return`
  else perception dispatch: phrase=parse_highlight(text); ""->_handle_clear(); not None->_handle_highlight(phrase);
  else->_handle_ask(text).
- _handle_drone(text): False if router is None; else res=self.router.handle(text) (try/except -> chat
  "[drone unreachable: e]", return True); if res.tier is Tier.COMPLEX return False (today: falls to perception);
  else append ("model", f"[drone] {res.action}"), return True.
- _handle_highlight/_handle_ask snapshot S.frame under S.lock and run VLM work on daemon threads
  (_gate_thread/_ask_thread). _ask_thread calls vlm.ask, appends answer+spoken to S.chat, voice.say(spoken) if voice.
  THIS is "the existing ask path with the live frame" -- it reads the frame from module-level S, not a passed arg.
- Router built ONLY under MVD_DRONE: router = Router(DjiWire.from_env()) (on_complex defaults to no-op today).
  voice built under MVD_TTS!="0": from audio.tts_io import Voice; voice=Voice(). S=Shared() holds frame/chat; worker() fills detections.
### 3d. recognizer/run_dicta_server.sh
DictaLM-3-1.7B q4_k_m, CPU (-ngl 0, 16 threads), host 127.0.0.1 port 18091, temp 0, zero VRAM. Execs
llama-server from build/release/shared/dji/bin with LD_LIBRARY_PATH. No GPU needed.
### 3e. run_mvd.sh pane structure
tmux windows: vlm (run_llama_server.sh, Qwen 18090), optional rtmp, keys, asr, optional gst+dog (dji), then app.
MVD_DRONE=1 always exported in the app-launch script -> recognizer path always active in run_mvd. App pane:
`python3 scene_omdet.py 2>&1 | tee ${TMPDIR:-/tmp}/mvd_app.log` -- mirror the tee-to-log for dicta. Mock control
in run_mvd = 127.0.0.1:8079 (MVD_WIRE_PORT=8079), NOT 8080 -- wire from DjiWire.from_env() reading MVD_WIRE_HOST/PORT/REAL.
(live_mock_smoke.py separately spawns its own mock on 8080 with DjiWire() defaults; unrelated to run_mvd's port.)

## 4. Exact implementation plan (ruled shape, no redesign)
### Edit A — scene_omdet.py main(): voice/router/on_text block. Break the circular dep (handler<-router<-pipe<-handler.perceive) by ordering:
1. Build voice FIRST (move the voice block above the router block).
2. on_text = TextHandler(None, voice)   # router assigned later
3. if os.environ.get("MVD_DRONE"):
     wire = DjiWire.from_env()
     from recognizer import Pipeline
     def _say(msg):
         with S.lock: S.chat.append(("model", msg))
         (voice.say(msg) if voice is not None else print(msg, flush=True))
     pipe = Pipeline(wire, vlm_query=on_text.perceive, say=_say)
     router = Router(wire, on_complex=pipe.handle)
     on_text.router = router
     print the existing "MVD drone router ON -> host (real|mock)" line
   wrap in try/except as today (print "drone router DISABLED: e"); on failure leave on_text.router = None.
### Edit B — scene_omdet.py TextHandler:
1. Add perceive(self, text) = today's perception dispatch verbatim:
     phrase = parse_highlight(text)
     if phrase == "": self._handle_clear()
     elif phrase is not None: self._handle_highlight(phrase)
     else: self._handle_ask(text)
2. __call__: keep "you:" print + ("user",text) append; then `if self._handle_drone(text): return` ; `self.perceive(text)`.
3. _handle_drone: change ONLY the COMPLEX case -- with a router present, COMPLEX is now handled by
   on_complex=pipe.handle, so return True (consumed) instead of False. After res=self.router.handle(text):
   if res.tier is not Tier.COMPLEX append ("model", f"[drone] {res.action}"); ALWAYS return True when router present.
   Keep the try/except unreachable branch. router is None -> return False (falls to perceive; no-drone behavior).
Net: no-drone -> perceive directly (today). drone -> router.handle; basic/emergency/override -> chat "[drone] action";
COMPLEX -> recognizer -> perception via perceive (today's UX) | Hebrew command -> planned mission on wire | reject -> _say.
### Edit C — run_mvd.sh: add the dicta pane right AFTER the `vlm` new-session line:
    tmux new-window -t "$SESSION" -n dicta "bash -c '$SCENE/recognizer/run_dicta_server.sh 2>&1 | tee ${TMPDIR:-/tmp}/mvd_dicta.log; echo [dicta exited]; exec bash'"
($SCENE = the integration_harden dir, already defined.) CPU-only; no GPU contention.
### Edit D — README.md: data-flow shows COMPLEX -> Recognizer (pipeline.py) -> {mission/perception/reject}; Run/panes lists the dicta pane. Keep it current-state.

## 5. Gates (all mock/CPU; every one green before reporting)
1. cd /root/groundstation/projects/integration_harden && python3 -m pytest test/ -q  -> >= 26 passed. If the new
   on_text/perceive or Router(on_complex=pipe.handle) path is uncovered, ADD a scene_omdet-level faked-model
   wiring test (fake wire recording fly_mission/halt; Pipeline with injected fake plan_fn + fake translate; assert
   perception->vlm_query, Hebrew command->wire.fly_mission, reject->say). Do NOT modify test/test_recognizer.py.
2. python3 -c "import scene_omdet"  (from integration_harden) -> OK.
3. cd /root/groundstation/projects && python3 integration_harden/test/live_mock_smoke.py -> "LIVE MOCK SMOKE PASSED"
   (it self-spawns the mock on 127.0.0.1:8080; safe).
4. ONE REAL translate call proving the dicta pane wiring (CPU, no GPU, no drone):
     bash /root/groundstation/projects/integration_harden/recognizer/run_dicta_server.sh 2> /tmp/dicta.log &
     for i in $(seq 1 30); do ss -tln | grep -q 127.0.0.1:18091 && break; sleep 1; done
     cd /root/groundstation/projects/integration_harden && python3 -c "
from recognizer.llama import chat
from recognizer.prompts import TRANSLATE_SYS, LINE_GRAMMAR, TRANSLATE_SHOTS
out,_ = chat(18091, TRANSLATE_SYS, 'עלה עשרה מטרים', max_tokens=200, grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)
print('translate ->', out.strip())"
     pkill -f 'port 18091'    # stop the server after
   Expect a real English line (e.g. "go up 10 meters").

5. parse_highlight English-safety (VERIFY-DON'T-ASSUME, manager-flagged). With this wiring, perception text
   reaches TextHandler.perceive as the recognizer's ENGLISH output (Pipeline calls vlm_query(payload), payload=
   translated English), whereas TODAY perceive ran on the raw ASR text. So parse_highlight + the highlight/ask
   split now operate on English. This sits on the perception UX the owner said must stay unchanged.
   VERIFIED 2026-09-03 by groundstation-24: perception/engine.py CLEAR_RE/FIND_RE/LEAD_VERB_RE/FILLER_RE are ALL
   English-keyed (highlight/locate/track/mark/find/show me/point at / clear/reset/deselect/never mind / please/
   thanks), no Hebrew -> English input is handled correctly and the UX is preserved. (Also consistent today: the
   demo ASR is English parakeet, so perceive already gets English.) RE-CONFIRM after wiring:
     'highlight the red backpack' -> 'red backpack' ; 'clear' -> '' ; 'what do you see' -> None (ask branch).
   If parse_highlight is ever Hebrew-keyed, the ruled shape introduces a REAL bug -- stop and escalate to 0c.

## 6. Report + completion
Write docs/active/2026-09-03-golive-wiring-report.md (Objective/Setup/Changes/Verification/Analysis/Changed files),
list every gate + outcome, state it is behaviour-preserving for perception and additive for the Hebrew command
path, and INCLUDE the "Live-test handoff" section below (sec 6b). Suggest a house-style commit block; human runs
all git. Then message groundstation-0c: 3 lines (what changed, gate results, report path).

## 6b. REQUIRED "Live-test handoff" section in the report (manager-specified, copy-paste runnable, absolute paths)
Write this section verbatim-in-spirit for the desk tester who boots the full app on the mock:

(1) What changed in the live app (one bullet per change):
- scene_omdet.py: COMPLEX text now runs the Recognizer (Pipeline as Router.on_complex) instead of going
  straight to perception.
- scene_omdet.py: the perception dispatch is now TextHandler.perceive, reused as the Pipeline's vlm_query.
- run_mvd.sh: new `dicta` tmux pane = DictaLM on CPU :18091, output to ${TMPDIR:-/tmp}/mvd_dicta.log.
- README.md: data-flow + run sections updated.

(2) Live verification points the wiring adds (run the app: `bash /root/groundstation/projects/integration_harden/run_mvd.sh webcam mock`, mock on 127.0.0.1:8079 started separately):
- Dicta pane healthy: tmux window `dicta` present; `ss -tln | grep 127.0.0.1:18091` shows LISTEN; tail
  ${TMPDIR:-/tmp}/mvd_dicta.log for the llama-server ready line and no errors.
- Hebrew command -> planned mission on the MOCK wire: after a Hebrew movement command, the mock ApiServer
  receives POST /c/fly with a mission; the chat pane does NOT show a perception answer.
- Perception phrase behaves exactly as before: a Hebrew see-question -> VLM answer in the chat pane, same as today.
- Reject spoken/printed: an unresolved-number Hebrew -> the "לא הבנתי, שמעתי: ..." line is spoken (or printed)
  and appears in chat.

(3) Suggested Hebrew test sentences, one per outcome kind:
- mission (bypass, no model): "עלה עשרה מטרים"  (go up 10 meters)
- command (translate + planner): "טוס קדימה חמישה מטרים ואז הסתובב תשעים מעלות"  (chain -> planned mission)
- perception (VLM): "מה אתה רואה עכשיו?"  (what do you see now?)
- reject: pull a REJECT-labeled case from tools/bench/hebrew-command-bench/cases_commands.py -- do NOT fabricate one;
  the verified reject triggers (unresolved/hallucinated numbers) live there.
- emergency (router tier-4, not the Pipeline): "עצור"  -> wire.halt() = POST /c/fly [{delay:0}], NOT /c/stop.

(4) Gotchas a live run can trip on:
- Startup ORDER: DictaLM (:18091) and Qwen VLM (:18090) must be UP before the first COMPLEX Hebrew utterance,
  or the Pipeline's translate/plan call errors. run_mvd starts both panes; give them a few seconds; watch the logs.
- PORTS: run_mvd mock control = 127.0.0.1:8079 (MVD_WIRE_PORT), Qwen = 18090, dicta = 18091. Do not confuse
  8079 with live_mock_smoke's 8080.
- ENV: MVD_DRONE=1 must be set (run_mvd sets it) or the Pipeline is never built and Hebrew commands won't fly.
  HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 (run_mvd sets) so OmDet loads from the /root/models cache.
- First DictaLM call is slower (CPU warmup). Not an error.

## 7. Traps to avoid
- Do NOT edit recognizer/ (sync rule); wiring is scene_omdet.py + run_mvd.sh only.
- Do NOT run bench.py (GPU, coordinated by 0c).
- Do NOT send any command to a real drone. All above is mock/CPU. run_mvd `real` mode is HUMAN-only.
- Pipeline is built ONLY inside the MVD_DRONE branch; without MVD_DRONE, TextHandler.perceive runs directly
  (no recognizer, no dicta) -- keep that path working.
- Frame snapshots stay under S.lock; do not move VLM work onto the ASR callback thread.
