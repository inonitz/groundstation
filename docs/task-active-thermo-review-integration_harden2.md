# Thermo-nuclear review — integration_harden2 (2026-09-17)

Scope: the whole `projects/integration_harden2` module (it is entirely new vs master, so the
branch review == the module). Method: 5 parallel read-only agents applying the thermo-nuclear
standards (ambitious structural simplification / code-judo, spaghetti, boundary + type cleanliness,
file size, canonical-layer reuse). Static analysis + grep call-graph only — **no code was run and no
proposed change was verified at runtime.** Every "dead" claim is grep/call-graph evidence: strong,
not runtime-proven. Per-area detail lives in
`scratchpad/thermo-{orchestration,recognizer,perception,control-config,audio-session}.md`.

File-size rule (1000 lines): **no violation.** Largest is recognizer.py at 786; mvd.py 561.

GATE ON ANY CHANGE: every deletion must be gated by the 66-test suite AND the 410/487 unified_bench
re-run before it is trusted. Develop in a fork, prove green, then merge. These are review findings,
not decisions.

---

## Headline: two abandoned migrations left large dead layers

The single biggest quality issue, repeated three times. Prior migrations shipped the new path but
never deleted the old one, so whole layers stay alive only through conditionals and tests.

1. Translator retirement -> ~240-260 dead lines in the recognizer. `recognizer.py:329-570`
   (stages 4/4b/5/6: number-retry ladder, answer-mode, colour guard, English rewrites, `route`) has
   no live caller; only `selftest()` (`recognizer.py:573-716`, 143 lines) keeps it "used".
   `_nums_en`/`EN_NUM` survive only because `is_shot_echo` feeds Hebrew to the English number parser
   (`recognizer.py:395-421`, `pipeline.py:39-45`) — repoint to `_nums_he` and both delete.

2. SAM3 adoption -> half-finished `perception2/` fold. `perception2/__init__.py:2-5` claims the
   engine/vlm_client/detectors copies "were removed 2026-09-11" — they are still on disk, dead.
   `perception2/engine.py` (189), `vlm_client.py` (116), `detectors.py` (124, OmDet+SAM2) are
   imported by nothing live; `chain_demo.py` is broken. mvd.py uses only `phrase_concepts`,
   `count_instances/median_count`, `Sam3Backend`, plus `lexicon.fix_target`. Move those 4 live
   modules into `perception/`, delete the 4 dead files, delete `perception2/`, repoint ~6 imports.

3. SAM3 adoption -> dead OmDet dual-backend scaffolding in the render path. `build_highlight`
   (mvd.py:153-154) hard-raises unless the backend is `sam3`, yet mvd.py/overlay.py still branch on
   `SEG`, thread an `OM = {"name":"SAM3"}` identity-dict through the render path, plumb `om_name`
   across both files, and keep a dead `"omdet"` map entry (mvd.py:64,78,273,332,337;
   overlay.py:126-140). Make `phrase_concepts` unconditional and the whole "which backend" concept
   leaves the render path.

Net: three deletions remove roughly a package, ~260 recognizer lines, and a backend-selection layer,
with no behavior change to the live Hebrew-voice -> SAM3 path.

---

## Findings by area (most-structural first)

### Orchestration + UI (mvd.py 561, overlay.py 229)
- Dead OmDet backend layer — headline #3.
- Chat semantics are string-encoded then reverse-parsed. overlay.py:187-229 recovers each row's
  meaning by prefix-matching literal English AND Hebrew strings mvd.py wrote. Tag intent on the
  entry as `(role, text, kind)` and delete the `startswith` sniffing (`_miss`/`_hit`).
- `("meta","")` separator emitted by mvd.py:224, skipped by overlay.py:174 as "legacy" — delete both.
- Session recording is monkey-patched in (mvd.py:428-447 replaces `wire.fly_mission`/`wire.halt`/
  `pipe.handle`); route it through the `observe=` hook the Pipeline already accepts.
- Vestigial OmDet knobs `S.conf`/`S.mask_k` (mvd.py:89,117) — read into locals, never used; delete.

### Recognizer (recognizer.py 786, pipeline.py 136, prompts.py 193, llama.py 92, trace.py 28)
- Dead translator-era stages + English numbers + self-test — headline #1.
- `pipeline.py:88-127` `handle_direct` is a three-level nested tag/kind/mission dispatch — extract
  `_route_planner_result`.
