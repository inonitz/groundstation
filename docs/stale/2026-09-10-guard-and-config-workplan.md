# WORKPLAN (living) — negation guard + config merge, 2026-09-10

Update the checkboxes and the status log as I go. Two harden2 changes, in order.

## Guardrails (do not lose these)
- The human owns ALL git; I prepare, they run. The human runs every boot.
- Temp 0; one model on the GPU; state a duration estimate before every GPU run; full tables.
- Recognizer change rule (recognizer-bench skill): >=2 measured failures, positives, adversarial
  negatives (lookalikes it must NOT touch), clean self-test. ZERO FALSE FIRES is the ship gate.
- After any recognizer change: RE-RUN the full bench, compare per-set counts. Temp 0 => unchanged
  cases reproduce exactly; any diff is my change.
- harden2 bench = tools/bench/hebrew-command-bench/unified_bench.py (NOT the stale harden bench.py).
  Recognizer = projects/integration_harden2/recognizer/ (recognizer.py, pipeline.py, prompts.py).
- Config merge must NOT change harden2 runtime behaviour; the golden-master proves it per scenario.
- The recognizer-bench skill is STALE (points at integration_harden + DictaLM). Its Hebrew-language
  gotchas still apply; its paths/DictaLM facts do not. Repoint it during cleanup.

## Workstream A — negation guard (behaviour CHANGE, intended; must be in the final system)
- [ ] A1 BASELINE: run unified_bench (unmodified). Record per-set counts + the negation cases'
      current verdicts. Log scratchpad/baseline.log; result results/<date>-negation-baseline.json.
- [ ] A2 DESIGN the rule. FIRE only on a PURE action-negation with NO other order. Do NOT fire when a
      real command is present.
      Positives (MUST refuse): "בלי להסתובב בבקשה" (r_neg4, flew two spins live); "אל תנחת";
        "בשום אופן אל תרד עכשיו"; double negation "אל תפנה 90 מעלות שמאלה ואז אל תפנה ימינה".
      Negatives (MUST NOT fire): "תטוס קדימה בלי לעצור" (order: fly forward); "תסתובב ימינה, לא שמאלה"
        (order: turn right); any utterance with an imperative verb outside the negated clause; lookalikes.
      Placement: a deterministic stage in recognize_direct AFTER emergency, BEFORE the Gemma call.
      Returns ("reject", he, ["neg-guard"]) so the pipeline says the reject and sends NOTHING to the wire.
- [ ] A3 TEST first: test_negation_guard.py — positives refuse, negatives pass through, 0 false fires.
- [ ] A4 IMPLEMENT the rule; run the recognizer self-test + pytest (all green).
- [x] A5 RE-RUN full bench: 410/487, identical to A1; 0 changed cases; 0 unsafe flips; negations reject via guard.
- [x] A6 README scorecard updated in place (unified 410/487 line + negation-guard rule/positives/negatives).

## Workstream B — config merge (behaviour-PRESERVING; golden-master TDD)
- [ ] B1 BASELINE: capture resolved settings per scenario (webcam+mock, dji+mock, dji+real, bench)
      from the CURRENT env/script path -> golden file (test/golden_config.json).
- [ ] B2 WIRE app + launcher to config_constants.py/config_defaults.py; delete dead paths (translator,
      qwen3vl, omdet, MVD_DRONE); empty the scripts of config.
- [ ] B3 GOLDEN-MASTER test: new resolved settings == golden per scenario, field by field. Offline.
- [ ] B4 DRY PASS on data: run unified_bench once -> confirm still 410/487 end to end.

## Order & gating
A before B. Both before the outdoor validation (which freezes the baseline). Then cleanup finalises;
commit to the feature branch; merge to master as the stable demo. Owner tests too (final word).

## Status log (append)
- 2026-09-10 (start): skill loaded; A1 baseline bench launched in the background; designing the rule.

