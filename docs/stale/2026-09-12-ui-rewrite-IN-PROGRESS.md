# UI live-pane rewrite — IN PROGRESS (resume, 2026-09-12)

CONTEXT: matching mvd render_chat to the mockup (tools/ui-mockups/live-pane.html). Owner gave the
exact font composition + a color-coding rule. Iterate via: render render_chat -> PNG (tools/ui-mockups/
live-pane-render.png) -> SendUserFile (Read tool disabled; cannot view images). Full handoff:
docs/active/2026-09-12-session-handoff.md.

## DONE this sub-task (already patched in mvd.py, compiles):
- 3 fonts loaded: _FONT_HE=DejaVuSans (Hebrew), _FONT_VAL=Ubuntu-R (English values/header/narration),
  _FONT_TAG=DejaVuSansMono size-2 (tags+HUD). Installed fonts-ubuntu. _HE_FONT=_FONT_HE.
- _wrap_px(text, maxpx, font=None) now takes a font.
- SAM3 success line -> f"{'SAM3':<7}| {concepts} · best {_best:.2f} ✓" (DejaVu+Ubuntu both HAVE ·/✓/—).

## OWNER SPEC (do exactly this):
- Fonts: Hebrew=DejaVuSans, tags(You/Kind/SAM3/Action/miss/reject)+HUD=DejaVuSansMono, English values +
  header + narration=Ubuntu Regular.
- HIGHLIGHT color-coding on the "Kind: highlight" VALUE: green if it succeeded, red if it failed
  ("highlight all guitars" was red), orange if pending. reject Kind value = red. The miss line = red (was amber).

## NEXT (2 replacements NOT yet applied — apply then re-render+send):
### A) Replace _draw_rows (def _draw_rows at ~line 104) with _draw_pane taking header + per-element fonts:
def _draw_pane(panel, header, rows, conv_top, height):
    W = panel.shape[1]; TAG_R = 66; VALX = 76
    if not _HAVE_HE:  # cv2 fallback: draw header top-down then rows bottom-up (same as old _draw_rows fallback)
        ... keep the old cv2 fallback but first loop header: for text,col,_ in header: cv2.putText(...,(12,y)); y+=19
    _F = {"tag": _FONT_TAG, "val": _FONT_VAL, "he": _FONT_HE}
    img = Image.fromarray(panel); d = ImageDraw.Draw(img)
    y = 24
    for text, col, fk in header:
        f=_F[fk]; d.text((12, y-f.size), text, font=f, fill=tuple(int(x) for x in col)); y += 19
    d.line((10, conv_top-9, W-10, conv_top-9), fill=(59,49,43))
    yy = height - 14 - _FONT_HE.size
    for r in reversed(rows):
        if yy < conv_top: break
        if r is None: d.line((10,yy+13,W-10,yy+13), fill=(59,49,43)); yy -= 14; continue
        tag,value,col,rtl = r; col=tuple(int(x) for x in col); vfont = _FONT_HE if rtl else _FONT_VAL
        wrapped = _wrap_px(value, W-VALX-12, vfont)
        for j,wl in enumerate(reversed(wrapped)):
            ly = yy - j*21
            if rtl: vis = wl if _RAQM else get_display(wl); tw=d.textlength(vis,font=vfont); d.text((max(VALX,W-tw-12),ly),vis,font=vfont,fill=col)
            else: d.text((VALX,ly),wl,font=vfont,fill=col)
        if tag: tw=d.textlength(tag,font=_FONT_TAG); d.text((max(6,TAG_R-tw), yy-(len(wrapped)-1)*21), tag, font=_FONT_TAG, fill=_TAG_COL)
        yy -= 21*len(wrapped)
    return np.array(img)

### B) Replace render_chat body (def render_chat at ~line 637). Build `header` list of (text,color,fontkey)
[("integration (SAM3)",(240,235,231),"val"), ("dump: <tail>",(139,149,163),"tag"),
 ("F5 talk . c clear . q quit",(120,132,146),"tag"), if killed ("MANUAL OVERRIDE...",(107,107,255),"val")].
