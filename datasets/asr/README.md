# datasets/asr — Hebrew ASR corpus from live sessions

Built 2026-09-15 from logs/sessions clips + their session transcripts. Gitignored (private audio).

- `clips/<session>__<clip>.wav` — the recorded push-to-talk audio.
- `manifest.jsonl` — one row per clip: session, clip, transcript_he, action, kind, match.

IMPORTANT: `transcript_he` is whisper's OUTPUT (what was heard), NOT a corrected ground-truth reference.
This is a raw corpus. Turning it into a SCORED eval set needs the correction pass (a human/tooling step),
which is still the deferred Phase-2 work. `match` shows how each clip was linked (by-audio_clip / positional / unmatched).
