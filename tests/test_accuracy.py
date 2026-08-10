"""Signal accuracy-tracking tests — recording a directional signal and
later resolving it against actual price movement.
"""

from datetime import date, timedelta

import pytest

from monitor import (
    build_tracking_entry,
    resolve_due_entries,
    resolve_signal_outcome,
    summarize_accuracy,
    update_signal_history,
)

# --- resolve_signal_outcome: the core "did price move the way the signal
# implied" logic -------------------------------------------------------


def test_bullish_signal_correct_when_price_rises():
    assert resolve_signal_outcome("bullish", price_at_signal=100.0, price_now=105.0) is True


def test_bullish_signal_incorrect_when_price_falls():
    assert resolve_signal_outcome("bullish", price_at_signal=100.0, price_now=95.0) is False


def test_bearish_signal_correct_when_price_falls():
    assert resolve_signal_outcome("bearish", price_at_signal=100.0, price_now=95.0) is True


def test_bearish_signal_incorrect_when_price_rises():
    assert resolve_signal_outcome("bearish", price_at_signal=100.0, price_now=105.0) is False


def test_exactly_flat_price_is_unjudged():
    assert resolve_signal_outcome("bullish", price_at_signal=100.0, price_now=100.0) is None
    assert resolve_signal_outcome("bearish", price_at_signal=100.0, price_now=100.0) is None


def test_non_directional_signal_is_never_resolved():
    assert resolve_signal_outcome("mixed", price_at_signal=100.0, price_now=200.0) is None
    assert resolve_signal_outcome(None, price_at_signal=100.0, price_now=200.0) is None


def test_missing_prices_are_unjudged():
    assert resolve_signal_outcome("bullish", price_at_signal=None, price_now=105.0) is None
    assert resolve_signal_outcome("bullish", price_at_signal=100.0, price_now=None) is None
    assert resolve_signal_outcome("bullish", price_at_signal=0, price_now=105.0) is None


# --- build_tracking_entry: what gets recorded --------------------------


def test_bullish_signal_produces_a_tracking_entry():
    signal = {"class": "bullish"}
    entry = build_tracking_entry(signal, price=150.0, today_str="2026-01-01")
    assert entry == {
        "date": "2026-01-01",
        "direction": "bullish",
        "price_at_signal": 150.0,
        "resolve_on": "2026-01-08",  # +7 calendar days
        "resolved": False,
        "correct": None,
    }


def test_mixed_signal_produces_no_tracking_entry():
    assert build_tracking_entry({"class": "mixed"}, price=150.0, today_str="2026-01-01") is None


def test_missing_price_produces_no_tracking_entry():
    assert build_tracking_entry({"class": "bullish"}, price=None, today_str="2026-01-01") is None


# --- resolve_due_entries: pending -> resolved on schedule ---------------


def test_entry_resolves_once_its_date_arrives():
    pending = [{
        "date": "2026-01-01", "direction": "bullish", "price_at_signal": 100.0,
        "resolve_on": "2026-01-08", "resolved": False, "correct": None,
    }]
    resolved = resolve_due_entries(pending, current_price=110.0, today_str="2026-01-08")
    assert resolved[0]["resolved"] is True
    assert resolved[0]["correct"] is True
    assert resolved[0]["price_at_resolution"] == 110.0


def test_entry_not_yet_due_is_left_untouched():
    pending = [{
        "date": "2026-01-01", "direction": "bullish", "price_at_signal": 100.0,
        "resolve_on": "2026-01-08", "resolved": False, "correct": None,
    }]
    resolved = resolve_due_entries(pending, current_price=110.0, today_str="2026-01-05")
    assert resolved[0]["resolved"] is False
    assert resolved[0]["correct"] is None


