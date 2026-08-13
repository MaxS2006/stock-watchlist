"""Experimental weighted-signal tests — compute_weighted_signal's scoring/
labeling logic and the intercept-baseline split between LEANS POSITIVE and
MIXED SIGNALS. Uses fixture weights (monkeypatched), not the real fitted
WEIGHTED_FACTOR_WEIGHTS constant, so these stay valid across re-fits.
"""

import monitor

# A deliberately small fixture weight set. Unlike the real fitted weights
# (where only one weak coefficient is negative — see the comment above
# WEIGHTED_FACTOR_WEIGHTS in monitor.py), this one has genuinely negative
# options so every branch (POSITIVE / MIXED / NEGATIVE) is reachable.
FIXTURE_WEIGHTS = {
    "intercept": 0.1,
    "rsi": {"pos": 0.5, "neg": -0.5, "neutral": 0.0},
    "volume": {"pos": 0.1, "neg": -0.1, "neutral": 0.0},
    "ma50": {"pos": 0.05, "neg": 0.0},
    "breadth": {"pos": 0.05, "neg": -0.05, "neutral": 0.0},
    "regime": {"downtrend": -0.2, "uptrend": 0.0},
}

UPTREND = {"label": "uptrend", "pct_vs_ma": 2.0}
DOWNTREND = {"label": "downtrend", "pct_vs_ma": -2.0}


def factors_with(rsi=None, volume=None, ma50=None, breadth=None):
    """Builds a factors list using real label text so FACTOR_DIMENSIONS'
    matchers pick each one up, the same way build_factors' output would."""
    result = []
    if rsi is not None:
        result.append({"label": "RSI 50", "lean": rsi})
    if volume is not None:
        result.append({"label": "Vol: 1.6x avg", "lean": volume})
    if ma50 is not None:
        result.append({"label": "Above 50d avg" if ma50 == "pos" else "Below 50d avg", "lean": ma50})
    if breadth is not None:
        label = {"pos": "Sector-wide dip", "neutral": "Sector-wide rally", "neg": "Stock-specific move"}[breadth]
        result.append({"label": label, "lean": breadth})
    return result


def test_no_factors_is_nothing_compelling(monkeypatch):
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal([], UPTREND)
    assert signal["label"] == "NOTHING COMPELLING"
    assert signal["class"] == "mixed"
    assert signal["icon"] == "◆"


def test_strong_positive_factor_leans_positive(monkeypatch):
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal(factors_with(rsi="pos"), UPTREND)
    assert signal["label"] == "LEANS POSITIVE"
    assert signal["class"] == "bullish"
    assert signal["icon"] == "▲"
    assert signal["score"] == 0.6  # intercept 0.1 + rsi_pos 0.5


def test_strong_negative_factor_leans_negative(monkeypatch):
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal(factors_with(rsi="neg"), UPTREND)
    assert signal["label"] == "LEANS NEGATIVE"
    assert signal["class"] == "bearish"
    assert signal["icon"] == "▼"
    assert signal["score"] == -0.4  # intercept 0.1 + rsi_neg -0.5


def test_baseline_only_factor_is_mixed_not_positive(monkeypatch):
    # ma50=neg is FIXTURE_WEIGHTS' dropped baseline (weight 0.0) — present
    # but contributes nothing beyond the intercept, so it shouldn't count
    # as "meaningfully above baseline".
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal(factors_with(ma50="neg"), UPTREND)
    assert signal["label"] == "MIXED SIGNALS"
    assert signal["class"] == "mixed"
    assert signal["icon"] == "⚠"


def test_weak_negative_factor_is_mixed_not_leans_negative(monkeypatch):
    # volume=neg (-0.1) isn't enough to push the score below zero
    # (0.1 - 0.1 = 0.0) — below baseline, but not an actual majority-down
    # call, so it should land on MIXED rather than being relabeled
    # LEANS NEGATIVE (that mislabeling was tried and rejected — see the
    # compute_weighted_signal docstring).
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal(factors_with(volume="neg"), UPTREND)
    assert signal["label"] == "MIXED SIGNALS"
    assert signal["score"] == 0.0


def test_regime_can_tip_a_mixed_case_into_leans_negative(monkeypatch):
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    factors = factors_with(volume="neg")  # score 0.0 under uptrend (MIXED, see above)

    uptrend_signal = monitor.compute_weighted_signal(factors, UPTREND)
    downtrend_signal = monitor.compute_weighted_signal(factors, DOWNTREND)

    assert uptrend_signal["label"] == "MIXED SIGNALS"
    assert downtrend_signal["label"] == "LEANS NEGATIVE"
    assert downtrend_signal["score"] == -0.2  # 0.0 + regime_downtrend -0.2


def test_multiple_factors_sum_additively(monkeypatch):
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal(
        factors_with(rsi="pos", volume="pos", ma50="pos", breadth="pos"), UPTREND
    )
    # intercept 0.1 + rsi_pos 0.5 + volume_pos 0.1 + ma50_pos 0.05 + breadth_pos 0.05
    assert signal["score"] == 0.8
    assert signal["label"] == "LEANS POSITIVE"


def test_unknown_regime_label_defaults_to_no_contribution(monkeypatch):
    monkeypatch.setattr(monitor, "WEIGHTED_FACTOR_WEIGHTS", FIXTURE_WEIGHTS)
    signal = monitor.compute_weighted_signal(factors_with(rsi="pos"), {"label": "sideways"})
    assert signal["score"] == 0.6  # unchanged from the uptrend case — unrecognized regime contributes 0.0
