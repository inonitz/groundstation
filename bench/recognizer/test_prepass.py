"""Tests for prepass.py's scoring: the word edit distance and the word error rate.
whisper itself is not run here."""
from prepass import edits, heard, word_error_rate


def test_edits_counts_each_kind_of_word_error():
    assert edits("a b c", "a b c") == 0
    assert edits("a b c", "a x c") == 1           # one substitution
    assert edits("a b c", "a c") == 1             # one deletion
    assert edits("a b c", "a b c d") == 1         # one insertion
    assert edits("", "a b") == 2
    assert edits("a b", "") == 2


def test_the_rate_is_all_edits_over_all_label_words():
    cases = [
        {"name": "one", "he_label": "טוס קדימה", "he": "טוס קדימה"},
        {"name": "two", "he_label": "עלה שני מטרים", "he": "עלה מטרים"},
    ]
    asr = word_error_rate(cases)
    assert asr["clips"] == 2 and asr["words"] == 5
    assert asr["wer"] == 20.0
    assert [pair["errors"] for pair in asr["pairs"]] == [0, 1]


def test_number_words_and_digits_match_in_the_digit_rate():
    cases = [
        {"name": "n", "he_label": "טוס אחורה 8 מטרים", "he": "טוס אחורה שמונה מטרים"},
    ]
    asr = word_error_rate(cases)
    assert asr["wer"] == 25.0
    assert asr["wer_digits"] == 0.0


def test_the_digit_rate_divides_by_the_label_words_in_digit_form():
    """"עשרים וחמישה" is 2 words but "25" is 1: 1 error over 2 words, not over 3."""
    cases = [{"name": "n", "he_label": "עלה עשרים וחמישה", "he": "עלה שלושים"}]
    assert word_error_rate(cases)["wer_digits"] == 50.0


def test_labels_mode_drops_removed_clips_and_keeps_the_owner_text():
    cases = [
        {"name": "a", "he": "טוס", "wav": "x.wav"},
        {"name": "b", "he": "", "wav": "y.wav", "removed": True},
    ]
    out, asr = heard(cases, keep_labels=True)
    assert asr is None
    assert [case["name"] for case in out] == ["a"]
    assert out[0]["he"] == out[0]["he_label"] == "טוס"


def test_whisper_markers_are_not_words():
    from prepass import MARKER_RE
    text = MARKER_RE.sub(" ", "[BLANK_AUDIO] טוס (music) קדימה")
    assert text.split() == ["טוס", "קדימה"]