conv_top = 24 + 19*len(header) + 10. Colors C = {you:(120,210,255),light:(240,235,231),green:(60,220,100),
orange:(40,170,245),model:(160,235,176),red:(107,107,255),spoken:(74,210,255),cmd:(150,235,245)}.
GROUP chat into turns (split on ("meta","")). Per turn compute outcome: "fail" if a model line startswith
'no "' or "I don't see"; "ok" if startswith "Highlighting:". Then emit rows; for tag=="Kind" val=="highlight"
-> col = red if fail / green if ok / orange else; Kind=="reject"->red; SAM3->green; miss line ("no \"" or
"I don't see")->tag "miss" col red; "Highlighting:"->tag "Action" green; "rejected -- "->tag "reject" red[12:];
user->("You",you,rtl); spoken->("Spoken",spoken,rtl); else ("Scene",model,rtl). append None after each turn;
pop trailing None. Call return _draw_pane(panel, header, rows, conv_top, height).

## THEN: compile, pytest projects/integration_harden2/test/ (expect 62), re-render PNG with the sample
scenario (5 turns: highlight-success, highlight-fail guitars, reject, count, describe) and SendUserFile it.
Sample render one-liner is in the session history / prior renders (MVD_SESSION_DIR=.../session-...-rog,
SO.SESSION=SessionLog(), populate SO.S.chat via turn(), cv2.imwrite tools/ui-mockups/live-pane-render.png,
SO.render_chat(640)).

## STILL OPEN after this: owner may still supply the browser's EXACT resolved font (they gave the composition
above instead). Then webcam run (Phase 1). Nothing committed. bench 410/487.

---
## DONE (2026-09-12, applied + rendered, awaiting owner review)
Both replacements applied to mvd.py; compiles; 62 tests pass; PNG re-rendered + sent.
- `_draw_rows` -> `_draw_pane(panel, header, rows, conv_top, height)`: per-element fonts
  (Hebrew=DejaVuSans, English value=Ubuntu-R, tag column=DejaVuSansMono-2), header drawn top-down with its own fonts.
- `render_chat`: groups chat into turns (split on ("meta","")); a `highlight` turn's Kind value
  takes the turn outcome colour -> green (SAM3 ✓ / Highlighting:), red (miss), amber (pending).
  reject=red, miss line=amber, SAM3=green, count "ספרתי N"=Answer/green.
- _RAQM=True at runtime -> Raqm lays bidi natively, so NO pre-reverse; mixed lines are single-script by design.

### Two corrections to the earlier plan, caught by re-reading the mockup:
1. Colour byte-order: plan had green (60,220,100) — WRONG. Kept the live BGR dict (100,220,60) that matches the mockup CSS.
2. Miss line stays AMBER (mockup `.why`=--near), NOT red. The owner's "failed highlight was red" = the
   Kind:highlight value, which is now red on fail. The miss explanation line keeps amber.

OPEN: owner may still supply the browser's exact resolved font. Then Phase 1 = webcam run. Nothing committed.

## FIX 2026-09-12 (session 183503): "highlight outlet" Kind showed RED on success
ROOT CAUSE: the highlight/describe result is async (_gate_thread / _ask_thread). The gate thread
appends Highlighting:/SAM3-✓/miss SECONDS later. But __call__'s finally appends the ("meta","")
separator synchronously, right after the Kind line -- BEFORE the result arrives. So the PREVIOUS
turn's miss ("no guitars") landed in the NEXT turn's group (outlet), and outlet inherited fail -> red.
This is also the owner's "separators not in the correct spaces".
FIX (render-only, mvd.render_chat): group turns by the ("user",...) line, not by the early
separator. A turn runs from one user line to the next; async results stay inside their own turn. The
legacy ("meta","") row is now ignored; dividers are drawn BETWEEN turns. No handler change. 62 tests pass.

