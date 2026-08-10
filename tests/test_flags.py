"""Threshold-flagging tests — daily/weekly % drop detection.

compute_price_flags() is deliberately threshold-agnostic in its signature
(it reads the module-level DAILY_DROP_PCT / WEEKLY_DROP_PCT constants), so
these tests monkeypatch those constants to fixed values rather than relying
on whatever the repo currently has configured — keeps the tests correct
regardless of future threshold tuning.
"""

import monitor
from monitor import compute_price_flags


def test_daily_drop_at_or_beyond_threshold_flags(monkeypatch):
    monkeypatch.setattr(monitor, "DAILY_DROP_PCT", 5.0)
    monkeypatch.setattr(monitor, "WEEKLY_DROP_PCT", 8.0)
    daily_flag, weekly_flag = compute_price_flags(daily_pct=-5.0, weekly_pct=0.0)
    assert daily_flag is True
    assert weekly_flag is False


def test_daily_drop_just_short_of_threshold_does_not_flag(monkeypatch):
    monkeypatch.setattr(monitor, "DAILY_DROP_PCT", 5.0)
    monkeypatch.setattr(monitor, "WEEKLY_DROP_PCT", 8.0)
    daily_flag, _ = compute_price_flags(daily_pct=-4.99, weekly_pct=0.0)
    assert daily_flag is False


def test_weekly_drop_at_or_beyond_threshold_flags(monkeypatch):
    monkeypatch.setattr(monitor, "DAILY_DROP_PCT", 5.0)
    monkeypatch.setattr(monitor, "WEEKLY_DROP_PCT", 8.0)
    _, weekly_flag = compute_price_flags(daily_pct=0.0, weekly_pct=-8.5)
    assert weekly_flag is True


def test_gains_never_flag_regardless_of_magnitude(monkeypatch):
    monkeypatch.setattr(monitor, "DAILY_DROP_PCT", 5.0)
    monkeypatch.setattr(monitor, "WEEKLY_DROP_PCT", 8.0)
    daily_flag, weekly_flag = compute_price_flags(daily_pct=12.0, weekly_pct=20.0)
    assert daily_flag is False
    assert weekly_flag is False


def test_both_can_flag_simultaneously(monkeypatch):
    monkeypatch.setattr(monitor, "DAILY_DROP_PCT", 5.0)
    monkeypatch.setattr(monitor, "WEEKLY_DROP_PCT", 8.0)
    daily_flag, weekly_flag = compute_price_flags(daily_pct=-6.0, weekly_pct=-10.0)
    assert daily_flag is True
    assert weekly_flag is True


def test_missing_data_never_flags():
    daily_flag, weekly_flag = compute_price_flags(daily_pct=None, weekly_pct=None)
    assert daily_flag is False
    assert weekly_flag is False


def test_exactly_at_threshold_boundary_flags(monkeypatch):
    # <= threshold flags (not strictly <) — boundary behavior matters for
    # alert dedup logic downstream, so pin it explicitly.
    monkeypatch.setattr(monitor, "DAILY_DROP_PCT", 5.0)
    monkeypatch.setattr(monitor, "WEEKLY_DROP_PCT", 8.0)
    daily_flag, _ = compute_price_flags(daily_pct=-5.0, weekly_pct=0.0)
    assert daily_flag is True