## A2 finalized rule design (2026-09-10)
negation_only(he) — clause-based, err toward NOT rejecting (zero false fires):
- Split he on [,.] and ואז/אבל/ורק into clauses.
- NEG trigger regex: (בשום אופן )?(אל ת\w+ | בלי ל\w+ | לא ל\w+).  POS imperative regex: bare/future
  motion verbs (תטוס/טוס/תעלה/עלה/תרד/רד/תסתובב/הסתובב/תפנה/פנה/תסע/סע/תזוז/זוז/תמריא/המריא/תנחת/נחת/
  תעוף/עוף/תחזור/חזור/בוא). NUM_UNIT = number/digit + מטר|מטרים|מעלות|מעלה|שניות.
- Per clause: npos=first NEG pos, ppos=first POS pos.
    if ppos is not None and (npos is None or ppos < npos): pos_found=True   # positive imperative BEFORE any negation = a real order
    elif npos is not None: neg_found=True                                    # negation governs the clause
    elif NUM_UNIT in clause: pos_found=True                                  # bare movement, don't reject
- REJECT iff neg_found and not pos_found.
- Verified by hand: r_neg1-5 + l75_neg_emphatic + double-negation -> reject. NON-fire: "תטוס קדימה בלי
  לעצור" (POS before NEG), "לא לטוס קדימה, תטוס אחורה 3 מטר" (2nd clause POS). Limitation: two imperatives
  in ONE clause with no separator, one negated one not, would over-reject; not in the dataset; err-safe side.
Placement: recognize_direct AFTER bypass, BEFORE apply_he -> return ("reject", he, ["neg-guard"]).
Wiring (3 spots): (1) recognizer.py negation_only() + the stage; (2) pipeline.handle_direct add
`elif kind == "reject": self.say(self.REJECT_HE + text); action = "reject-neg-guard"`; (3) unified_bench
add a kind=="reject" branch -> score([], expected) (CORRECT when expected == []).
Test: test/test_negation_guard.py — positives refuse, the 2 adversarial negatives pass through, 0 false fires.

## A1 BASELINE RESULT (2026-09-10 22:47) — CHANGES THE JUSTIFICATION
Baseline: ALL 487, tag negation-baseline. Totals: std 190/?, verbose 59/63, perception 103/138,
military 0/21, ALL 410/487. Latency p50 510 ms / p95 1066 ms, wall 251 s.
NEGATION CASES: ALL CORRECT at temp 0 — r_neg1-5, neg_trap, l_dbl_neg, l75_neg_emphatic all
"CORRECT-reject"; l75_neg_land_up4 + l75_neg_fwd_back3 (negation+order) CORRECT; v_neg1/2 CORRECT.
=> ZERO measured negation failures in the bench. Gemma already rejects every negation deterministically,
because UNIFIED_SHOTS now carries negation reject examples (incl. the double negation).
Implication: the skill's "> =2 measured failures" bar is NOT met. The guard is DEFENSE-IN-DEPTH against
the LIVE non-determinism (r_neg4 flew two spins "once, empty on retry" — variance the temp-0 bench does
not reproduce), not a bench fix. The main risk of building it becomes the guard REGRESSING a case Gemma
currently gets right (e.g. wrongly rejecting l75_neg_fwd_back3). PAUSED for an owner go/no-go.
Also note: current total is 410/487, not the "415/466" in older docs — that reference is stale.

## STATUS at stop (2026-09-11 ~01:00) — resume here in the morning
Workstream A (negation guard):
- [x] A1 baseline: 410/487; ALL negation cases already CORRECT at temp 0 (guard = defense-in-depth).
- [x] A2 rule designed (clause-based negation_only; POS list includes perception verbs after the
      "שים עין ... ואל תרד" false-fire catch).
- [x] A3 test written: test/test_negation_guard.py (10 pure-negation positives + 10 adversarial
      must-pass, incl. the perception+negation trap and negation-then-order).
- [x] A4 implemented in 3 files + offline tests GREEN: recognizer self-test clean; test_negation_guard
      3/3 pass. Changes are in the working tree, UNCOMMITTED (human owns git).
      Files touched: projects/integration_harden2/recognizer/recognizer.py (negation_only + stage),
      recognizer/pipeline.py (handle_direct reject branch), tools/bench/hebrew-command-bench/unified_bench.py
      (top-level kind=="reject" scoring branch).
