# Groundstation

A voice-commanded camera drone with scene understanding. A human speaks; the system understands the
scene the drone sees and acts. Human-in-the-loop and safety-gated (see `../CLAUDE.md`). No
weaponization, no targeting, no payload.

## The three project trees

- **`projects/integration_harden2/` — the LIVE system (MVD).** Hebrew voice in (whisper-ivrit ASR) ->
  one Gemma-4 call that routes + plans + speaks Hebrew, behind a deterministic recognizer safety sieve
  -> {mission verbs -> DJI REST | perception queries -> SAM3 open-vocab detect/count/highlight}.
- **`projects/integration_tts/` — the FROZEN demo fallback.** The proven English MVD; changes land in
  forks, never here.
- **`projects/llm_to_action/` — the PARKED destination (C++).** An FMU 20 Hz control loop over a
  `GenericBackend` (CRTP); the real product harden2's layer will eventually fold onto. Design of record:
  `spec-fmu-architecture.md`.

## How the live path runs

The Linux laptop is the brain. A DJI drone is flown from a phone (ExoSkeletons MSDK app); the laptop
reaches it over WiFi -- control + telemetry on `:8080` (REST), raw H.264 video on `:5600`. Perception
(SAM3, ONNX depth/seg) runs on the laptop; the 8 GB GPU holds the VLM, so seg/depth run on the CPU.
Safety is law: the assistant prepares arm/takeoff/land/motor commands; a human runs them.

## Docs map (flat; prefixes name the category)

| Prefix / file | What it is |
|---|---|
| `README.md` `ROADMAP.md` `HISTORY.md` `guidelines.md` | overview, forward plan, running log, code+prose rules |
| `spec-harden2-architecture.md` | the LIVE harden2 architecture (measured numbers, env switches, boot) |
| `spec-harden2-run-arguments.md` | every harden2 run env var / argument |
| `spec-fmu-architecture.md` | the parked C++ FMU engine spec (was ARCHITECTURE.md) |
| `spec-dji-*.md` | the DJI wire: websocket protocol, H.264 video, backend |
| `research-*.md` / `research-complete-*.md` | investigations; `-complete-` = finished |
| `task-active-*.md` | in-flight task docs (`task-active-<name>-*`) |
| `task-scheduled-*.md` | not-yet-started phases |
| `stale/` | superseded docs, deleted after the GitHub commit; git history is the archive |
| `private/` | gitignored, never committed |

The docs live flat: no nested folders except `stale/` and `private/`. A file's prefix names its category.
