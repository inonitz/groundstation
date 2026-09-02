# ASR recording spec — for the team (2026-09-02)

What this is for. An EVALUATION set (not training data) for the ASR round: whisper-turbo-v3
ivrit-ai across serving stacks (CT2/faster-whisper, whisper.cpp quants, sherpa-onnx/onnxruntime,
GPU and CPU), measured on OUR sentences instead of a generic corpus. It also measures, for the
first time, whether ASR survives military abbreviations at all.

## What to record

The 65 sentences in RECORDING-SCRIPT.md: 25 movement commands, 15 perception commands,
20 military-phraseology probes, 5 emergency/override phrases. One clip per sentence.

## Who and where

- Speakers: at least 4 different people (mixed voices; the more the merrier).
- Environments, each speaker records the full script once per environment:
  1. quiet indoor room
  2. outdoors with wind (this is the demo reality — most important set)
  3. noisy background (street / crowd / TV)
  4. phone held at arm's length while walking (handling noise + distance)
- Total: 65 x 4 speakers x 4 environments = 1,040 clips, roughly 60–90 minutes of audio.
  A partial delivery is fine — priority order: env 2, then 1, then 4, then 3.

## Format

- One file per sentence. WAV 16 kHz mono preferred; phone default (m4a/44.1k) acceptable,
  we resample.
- Filename: `s<speaker-number>_e<env-number>_<case-id>.wav` (e.g. `s1_e2_up10.wav`).
  Speaker NUMBERS, not names — recordings and any transcripts stay out of git and out of
  logs (same privacy rule as the sttserv benchmarks).
- Read naturally at command pace. Mistakes are fine — mark redone takes with `_r2` suffix.

## What we measure with it

Per serving stack: word/character error rate per sentence class (command / perception /
military / emergency), per environment, plus latency and peak memory. The military class tells
us whether acronyms (נ.צ., חפ"ק, כטב"ם) survive ASR before any hotword biasing — nobody has
verified this, and the translation bench says the models downstream will not fix what ASR breaks.