- [x] A5 DONE (2026-09-11): re-ran full unified_bench, tag negation-guard. 410/487, identical to the A1
      baseline per set. compare_runs vs 2026-09-10-negation-baseline: 0 changed cases. 0 REJECT-neg-guard
      (no false fires). All six negations (r_neg1-5, neg_trap) reject via the guard (flag neg-guard),
      deterministically before the GPU. Raw: results/2026-09-11-negation-guard.json.
- [x] A6 DONE (2026-09-11): README scorecard updated in place — unified 410/487 line + the guard rule,
      positives, and adversarial negatives.
- [x] A7 DONE (2026-09-11): dataset grown to 24 must-refuse + 25 must-pass (49 adversarial cases). Exposed
      a real gap: a leading manner-negation before an order ("בלי לעצור תמשיך ישר") false-fired. Fixed by
      rewriting negation_only to the subtract rule (remove the negated verb, a surviving order verb = a real
      order) and adding continue/slow/speed verbs to the positive list. Re-ran the full bench (tag
      negation-guard-a7): 410/487, 0 changed cases vs baseline, 0 false fires. pytest 3/3, self-test clean,
      64 wiring tests pass. NEXT = Workstream B (config merge, golden-master).
Workstream B (config merge, golden-master) — NOT STARTED. See the plan above.
Reminder: the guard is a behaviour CHANGE (intended) and must be in the final system before the outdoor
validation. A5 is the first thing to run in the morning; it needs the Gemma server (~4 min).

## Appendix: assurance math for the negation (safety) class (persisted 2026-09-11)
Model: each negation utterance = one Bernoulli trial; X ~ Binomial(n, p), p = true failure rate.
Observed X=0 in ~15 cases. One-sided 95% upper bound on p (alpha=0.05):
- Exact (Clopper-Pearson), k=0:  (1 - p_U)^n = alpha  ->  p_U = 1 - alpha^(1/n).   0/15 -> 18.1%.
- Rule of three (Taylor of the exact): p_U ~= ln(1/alpha)/n ~= 3/n.   0/15 -> 20%.
- Wilson (p_hat=0): p_U = z^2/(n + z^2), z=1.96.   0/15 -> 20.4%.  (all three agree)
To reach p_U <= target at 0 failures: n ~= 3/target. <1% needs ~300 cases, ALL passing.
Implications: (1) bound falls only as 1/n -> 10x tighter = 10x data. (2) confidence is cheap (enters as
ln(1/alpha): 95->99->99.9% ~ x1.5 each); the RATE is expensive (halving target doubles n). (3) zero-
failures is a knife-edge: 1 failure in 300 -> Wilson upper ~1.8%, erases ~200 cases. (4) i.i.d. is the
weak point: failures cluster by structure (effective n < raw n) and the LIVE distribution != the bench
distribution, so a bench bound is necessary NOT sufficient. (5) a DETERMINISTIC guard sets p=0 by
construction for covered patterns -> converts an O(1/p) sampling problem into a finite COVERAGE problem;
residual risk = guard coverage gaps + ASR mishearing a negation. (6) so we need a few dozen ADVERSARIAL
cases spanning the structure, not 300 random draws.

## Workstream B — design notes + status (2026-09-11)
B1 DONE: test/capture_golden_config.py resolves the current config surface per scenario -> test/golden_config.json.
Surface = config.py attrs + the getenv reads scattered in scene_omdet.py / recognizer/pipeline.py /
video/video_watchdog.py (~47 keys). Host/network/time-derived values are excluded by design (HE font path,
resolve_device, default_gateway/PHONE_IP, session dir) — the merge keeps those resolver functions unchanged.

The scenario-varying keys split into two groups:
- Group 1, launcher BAKES the active value (identical across webcam/dji/mock/real; differs only from the
  naked bench import): BG off, DRONE_ROUTER on, TTS lang he. The bench's yolo/en are STALE config.py defaults
  that never apply in a real run, and the bench does not read them. The two draft files already bake the
  active values (BACKGROUND_SEGMENTER=None, TTS_LANGUAGE="he", routing unconditional). No behaviour changes.
