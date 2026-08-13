"""Move Maturity tests — the points-based Fresh/Extended/Overextended read
on whether a LEANS POSITIVE signal is catching a move early or arriving
after it's already mostly played out (compute_move_maturity), and the
signal-streak day-count it partly depends on (update_signal_streak).
"""

from monitor import (
    ACCURACY_RESOLUTION_DAYS,
    MOVE_MATURITY_STREAK_SOFT_DAYS,
    WEEKLY_DROP_PCT,
    compute_move_maturity,
    update_signal_streak,
)

# --- update_signal_streak ---------------------------------------------------


def test_first_ever_signal_starts_a_zero_day_streak():
    state = {}
    days = update_signal_streak(state, "bullish", "2026-08-10")
    assert days == 0
    assert state["signal_streak"] == {"class": "bullish", "since": "2026-08-10"}


def test_same_class_on_a_later_day_extends_the_streak():
    state = {"signal_streak": {"class": "bullish", "since": "2026-08-01"}}
    days = update_signal_streak(state, "bullish", "2026-08-10")
    assert days == 9
    assert state["signal_streak"]["since"] == "2026-08-01"  # unchanged — streak continues


def test_class_change_resets_the_streak_to_zero():
    state = {"signal_streak": {"class": "mixed", "since": "2026-07-01"}}
    days = update_signal_streak(state, "bullish", "2026-08-10")
    assert days == 0
    assert state["signal_streak"] == {"class": "bullish", "since": "2026-08-10"}


# --- compute_move_maturity: labeling -----------------------------------------


def test_quiet_fresh_flip_with_no_extension_signals():
    maturity = compute_move_maturity(
        weekly_pct=1.0, monthly_pct=2.0, pct_below_52wk_high=20.0,
        rsi=45, rsi_label_value="neutral", streak_days=0,
    )
    assert maturity["label"] == "Fresh"
    assert maturity["score"] == 0
    assert "just turned positive today" in maturity["sentence"]
    assert "not a prediction" in maturity["sentence"]


def test_flipped_yesterday_says_yesterday():
    maturity = compute_move_maturity(
        weekly_pct=0.5, monthly_pct=1.0, pct_below_52wk_high=30.0,
        rsi=50, rsi_label_value="neutral", streak_days=1,
    )
    assert maturity["label"] == "Fresh"
    assert "just turned positive yesterday" in maturity["sentence"]


def test_strong_weekly_move_and_near_high_is_extended():
    maturity = compute_move_maturity(
        weekly_pct=WEEKLY_DROP_PCT, monthly_pct=None, pct_below_52wk_high=1.5,
        rsi=60, rsi_label_value="neutral", streak_days=None,
    )
    assert maturity["score"] == 4  # 2 (weekly) + 2 (near high)
    assert maturity["label"] == "Extended"
    assert f"up {WEEKLY_DROP_PCT:.0f}% this week" in maturity["sentence"]
    assert "near its 52-week high" in maturity["sentence"]


def test_strong_weekly_near_high_and_overbought_is_overextended():
    maturity = compute_move_maturity(
        weekly_pct=WEEKLY_DROP_PCT + 4, monthly_pct=None, pct_below_52wk_high=0.0,
        rsi=78, rsi_label_value="overbought", streak_days=None,
    )
    assert maturity["score"] == 6  # 2 (weekly) + 2 (at new high) + 2 (overbought)
    assert maturity["label"] == "Overextended"
    assert "at a new 52-week high" in maturity["sentence"]
    assert "RSI overbought at 78" in maturity["sentence"]
    assert "well extended" in maturity["sentence"]


def test_overbought_number_only_counts_when_label_says_overbought():
    # A high raw RSI with a non-"overbought" label (shouldn't happen from
    # rsi_label() in practice, but the function should trust the label,
    # not re-derive it from the number) earns no RSI points.
    maturity = compute_move_maturity(
        weekly_pct=1.0, monthly_pct=1.0, pct_below_52wk_high=30.0,
        rsi=69, rsi_label_value="neutral", streak_days=0,
    )
    assert maturity["label"] == "Fresh"
    assert "RSI" not in maturity["sentence"]


def test_long_streak_alone_reaches_extended():
    maturity = compute_move_maturity(
        weekly_pct=None, monthly_pct=None, pct_below_52wk_high=None,
        rsi=None, rsi_label_value=None, streak_days=ACCURACY_RESOLUTION_DAYS,
    )
    assert maturity["score"] == 2
    assert maturity["label"] == "Extended"
    assert f"held positive for {ACCURACY_RESOLUTION_DAYS} days" in maturity["sentence"]


def test_soft_streak_is_worth_fewer_points_than_a_long_one():
    maturity = compute_move_maturity(
        weekly_pct=None, monthly_pct=None, pct_below_52wk_high=None,
        rsi=None, rsi_label_value=None, streak_days=MOVE_MATURITY_STREAK_SOFT_DAYS,
    )
    assert maturity["score"] == 1
    assert maturity["label"] == "Fresh"  # 1 point alone isn't enough to tip into Extended


def test_missing_data_is_skipped_not_treated_as_zero():
    # None inputs shouldn't crash or silently score as if the underlying
    # value were 0/absent-in-a-meaningful-way — they should just not
    # contribute to the score.
    maturity = compute_move_maturity(
        weekly_pct=None, monthly_pct=None, pct_below_52wk_high=None,
        rsi=None, rsi_label_value=None, streak_days=None,
    )
    assert maturity["score"] == 0
    assert maturity["label"] == "Fresh"


def test_sentence_always_states_this_is_not_a_prediction():
    fresh = compute_move_maturity(1, 1, 30, 40, "neutral", 0)
    extended = compute_move_maturity(WEEKLY_DROP_PCT, None, 1.0, 60, "neutral", None)
    for maturity in (fresh, extended):
        assert "not a prediction" in maturity["sentence"]
