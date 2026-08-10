"""RSI(14) tests — validated against an independent reference implementation
of the classic Wilder-seeded recursive smoothing (the standard RSI
definition used by most charting platforms), plus two deterministic edge
cases that don't need any reference implementation at all.
"""

import pandas as pd
import pytest

from monitor import compute_rsi

# A fixed, hand-inspectable 30-day closing-price series (not random) with a
# mix of up/down moves, long enough to comfortably clear the 14-period
# warm-up.
KNOWN_CLOSES = [
    100.00, 101.20, 100.80, 102.50, 103.10, 102.90, 104.30, 105.00, 104.50,
    103.80, 104.90, 106.10, 105.70, 107.00, 106.50, 105.90, 107.40, 108.20,
    107.80, 106.90, 108.50, 109.30, 108.90, 110.10, 109.60, 111.00, 110.40,
    112.20, 111.80, 113.50,
]


def reference_wilder_rsi(values, period=14):
    """A second, independently-written implementation of classic Wilder
    RSI (seed = simple average of the first `period` gains/losses, then
    recursive smoothing) — used to cross-validate compute_rsi()'s result
    rather than trusting a single memorized reference number."""
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    up_moves = [max(d, 0.0) for d in diffs]
    down_moves = [max(-d, 0.0) for d in diffs]

    mean_up = sum(up_moves[:period]) / period
    mean_down = sum(down_moves[:period]) / period
    idx = period
    while idx < len(diffs):
        mean_up = (mean_up * (period - 1) + up_moves[idx]) / period
        mean_down = (mean_down * (period - 1) + down_moves[idx]) / period
        idx += 1

    if mean_down == 0:
        return 100.0
    relative_strength = mean_up / mean_down
    return 100 - (100 / (1 + relative_strength))


def test_rsi_matches_independent_reference_implementation():
    closes = pd.Series(KNOWN_CLOSES)
    expected = reference_wilder_rsi(KNOWN_CLOSES)
    assert compute_rsi(closes) == pytest.approx(expected, abs=1e-9)


def test_rsi_matches_reference_on_a_shorter_warmup_window():
    # Exactly period+1 points is the minimum viable input.
    closes = pd.Series(KNOWN_CLOSES[:15])
    expected = reference_wilder_rsi(KNOWN_CLOSES[:15])
    assert compute_rsi(closes) == pytest.approx(expected, abs=1e-9)


def test_rsi_is_100_when_every_move_is_a_gain():
    closes = pd.Series([100 + i for i in range(20)])  # strictly increasing
    assert compute_rsi(closes) == pytest.approx(100.0)


def test_rsi_is_0_when_every_move_is_a_loss():
    closes = pd.Series([100 - i for i in range(20)])  # strictly decreasing
    assert compute_rsi(closes) == pytest.approx(0.0)


def test_rsi_is_none_with_insufficient_data():
    closes = pd.Series([100.0, 101.0, 99.5])  # far fewer than period+1
    assert compute_rsi(closes) is None


def test_rsi_stays_within_bounds_on_flat_prices():
    closes = pd.Series([100.0] * 20)  # no moves at all -> avg_loss == 0
    assert compute_rsi(closes) == pytest.approx(100.0)