- Group 2, genuinely derived from VIDEO_SOURCE / CONTROL_TARGET: video input (0 webcam / ros dji),
  WIRE_HOST (127.0.0.1 mock / PHONE_IP real), WIRE_PORT (8079 mock / 8080 real), WIRE_REAL (mock off / real on).

Dead keys the merge DROPS with the omdet/sam2/yolo path: BG_SEG_MODEL, SAM2_WEIGHTS, CONF_BG, DETECT_IMGSZ,
and the translator keys (MVD_TRANSLATOR, MVD_XLATE_PORT, MVD_TRANSLATE_PROMPT). The golden-master does NOT
assert these; deleting the code that reads them is the live-run-gated step below.

B2/B3 PLAN (staged; B2 rewire needs a live run to confirm — the bench covers only the recognizer):
- Complete config_constants.py + config_defaults.py to a full superset of the ACTIVE keys (DONE this
  session: 39 constants + the overridable defaults + video_input()/wire_target() derivers; additive, not
  yet imported by the app -> zero runtime risk). Proven by the golden-master below.
- B3 golden-master test/test_config_golden.py: resolve the active keys from the two files per app scenario,
  assert == golden. Offline. (done this session: test/test_config_golden.py, 2 tests green —
  every active key matches the golden across webcam_mock/dji_mock/dji_real; nothing silently lost.)
- B2 (GATED on owner + a live webcam run): swap every os.environ.get for the active keys in scene_omdet.py /
  pipeline.py / video/* to read the two config files; delete the omdet/sam2/yolo + translator code paths and
  their keys; strip those exports from run_mvd.sh. Nets: golden-master (values) + the 64 wiring tests (imports)
  + the bench (recognizer). Residual risk = live perception/camera/TTS runtime -> owner confirms with one
  webcam run. B4: re-run the bench, expect 410/487.

ONE CONFIRMATION (recommend yes, already implied by the drafts): bake the active values (he / bg-off /
router-on) as the decided constants and drop the stale config.py en/yolo naked defaults. The bench does not
read them, so nothing changes in behaviour; it only removes misleading dead defaults.

## Status update 2026-09-11 (config WIRED + perception capture + static-analysis pass)
B2 WIRING DONE (behaviour-preserving, proven offline):
- config.py is now a thin ADAPTER sourcing every value from config_constants.py + config_defaults.py,
  each env override preserved. Added to the two files: overlay colours (constants) and the host resolvers
  resolve_device/resolve_torch_device/default_gateway/resolve_he_font (defaults).
- scene_omdet's scattered perception knobs (SEG/GATE/HL_TOPK/HL_MAX/COUNT_*/MIN_BOX_FRAC/HL_GIVEUP/
  SAM3_PERIOD + the main() DETECT_FLOOR/HL_CONF/HL_REL) now take their defaults from the two files.
- Proof: golden-master 2/2; scene_omdet imports with every knob value identical (sam3/sam3/128/128/3/
  0.001/8.0/1.0); 70 offline tests; guard bench unaffected (410/487). The config files are no longer inert.
B2 REMAINING (cleanup, not blocking a flight): delete the omdet/sam2/yolo + translator dead code
  (incl. perception2/detectors.Eyes's unguarded YOLO(config.BG_SEG_MODEL)), and strip the now-redundant
  SCENE_*/MVD_* config exports from run_mvd.sh. These are dead-by-default; a live webcam run still confirms
  the wired app end to end.

Session-folder symmetry (owner, "dont mix the data"): session now = meta.json + asr/ (utterances.jsonl +
.log + clips/) + perception/ (frames + perception.jsonl). SessionLog + run_mvd.sh write there; the 5 reader
tools fall back to the legacy top-level layout so old sessions still read.

Static-analysis / dry-run pass on every session feature: see docs/NOTES.md 2026-09-11. One latent bug fixed
(recognize_direct None-crash, unreachable live, hardened); one dead-code trap identified (perception2 Eyes
unguarded YOLO on BG=off) for the dead-code deletion; guard is fail-safe (reject only); perception threads
dry-run crash-free.