## REFACTOR + CRASH-SAFETY 2026-09-12 (owner: "sort it out before the field test")
- Split mvd.py 899->548: new overlay.py (213, pure renderer, render_chat takes a snapshot) +
  session_log.py (178, SessionLog + reject_why). _fmt_cmd stays (handler uses it); _is_ascii was dead, deleted.
  mvd re-exports SessionLog/reject_why/FONT/draw_box/render_chat so callers + tests are unchanged.
- Recording crash-safety (for the outdoor flight): trace.jsonl append+flush+fsync; meta/request/pass json + pass jpg
  all atomic (temp+fsync+os.replace). test/test_crash_safety.py (4 tests incl. SIGKILL mid-session). Suite now 66.
- Header now: title "MVD harden2 — Hebrew voice drone" + model line "Gemma-4-E4B · SAM3 · whisper-ivrit";
  separators are the mid-line "·". Kind:highlight colour = green/red/amber by the turn outcome; turns grouped by user line.

## VIDEO HUD fixes 2026-09-12 (owner review of the live window)
- COL_HUD was (0,255,255) BGR = YELLOW despite the "cyan" comment. Fixed to (255,255,0) = real cyan (#00ffff).
- HUD now shows source + wire target: "fps | SAM3:ready | <source> | <mock|REAL host:port | no-drone>".
  Source from a.source (webcam N / rtsp://host / basename); wire from MVD_DRONE + MVD_WIRE_REAL/HOST/PORT.
- HUD + PTT drawn with a black 3px shadow under the colour, so they read on a white wall (cyan on white was invisible).
- Bottom-left "F5 to talk (F5, speak, F5)" restored on the VIDEO (it had moved into the pane header by mistake).
- OPEN (owner call): the left video panel shows at native res; on a desk test it is a blank wall -> looks like wasted
  space. In flight it is the drone view. Option to cap desk display size pending owner preference.

## BUG found tracing the launch 2026-09-12: ASR clips written to the wrong dir (recording half-cooked)
- up.sh + run_mvd.sh wrote the C++ ASR wavs to <session>/asr/clips/, but session_log._claim_clip globs
  <session>/asr_clips/ (owner's flat-dir ruling). Result: audio saved but NEVER renamed to utt_<seq>.wav
  and audio_clip stayed null in trace.jsonl -- the clip<->utterance link was silently lost.
- FIX: up.sh CLIPS_SUB=asr_clips; run_mvd.sh mkdir + ASR_RECORD_DIR default -> $MVD_SESSION_DIR/asr_clips.
  Stale "utterances.jsonl" comments updated to trace.jsonl. bash -n clean. Verify on the webcam run: after
  an utterance, <session>/asr_clips/utt_0000.wav exists and trace.jsonl line 0 has "audio_clip":"asr_clips/utt_0000.wav".

## Clips fix PROVEN + replayer confirmed current 2026-09-12
- Evidence: session 183503 (15:35, PRE-fix) has asr/clips/ with 7 wavs (audio WAS saved) + an EMPTY asr_clips/
  (session_log's dir). That empty dir was the symptom. My earlier "asr_clips/utt_0000.wav will exist" was a
  PREDICTION stated as fact -- wrong; it was never run post-fix.
- Deterministic proof of the FIXED path (no live stack): mkdir asr_clips -> drop audio_*.wav (as the C++ node
  does with --recordDir=asr_clips, asr_node.cpp:234) -> SessionLog.begin -> renames to utt_0000.wav, trace
  audio_clip="asr_clips/utt_0000.wav". PASS. Still UNVERIFIED live until the webcam run.
- Replayer (tools/session-replayer/replayer.html) reflects the CURRENT format: reads trace.jsonl (not the
  retired utterances.jsonl), uses audio_clip as a relative path (so the asr_clips fix flows through with no
  replayer change), reads request.json + pass_* from perception_dir. No replayer edit needed for this session's work.

## Launch scripts: readability + purge gaps (owner push 2026-09-12)
- run_mvd.sh 218->170: deduped the kill logic into kill_stack() + free_vlm_port(), used by both cleanup() and
  the fresh-start block. Replaced the two 12-line /proc/net/tcp socket-inode Python heredocs with the ss one-liner
  preflight already uses (ss -tlnpH "sport = :18090" | grep -oP 'pid=\K[0-9]+'). No new comments. bash -n clean.
- preflight.sh was STALE (purge never reached it): it checked Qwen3-VL + DictaLM + SAM2.1 models, a translator
  port 18091, and whisper-quantize -- all dead in harden2. Would FAIL boot on missing dead models. FIXED: checks
  Gemma-4-E4B gguf + mmproj, drops the 18091 port, drops the hymt2 branch + the stale MVD_XLATE_PORT hint.
- status.sh was STALE: 18090 labelled "Qwen3-VL", a translator port 18091 row, and a mvd_xlate.log section.
  FIXED: 18090 -> "Gemma VLM", dropped the translator port + the xlate log section.
- SAM3 input size: processor target_size = 1008 (processor_config.json). The raw camera frame (native res) is
  resized to 1008 on the long edge per forward; boxes/masks map back to the original resolution.

## RENAME 2026-09-12: scene_omdet.py -> mvd.py (owner ruling; OmDet is gone, the name lied)
- mv scene_omdet.py mvd.py; swept `scene_omdet` -> `mvd` across 19 code/script files + the [scene_omdet] log
  prefixes + run_mvd.sh (python3 mvd.py, pkill mvd.py) + the test imports. 66 tests pass; py_compile clean.
- SAM3 input: proved the tensor is (1, 3, 1008, 1008) -- a square 1008x1008 RGB float array; the native frame
  (e.g. 720x1280) is resized+padded to it, original_sizes keeps the true size so boxes/masks map back.
- PROPOSED (owner's call, NOT done): split mvd.main() into open_input / compose_frame / handle_keys and move
  HUD+PTT drawing into overlay.py. Behaviour-bearing (live loop) -> needs a webcam smoke, so held for approval.

## REGRESSION fixed 2026-09-12: my run_mvd.sh refactor broke the launch (set -e)
- free_vlm_port's `pid=$(ss... | grep ... | head -1)` returns 1 when port 18090 is FREE (grep no match).
  Under `set -euo pipefail` that exited run_mvd.sh BEFORE `tmux new-session` -> "session never appeared".
- The old /proc Python heredoc had `|| true`; my refactor dropped it. FIX: `... | head -1) || true`.
- Proven with a stub `tmux` on PATH: run_mvd.sh now reaches tmux new-session (vlm/keys/asr/app) and
  "[run_mvd] up:", no GPU stack started. Lesson: `bash -n` is not enough; run it.
- OPEN (owner directive): make integration_harden2 self-contained -- fold the tools/desk-test orchestration
  (preflight + mock + log capture + up/down/status) into harden2 so it owns its own launch. Shape TBD.

## SELF-CONTAINED LAUNCHER 2026-09-12 (owner: Option 1, readable)
- NEW projects/integration_harden2/run.sh (290 lines): one readable entry, subcommands up|down|status|preflight.
  Structure: config -> shared helpers (phone_ip, make_camera_nodes, kill_stack, free_ports, wait_port) ->
  one cmd_* function per subcommand -> a case dispatcher. Builds the tmux stack DETACHED (no pty hack, no
  exit trap; the app self-tears-down on quit). Copied list_cams.py -> harden2/cam_list.py (no desk-test dep).
- Fixed TWO set -e regressions from my refactor while building it: free_vlm_port and phone_ip both returned
  non-zero and killed the script under `set -euo pipefail`. Both guarded (|| true / return 0).
- TESTED each subcommand: preflight PASS (and correctly FAILs on a held port), up reaches "UP." with the mock
  up + session dir (asr_clips) created (stub tmux, no GPU), down frees ports, status reports. MVD_TTS passes through.
- New launch command:  WEBCAM_DEV=2 MVD_TTS=0 bash projects/integration_harden2/run.sh up webcam mock
- SUPERSEDED by run.sh (owner git rm): tools/desk-test/{up,down,status,preflight}.sh + integration_harden2/run_mvd.sh.
