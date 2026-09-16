# Fine-tuning data: how much, what shape (2026-09-02, answers to owner questions)

Everything here is standard-practice ballpark, NOT measured by us — labeled accordingly.

## Fix-order before any fine-tune (cheapest first)

1. Deterministic glossary/canonicalizer for the CLOSED vocabulary (acronyms, procedure words,
   idiom triggers): ~50–150 lexicon entries, zero training data. Fixes ASR garble and
   translator garble in one layer, placed right after ASR. The slang probe says this is where
   most of the loss is.
2. Planner few-shot / prompt additions (idiom → action mapping, e.g. Indian circle → fly_circle):
   10–30 curated examples. The revised-prompt result (56→94 on the app engine) shows the size
   of this lever.
3. LoRA, only after 1–2 saturate.

## Dataset sizes (unverified, literature practice)

- LoRA on a 1–4B model (DictaLM) for register adaptation or direct Hebrew→mission-JSON parsing:
  ~1,000–5,000 high-quality pairs; visible gains often from ~1k. Quality and coverage beat volume.
- Full NMT domain adaptation (translator register): ~10,000–100,000 parallel pairs, usually
  reached with back-translation augmentation from monolingual in-domain Hebrew.
- Whisper LoRA for vocabulary/register: ~5–50 hours in-domain audio. Hotword biasing
  (faster-whisper initial_prompt, sherpa-onnx hotwords) costs zero training and comes first.
- Rule of thumb for the closed lexicon: ~20–50 carrier sentences per lexicon item, varied
  frames. 100-item lexicon × 30 ≈ 3,000 sentences — that is the whole text dataset.

## The data point (one example, all fields)

{audio (ASR only), raw_hebrew, canonical_hebrew (post-glossary), english_ref (if translation
kept), intent_json (the mission array — ground truth), tags: [class: command/perception/
military/emergency, homograph?, negation?, question?, steps: N, units: m/ft]}

## Structures the set must capture (axes, not volume)

1. Closed lexicon coverage: every acronym + expansion + target action; procedure words in
   opening/closing position.
2. Homograph minimal pairs — same word, both senses, context decides (המראה, עבור, רות, רגל).
3. Idiom → action + argument slots (מעגל אינדיאני על X → circle(target=X)).
4. Negation, questions, refusals.
5. Numbers and UNITS: military speaks feet, our wire schema is meters — unit conversion is a
   new requirement discovered by the slang probe (s_feet_hold).
6. Multi-step missions with order preserved.
7. For ASR: speaker/channel variation — wind, distance, radio compression, clipped fast speech.
8. Distractors and near-misses (should produce []).

## The ASR-abbreviation problem (owner: "who says ASR captures them?")

Nobody — and it is likely WORSE than the translation stage: whisper models normalize and
"correct" toward their training distribution (podcasts/web for ivrit-ai), so נ.צ. can surface
as נץ, חפ"ק as noise. Mitigation ladder: (1) measure first — the recording script's military
class exists exactly for this; (2) hotword/bias lists at decode time (zero training);
(3) post-ASR fuzzy canonicalizer against the closed lexicon (same layer as fix-order #1);
(4) whisper LoRA last. The eval recordings (~1,040 clips) are an EVAL set; a training set for
LoRA would need the sizes above and does not exist yet.
