"""Path B's prepass (task B2, ruling U2.2): each recorded clip -> whisper's text; path A
then scores that text. Also whisper's word error rate against the owner's labels, which
are the reference (owner M5, JR2).

whisper-cli runs the app's ASR model with the live ASR server's decode settings
(sttserv/source/backend_whisper.cpp): beam search 8, no timestamps, the same starting
prompt carried into every window, one thread (audio/asr_ros.py). Not mirrored:
single_segment, which whisper-cli has no flag for; a clip under 30 s is one window.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden2"))
sys.path.insert(0, os.path.join(ROOT, "bench", "hebrew_asr"))

import config                                                   # noqa: E402
from asr_bench import normalize_he                              # noqa: E402
from runtime.fatal import die                                    # noqa: E402
from util.hebrew import hebnum_to_digits                        # noqa: E402

WHISPER_CLI = os.path.join(config.NATIVE_BIN_DIR, "whisper-cli")
BEAM_SIZE = "8"
THREADS = "1"
# whisper's non-speech markers ("[BLANK_AUDIO]", "(music)"): not words anyone said
MARKER_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")
# the live server's kWhisperSystemPrompt, word for word
ASR_PROMPT = (
    "You are listening to audio input in a noisy environment.\n"
    "There may be wind, industrial vehicles operating and also man-made noises.\n"
    "You are tasked with deciphering your operators' instructions, who will talk the "
    "closest to the microphone\n"
)


def heard(cases, keep_labels=False):
    """The active clips (not "removed"), each with `he_label` = the owner's sentence and
    `he` = whisper's text, or the label again when keep_labels. -> (cases, asr): asr is
    whisper's word error rate with every pair, or None when keep_labels."""
    active = [case for case in cases if not case.get("removed")]
    out = []
    texts = []

    if keep_labels:
        for case in active:
            out.append(dict(case, he_label=case["he"]))
        return out, None

    texts = whisper_texts([case["wav"] for case in active])
    for case, text in zip(active, texts):
        out.append(dict(case, he=text, he_label=case["he"]))
    return out, word_error_rate(out)


def whisper_texts(wavs):
    """[whisper's text] in the order of `wavs`, without non-speech markers. One
    whisper-cli run loads the model once for every clip. Each clip is linked into a
    temporary folder, removed afterwards, so no text file lands next to the clips."""
    with tempfile.TemporaryDirectory(prefix="b2-whisper-") as folder:
        return _whisper_in(folder, wavs)


def _whisper_in(folder, wavs):
    links = []
    texts = []
    text = ""
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = config.NATIVE_BIN_DIR + ":" + env.get("LD_LIBRARY_PATH", "")

    for i, wav in enumerate(wavs):
        link = os.path.join(folder, f"{i:04d}.wav")
        os.symlink(os.path.join(ROOT, wav), link)
        links.append(link)

    argv = [
        WHISPER_CLI,
        "-m", config.ASR_MODEL_PATH,
        "-l", config.ASR_LANGUAGE,
        "-bs", BEAM_SIZE,
        "-t", THREADS,
        "-nt",
        "-np",
        "--prompt", ASR_PROMPT,
        "--carry-initial-prompt",
        "-otxt",
    ]
    done = subprocess.run(argv + links, env=env, capture_output=True, text=True)
    if done.returncode != 0:
        die(f"whisper-cli failed ({done.returncode}): {done.stderr[-800:]}")

    for link in links:
        path = link + ".txt"
        if not os.path.exists(path):
            die(f"whisper-cli wrote no text for {link}; its folder: {folder}")
        with open(path, encoding="utf-8") as f:
            text = MARKER_RE.sub(" ", f.read())
        texts.append(" ".join(text.split()))
    return texts


def edits(ref, hyp):
    """The word edit distance (substitutions, deletions, insertions) from ref to hyp."""
    ref_words = ref.split()
    hyp_words = hyp.split()
    row = list(range(len(hyp_words) + 1))
    previous = []
    cost = 0

    for i, word in enumerate(ref_words, 1):
        previous = row
        row = [i]
        for j, other in enumerate(hyp_words, 1):
            cost = 0 if word == other else 1
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + cost))
    return row[-1]


def word_error_rate(cases):
    """Whisper's word error rate over every clip, in %: all edits over all label words.
    Twice: on the plain words, and with number words turned into digits on both sides
    (the owner typed "8" where whisper can write the word). Each rate divides by the
    label's word count in its own form: "עשרים וחמישה" is 2 words, "25" is 1. -> a dict
    with every pair."""
    pairs = []
    words = 0
    digit_words = 0
    plain = 0
    digits = 0
    errors = 0
    ref = ""
    ref_digits = ""

    for case in cases:
        ref = normalize_he(case["he_label"])
        ref_digits = normalize_he(hebnum_to_digits(case["he_label"]))
        errors = edits(ref, normalize_he(case["he"]))
        words += len(ref.split())
        digit_words += len(ref_digits.split())
        plain += errors
        digits += edits(ref_digits, normalize_he(hebnum_to_digits(case["he"])))
        pairs.append({
            "name": case["name"],
            "label": case["he_label"],
            "whisper": case["he"],
            "errors": errors,
        })

    return {
        "clips": len(cases),
        "words": words,
        "wer": round(100.0 * plain / max(words, 1), 1),
        "wer_digits": round(100.0 * digits / max(digit_words, 1), 1),
        "pairs": pairs,
    }