def test_already_resolved_entry_is_not_touched_again():
    already_done = [{
        "date": "2026-01-01", "direction": "bullish", "price_at_signal": 100.0,
        "resolve_on": "2026-01-08", "resolved": True, "correct": False,
        "price_at_resolution": 90.0,
    }]
    # Even with a current_price that would flip the outcome, an already
    # resolved entry must never be re-judged.
    resolved = resolve_due_entries(already_done, current_price=999.0, today_str="2026-01-09")
    assert resolved[0]["correct"] is False
    assert resolved[0]["price_at_resolution"] == 90.0


def test_resolve_due_entries_does_not_mutate_input():
    pending = [{
        "date": "2026-01-01", "direction": "bullish", "price_at_signal": 100.0,
        "resolve_on": "2026-01-08", "resolved": False, "correct": None,
    }]
    resolve_due_entries(pending, current_price=110.0, today_str="2026-01-08")
    assert pending[0]["resolved"] is False  # original untouched


# --- update_signal_history: the per-run record+resolve cycle -----------


def test_new_directional_signal_gets_recorded():
    history = update_signal_history([], {"class": "bearish"}, price=50.0, today_str="2026-02-01")
    assert len(history) == 1
    assert history[0]["direction"] == "bearish"
    assert history[0]["resolved"] is False


def test_mixed_signal_is_not_recorded():
    history = update_signal_history([], {"class": "mixed"}, price=50.0, today_str="2026-02-01")
    assert history == []


def test_same_day_rerun_does_not_duplicate_entry():
    # monitor.py runs every ~15 minutes — only one entry per calendar day.
    history = update_signal_history([], {"class": "bullish"}, price=50.0, today_str="2026-02-01")
    history = update_signal_history(history, {"class": "bullish"}, price=51.0, today_str="2026-02-01")
    assert len(history) == 1


def test_next_day_run_adds_a_second_entry():
    history = update_signal_history([], {"class": "bullish"}, price=50.0, today_str="2026-02-01")
    history = update_signal_history(history, {"class": "bearish"}, price=52.0, today_str="2026-02-02")
    assert len(history) == 2
    assert [e["date"] for e in history] == ["2026-02-01", "2026-02-02"]


def test_history_length_is_capped():
    from monitor import MAX_SIGNAL_HISTORY

    history = []
    start = date(2026, 1, 1)
    for offset in range(MAX_SIGNAL_HISTORY + 20):
        today_str = (start + timedelta(days=offset)).isoformat()
        history = update_signal_history(history, {"class": "bullish"}, price=100.0, today_str=today_str)
    assert len(history) == MAX_SIGNAL_HISTORY


def test_full_cycle_record_then_resolve_a_week_later():
    history = update_signal_history([], {"class": "bullish"}, price=100.0, today_str="2026-03-01")
    assert history[0]["resolved"] is False

    # A week later, a fresh run both resolves the old entry and (since the
    # signal is still directional) records a new one for that day.
    history = update_signal_history(history, {"class": "bearish"}, price=108.0, today_str="2026-03-08")
    assert history[0]["resolved"] is True
    assert history[0]["correct"] is True  # bullish + price rose = correct
    assert len(history) == 2
    assert history[1]["direction"] == "bearish"
    assert history[1]["resolved"] is False


# --- summarize_accuracy --------------------------------------------------


def test_summary_with_no_resolved_entries():
    summary = summarize_accuracy([{
        "date": "2026-01-01", "direction": "bullish", "price_at_signal": 100.0,
        "resolve_on": "2026-01-08", "resolved": False, "correct": None,
    }])
    assert summary == {"resolved": 0, "correct": 0, "accuracy_pct": None}


def test_summary_counts_only_judged_outcomes():
    history = [
        {"resolved": True, "correct": True},
        {"resolved": True, "correct": False},
        {"resolved": True, "correct": True},
        {"resolved": True, "correct": None},  # flat move - not judged
        {"resolved": False, "correct": None},  # still pending
    ]
    summary = summarize_accuracy(history)
    assert summary == {"resolved": 3, "correct": 2, "accuracy_pct": pytest.approx(66.666, rel=1e-3)}
