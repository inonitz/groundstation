# Checklist 2026-09-09 — judges at 10:00, team at 09:00 (tick as you go; times are targets)

## Team document
- [x] 06:00 docs/private/team-summary-2026-09-09.pdf (7 pages) + md + competitors-validation.md; owner reads STATUS + checks the PDF by eye

## Deck (owner + teammate)
- [x] harden2 simplified / language / perception diagrams (dot, png, svg, drawio) — docs/active/assets
- [x] demo-day-style delta diagram — harden2-simplified-demoday.drawio + png
- [x] llm_to_action diagrams — the llm_to_action lane's pair (owner approved)
- [x] DJI API server diagrams + route doc — dji-apiserver-*.{dot,png,svg,drawio}, 2026-09-09-dji-apiserver-architecture.md
- [x] scope slide + speaker notes — slide-scope.{md,png}, slide-scope-notes.{md,png}
- [x] numbers slide — slide-numbers.{md,png}
- [x] method slide — slide-method.{md,png}
- [x] research slides, 7, with the tables — slides-research.md, slide-r1..r7.png
- [ ] 04:50 hand everything to the teammate; say which files are placeholders (the slide-*.png)
- [ ] decide: research = 1 slide or 7 (owner)
- [ ] scope-slide note 5.1.5 says "flight video today": change it if the flight fails
- [ ] re-read the two brute answers (novelty, differentiation) — chat only, by rule

## Testing (run sheet: tools/desk-test/live-run-2026-09-09.md)
- [ ] after any laptop/container restart: bash /root/groundstation/tools/devenv/install-runtime-deps.sh, then preflight (07:19: bitsandbytes was gone)
- [x] 05:50 A. webcam + mock: 7/7 routed, kill + re-arm proven; count jitter fixed (median of 3 frames) -- verify the count in B
- [x] fix anything A breaks (agent): counting fix + kill lines in app.log; 21 tests pass
- [ ] batteries on charge now: aircraft packs, RC, phone, laptop
- [x] 06:25 B. phone + drone video + mock: mark + count + Hebrew TTS worked; vision-word fixes landed (lexicon, synonyms, positional strip, SCENE_GATE switch)
- [x] 07:30 C. real control: 6 missions flew (HTTP 200) after two blockers (unbound var, hotspot IP changed); check the recordings exist
- [ ] 07:30 abort rule: no flight -> webcam demo (A) is the live demo
- [ ] after C: down.sh; session folder = evidence; agent scores it

## Repo
- [ ] 07:45 commit harden (handoff §9 block) and harden2 (the whole tree + desk-test + bench changes) — owner runs git
- [ ] the 7 other-lane files under llm_to_action stay out of this commit

## Meeting
- [ ] 08:15 one timed rehearsal: scope -> diagrams -> numbers -> video/live demo; 20 + 10 + 15 min
- [ ] 09:00 team: roles (opener/closer, diagrams + demo, backups holder)
- [ ] demo laptop: external monitor off the dGPU or accept the VRAM; C920 + mock work standalone, no internet needed
- [ ] do-not-say list in the live demo: double negations, "אפשר ל...?" questions, slang, "עצור ל-10 שניות"

## After the judges (priority order, from the form)
- [ ] data folder + docs consolidation (handoff §16), one day
- [ ] negation rule in code (the one unsafe event)
- [ ] target approach (3.1): SAM3 target + approach behaviour
- [ ] noise / low light (4.1, 5.1.1): whisper on noisy clips first
- [ ] military slang (5.2.1), context across utterances (5.2.2)
- [ ] human labels for the 22 vision asks -> a real perception number
- [ ] fine-tune Gemma on the corpus once it is a few thousand cases
- [ ] speaker identification (5.3.1), last