- Module docstring (recognizer.py:1-24) advertises the retired 7-stage translated pipeline
  (contradicts line 761).
- Decomposition after the deletes (786 -> ~520): split into numbers/emergency/bypass/rewrites/guards
  with `__init__` re-exporting current names so all 8 consumers import unchanged.

### Perception (both packages)
- Collapse `perception2/` into `perception/` — headline #2.
- `perception2/__init__.py:2-5` docstring lies about the disk state.
- `perception/vlm_client.py:1` has a stray `import os` above the docstring (demotes the docstring to
  a dead string; the perception2 copy lacks it — a drift marker).
- `perception/vlm_client.py` reads a `GEMMA` planner flag from env at import time, toggling
  temperature + grammar inside the shared client — un-overridable per call, invisible to tests.

### Control + config (control/*, config*.py)
- Config is WIRED — the "DRAFT, not yet wired" docstrings are false (imported by 8 modules, read
  directly by mvd.py, pinned by two golden tests). Fix the header.
- The two value files do not earn the split: `config.py` re-wraps the "baked" constants in
  `os.environ.get` anyway. Merge `config_constants.py` + `config_defaults.py` into one values file;
  keep `config.py` as the adapter (it applies env overrides and sets MIOPEN before torch — not a
  pure pass-through).
- Ports declared once, hardcoded everywhere. The Ports block is write-only except
  `LLAMA_SERVER_PORT`/`TTS_PORT`; the literals recur as `QWEN_PORT=18090` (pipeline.py:34),
  `"http://127.0.0.1:18090"` (concept.py:186), `port=8080` (dji_wire.py:31, phone_asr.py:25),
  `:8080`/`:5600` (video_doctor.py). Consume the constants.
- `config.wire_target()` + the `CONTROL` env var are DEAD — the live wire is built by
  `DjiWire.from_env()` from `MVD_WIRE_*`. Delete the unused parallel switch.

### Audio + session (audio/*, session_log.py)
- TTS backend logic is triplicated in tts_io.py: three readiness booleans (:48-53), the if/elif
  setting `_local_kind` (:55-62), the fallback dispatch in `_say_local` (:130-141). Already drifted
  — the espeak re-check at :64-66 is dead. Collapse the LOCAL backends into one table
  `{name:{ready,say}}` with espeak as the declared fallback (~20 lines gone). Keep `phone` OUT (a
  network sink with a different lifecycle; `both` runs it independently). Do it in a fork and bench
  phonikud/piper before merging; not hot before the field test.
- Duplicated probes: `which("espeak-ng") or which("espeak")` x3, `which("aplay")` x4 — fold into helpers.
- session_log.py mixed concurrency: `rec` is thread-local but `_seq`/`_req`/`_claimed` are shared
  singletons; it is single-consumer — drop the thread-local and say so. (Atomic writes are correct.)
