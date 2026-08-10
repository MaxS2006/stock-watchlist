"""Signal-strength scoring tests — the up/down/neutral tally and the
resulting LEANS POSITIVE / LEANS NEGATIVE / MIXED SIGNALS / NOTHING
COMPELLING label.
"""

from monitor import compute_signal


def factors(pos=0, neg=0, neutral=0):
    """Build a minimal factors list with the given lean counts — the
    labels themselves don't matter to compute_signal(), only "lean"."""
    return (
        [{"label": "p", "lean": "pos"} for _ in range(pos)]
        + [{"label": "n", "lean": "neg"} for _ in range(neg)]
        + [{"label": "u", "lean": "neutral"} for _ in range(neutral)]
    )


def test_majority_positive_leans_positive():
    signal = compute_signal(factors(pos=3, neg=2, neutral=0))
    assert signal["label"] == "LEANS POSITIVE"
    assert signal["class"] == "bullish"
    assert signal["icon"] == "▲"
    assert (signal["up"], signal["down"], signal["neutral"]) == (3, 2, 0)


def test_majority_negative_leans_negative():
    signal = compute_signal(factors(pos=1, neg=3, neutral=1))
    assert signal["label"] == "LEANS NEGATIVE"
    assert signal["class"] == "bearish"
    assert signal["icon"] == "▼"
    assert (signal["up"], signal["down"], signal["neutral"]) == (1, 3, 1)


def test_tied_nonzero_counts_is_mixed_signals():
    signal = compute_signal(factors(pos=2, neg=2, neutral=1))
    assert signal["label"] == "MIXED SIGNALS"
    assert signal["class"] == "mixed"
    assert signal["icon"] == "⚠"


def test_all_neutral_is_nothing_compelling():
    signal = compute_signal(factors(pos=0, neg=0, neutral=5))
    assert signal["label"] == "NOTHING COMPELLING"
    assert signal["class"] == "mixed"
    assert signal["icon"] == "◆"


def test_barely_one_signal_amid_neutrals_is_nothing_compelling():
    # A single lone lean (up+down <= 1) isn't a real signal even though
    # it's technically "1 up, 0 down" — this is the case that
    # distinguishes NOTHING COMPELLING from a tie.
    signal = compute_signal(factors(pos=1, neg=0, neutral=4))
    assert signal["label"] == "NOTHING COMPELLING"
    assert signal["class"] == "mixed"


def test_single_negative_lean_amid_neutrals_is_also_nothing_compelling():
    signal = compute_signal(factors(pos=0, neg=1, neutral=4))
    assert signal["label"] == "NOTHING COMPELLING"


def test_empty_factors_is_nothing_compelling():
    signal = compute_signal([])
    assert signal["label"] == "NOTHING COMPELLING"
    assert (signal["up"], signal["down"], signal["neutral"]) == (0, 0, 0)


def test_strong_unanimous_positive_lean():
    signal = compute_signal(factors(pos=5, neg=0, neutral=0))
    assert signal["label"] == "LEANS POSITIVE"
    assert signal["class"] == "bullish"


def test_strong_unanimous_negative_lean():
    signal = compute_signal(factors(pos=0, neg=5, neutral=0))
    assert signal["label"] == "LEANS NEGATIVE"
    assert signal["class"] == "bearish"