- Clean: ros2_asr.py, phone_asr.py (nit: shutdown doesn't close the server), run_llama_server.sh.

---

## Drone-safety flags (touch the CLAUDE.md hard rules)

- CLEAN and load-bearing: `dji_wire.py` loopback guard — hard `raise` on any non-loopback host
  unless `allow_real=True`; fail-safe defaults. The ONLY real mock/real separator. Preserve verbatim.
- DANGEROUS doc/code mismatch: `config_constants.py:6` states "CONTROL_TARGET alone decides the
  wire." False — `MVD_WIRE_REAL` decides it. `CONTROL=mock` does not constrain the wire. Fix the doc
  AND make the switch real, or delete the claim.
- `MOCK_WIRE_PORT=8079` is a phantom — the mock actually binds 8080 (same as real); only the host
  guard separates them.
- `kill.py:9` docstring says `halt()` "stays allowed" after a kill; the code refuses it (halt routes
  through the guarded `fly_mission`, returns 409). The docstring describes an UNSAFE behavior; never
  "fix" the code to match. Correct the docstring.
- `KillSwitch.MOTION` over-lists: six of nine entries are already covered by the `fly_mission` guard;
  `track_me`/`wave` are omitted. Minimal correct set is `{takeoff, land, fly_mission}`.

---

## Recommended action groups (owner rules each; all gated by tests + bench)

1. Safe dead-code deletes (highest value, behavior-preserving): recognizer stages 4/4b/5/6 + English
   numbers + selftest; perception2 dead files + directory collapse; OmDet render-path scaffolding.
2. Safety-doc corrections (do before the field test): the CONTROL_TARGET claim, the halt() docstring,
   the MOCK_WIRE_PORT phantom, the kill MOTION list.
3. Config consolidation: fix the "not wired" lie, merge the two value files, consume the Ports
   constants, delete the dead `wire_target()`/`CONTROL` switch.
4. Structural cleanups: tag chat entries, route recording through `observe=`, extract `handle_direct`
   dispatch, TTS backend registry, recognizer decomposition.

Confidence: headline deletes are grep/call-graph verified (high). Config-gated branches (VLM
presence-gate, ASCII fallback renderer) are NOT provably dead — owner ruling needed before deletion.

---

# Ponytail cross-check (ultra) — 2026-09-17

Ran the ponytail over-engineering audit (ultra: deletion-first) as an independent second pass to
corroborate the above. It confirmed the structural findings and forced ONE correction that would
otherwise have shipped an unsafe deletion. Detail: `scratchpad/ponytail-harden2-{logic,runtime}.md`.

## Corroboration
- OmDet dead render scaffolding — CONFIRMED (independent evidence, same conclusion).
- overlay string round-trip — CONFIRMED (tag entries `(role,text,kind)`).
- TTS triplication + dead espeak re-check — CONFIRMED.
- run_mvd.sh duplicate launcher, run_router.py dead — CONFIRMED.
- perception2 half-fold — CONFIRMED and STRONGER: engine.py/vlm_client.py are near-verbatim
  duplicates of perception/ v1 (33 and 18 differing lines); chain_demo.py CRASHES on import.
  ~494 dead lines in perception2.
- config: CONFIRMED worse — mvd.py:20 bypasses the config.py adapter and imports `_K`/`_D` directly
  for ~11 symbols while ALSO using `config.X`; two import surfaces. wire_target/video_input/
  CONTROL_TARGET are test-only.

## CORRECTION (verified against source — supersedes the recognizer finding above)
The thermo pass said "delete `_nums_en`/`EN_NUM`, repoint `is_shot_echo` to `_nums_he`." **That is
unsafe and is retracted.** Proven by reading the code: `_nums_en` is LIVE — `pipeline.py:107`
(`handle_direct`, the live path) calls `is_shot_echo`, which calls `_nums_en` at `pipeline.py:49`.
`handle_direct` passes `he2` (Hebrew) as the `english` arg, so `_nums_en` always returns `[]` — it is
live-but-inert. Deleting it or repointing to `_nums_he` would CHANGE `is_shot_echo`'s result. Do NOT
delete `_nums_en`/`EN_NUM`. (Whether `is_shot_echo` itself is vestigial from the translated era is a
separate question needing care, not a blind cut.)
So the genuinely-dead recognizer slice is ~180 runtime lines (stages 4b/5/6 + the stage-4 EN
reconciliation `check_numbers`/`patch_number`/`_resolve_numbers` + `check_colors` + the selftest lines
that test them), NOT ~260, and NOT including `_nums_en`/`EN_NUM`.

## New cuts ponytail added (not in the thermo pass)
- yagni: `config.py` is a redundant adapter mvd bypasses — pick one import surface (~50 lines).
- native: two gateway-discovery impls in config_defaults.py (`_default_route_ip` via `ip route`
  subprocess vs `default_gateway` via `/proc/net/route`) — collapse to one.
- delete: ceremonial port constants never read in Python (VIDEO_TCP_PORT; PHONE_ASR_PORT read as a
  literal "8080" in mvd).
- shrink: duplicate number-token predicate (`_number_token` vs `_nums_he`'s inner `is_number`).
- shrink: in-module selftests in perception2/engine.py + sam3_backend `_smoke` duplicate the pytest suite.

## Consolidated removable estimate (integration_harden2)
~700-780 lines (perception2 ~494 + recognizer genuinely-dead ~180 + config collapse/dead switch/ports
~68 + dedup ~40). STATIC estimate; the `_nums_en` case proves each deletion must be gated by the 66
tests + the 410/487 bench before it is trusted. No whole top-level dependency drops (live perception/
v1 still imports the same packages).
