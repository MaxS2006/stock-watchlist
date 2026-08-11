#!/usr/bin/env python3
"""
Backtests the current signal logic against historical daily price data.

Replays the exact same technical-analysis functions monitor.py uses live —
compute_rsi, compute_volume_ratio, compute_ma50_pct, classify_breadth,
build_factors, compute_signal — day by day, using only data that would
have been available on that historical day, then checks each directional
signal (LEANS POSITIVE / LEANS NEGATIVE) against what price actually did
over the following ACCURACY_RESOLUTION_DAYS days, using the exact same
resolve_signal_outcome() the live accuracy tracker uses.

Lookahead-bias safeguard: every metric for a simulated day is computed from
a DataFrame slice truncated to that day's row index (closes.iloc[:i+1]) —
structurally impossible to see a future row, not just an intention. The
only place future data is touched is the resolution step afterward, which
is the entire point (checking what actually happened next).

Known limitation: the earnings-proximity factor is always treated as
neutral ("No earnings soon") here. yfinance's earnings-dates endpoint only
reflects earnings as currently known, not a point-in-time historical view —
there's no safe way to reconstruct "what earnings were upcoming as of
some past date" without risking exactly the lookahead bias this backtest
exists to avoid. So this tests 4 of the 5 live factors faithfully; earnings
proximity is excluded rather than faked.

Usage:
    python backtest.py
"""

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

import monitor  # reuse the exact live signal logic — not a re-derived copy

# --- Configuration -----------------------------------------------------------

BACKTEST_YEARS = int(os.environ.get("BACKTEST_YEARS", "5"))
WARMUP_CALENDAR_DAYS = 120  # buffer before the test window for 50d MA / RSI / volume-avg warmup
RESOLUTION_DAYS = monitor.ACCURACY_RESOLUTION_DAYS  # same window as the live accuracy tracker
MIN_SAMPLE_SIZE = 30  # below this, a bucket is flagged as too small to draw conclusions from
EPISODE_GAP_DAYS = 4  # consecutive same-ticker-same-direction signals within this many calendar days count as one streak

UNIVERSE_FILES = [
    os.environ.get("TICKERS_FILE", "tickers.txt"),
    os.environ.get("MOVERS_POOL_FILE", "movers_pool.txt"),
]

OUTPUT_DIR = os.environ.get("BACKTEST_OUTPUT_DIR", "backtest_results")
RESULTS_JSON = os.path.join(OUTPUT_DIR, "results.json")
REPORT_MD = os.path.join(OUTPUT_DIR, "report.md")

FACTOR_DIMENSIONS = {
    "rsi": lambda factors: next((f["lean"] for f in factors if f["label"].startswith("RSI ")), None),
    "volume": lambda factors: next((f["lean"] for f in factors if f["label"].startswith("Vol:")), None),
    "ma50": lambda factors: next((f["lean"] for f in factors if f["label"] in ("Above 50d avg", "Below 50d avg")), None),
    "breadth": lambda factors: next(
        (f["lean"] for f in factors if f["label"] in ("Sector-wide dip", "Sector-wide rally", "Stock-specific move")),
        None,
    ),
}


# --- Universe + data fetch ----------------------------------------------------


def load_universe():
    tickers = []
    seen = set()
    for path in UNIVERSE_FILES:
        if not os.path.exists(path):
            continue
        for t in monitor.load_tickers(path):
            if t not in seen:
                seen.add(t)
                tickers.append(t)
    return tickers


def fetch_universe_history(tickers, start, end):
    """One batched call for the whole universe. Returns {symbol: DataFrame}
    with a naive (timezone-stripped) Date index, tickers with too little
    data dropped rather than erroring the whole run."""
    print(f"Fetching {len(tickers)} tickers from {start} to {end} (one batched call)...")
    data = yf.download(
        tickers, start=start, end=end, interval="1d",
        group_by="ticker", threads=True, progress=False, auto_adjust=True,
    )
    single = len(tickers) == 1
    histories = {}
    for symbol in tickers:
        try:
            df = data if single else data[symbol]
            df = df.dropna(subset=["Close"])
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            if len(df) < MA_PERIOD_MIN_ROWS:
                continue
            histories[symbol] = df
        except Exception:
            continue
    print(f"Got usable history for {len(histories)}/{len(tickers)} tickers.")
    return histories


MA_PERIOD_MIN_ROWS = monitor.MA_PERIOD + monitor.RSI_PERIOD  # bare minimum to ever produce a signal


def compute_daily_breadth(histories):
    """{Timestamp date: avg_daily_pct across the universe on that date} —
    for the sector-breadth factor. Uses only that day's own returns."""
    pct_by_ticker = {symbol: df["Close"].pct_change() * 100 for symbol, df in histories.items()}
    combined = pd.DataFrame(pct_by_ticker)
    avg_daily_pct = combined.mean(axis=1, skipna=True)
    return avg_daily_pct


# --- Replay --------------------------------------------------------------------


def replay_ticker(symbol, df, avg_daily_pct_by_date, start_date, cutoff_date):
    """One directional-signal dict per trading day this ticker was
    LEANS POSITIVE/NEGATIVE, using only data up to and including that day."""
    closes = df["Close"]
    volumes = df["Volume"]
    dates = df.index

    signals = []
    for i in range(len(df)):
        current_date = dates[i].date()
        if current_date < start_date:
            continue
        if current_date > cutoff_date:
            break

        closes_so_far = closes.iloc[: i + 1]
        volumes_so_far = volumes.iloc[: i + 1]
        if len(closes_so_far) < 2:
            continue

        current_price, daily_pct, weekly_pct = monitor.compute_price_moves(closes_so_far)
        rsi = monitor.compute_rsi(closes_so_far)
        volume_ratio = monitor.compute_volume_ratio(volumes_so_far)
        ma50_pct = monitor.compute_ma50_pct(closes_so_far)
        avg_daily_pct = avg_daily_pct_by_date.get(dates[i])
        breadth = monitor.classify_breadth(daily_pct, avg_daily_pct)

        metrics = {
            "symbol": symbol,
            "price": current_price,
            "daily_pct": daily_pct,
            "weekly_pct": weekly_pct,
            "rsi": rsi,
            "rsi_label": monitor.rsi_label(rsi),
            "volume_ratio": volume_ratio,
            "ma50_pct": ma50_pct,
            "breadth": breadth,
            "earnings": {"flag": False, "text": "No earnings soon"},  # documented limitation, see module docstring
        }
        factors = monitor.build_factors(metrics)
        signal = monitor.compute_signal(factors)
        if signal["class"] not in ("bullish", "bearish"):
            continue

        signals.append({
            "symbol": symbol,
            "date": current_date.isoformat(),
            "direction": signal["class"],
            "signal_label": signal["label"],
            "price_at_signal": current_price,
            "factors": factors,
            "row_index": i,
        })

    return signals


def resolve_signals(df, signals):
    closes = df["Close"]
    date_list = [d.date() for d in df.index]

    resolved = []
    for sig in signals:
        signal_date = date.fromisoformat(sig["date"])
        target_date = signal_date + timedelta(days=RESOLUTION_DAYS)

        price_now = None
        for j in range(sig["row_index"] + 1, len(date_list)):
            if date_list[j] >= target_date:
                price_now = float(closes.iloc[j])
                break
        if price_now is None:
            continue  # not enough future data to resolve — excluded, not guessed

        outcome = monitor.resolve_signal_outcome(sig["direction"], sig["price_at_signal"], price_now)
        resolved_sig = dict(sig)
        del resolved_sig["row_index"]
        resolved_sig["price_at_resolution"] = price_now
        resolved_sig["correct"] = outcome
        resolved.append(resolved_sig)
    return resolved


# --- Aggregation ---------------------------------------------------------------


def summarize(signals):
    judged = [s for s in signals if s["correct"] is not None]
    n = len(judged)
    correct = sum(1 for s in judged if s["correct"])
    return {
        "n": n,
        "correct": correct,
        "win_rate_pct": round(correct / n * 100, 1) if n else None,
        "small_sample": n < MIN_SAMPLE_SIZE,
    }


def dedupe_episodes(signals):
    """First day of each consecutive same-ticker-same-direction streak.

    Daily signals aren't independent trials: a ticker sitting in
    LEANS POSITIVE for ten straight days during one sustained rally is one
    underlying event counted ten times, which can make results look more
    validated than they are. This is a stricter, de-autocorrelated view of
    the same signals, reported alongside the raw count rather than instead
    of it."""
    by_ticker = defaultdict(list)
    for s in signals:
        by_ticker[s["symbol"]].append(s)

    episodes = []
    for symbol, sigs in by_ticker.items():
        sigs_sorted = sorted(sigs, key=lambda s: s["date"])
        prev_date = None
        prev_direction = None
        for s in sigs_sorted:
            d = date.fromisoformat(s["date"])
            is_continuation = (
                prev_date is not None
                and s["direction"] == prev_direction
                and (d - prev_date).days <= EPISODE_GAP_DAYS
            )
            if not is_continuation:
                episodes.append(s)
            prev_date = d
            prev_direction = s["direction"]
    return episodes


def factor_breakdown(signals):
    breakdown = {}
    for direction in ("bullish", "bearish"):
        dir_signals = [s for s in signals if s["direction"] == direction]
        by_factor = {}
        for dim_name, extractor in FACTOR_DIMENSIONS.items():
            buckets = defaultdict(list)
            for s in dir_signals:
                lean = extractor(s["factors"])
                if lean is not None:
                    buckets[lean].append(s)
            by_factor[dim_name] = {lean: summarize(sigs) for lean, sigs in buckets.items()}
        breakdown[direction] = {"overall": summarize(dir_signals), "by_factor": by_factor}
    return breakdown


# RSI and volume factor labels embed exact numbers ("RSI 71", "Vol: 1.6x
# avg"), which would fragment the exact-combo breakdown into mostly-unique
# buckets. Collapse those two to their underlying category for this
# breakdown only — MA50 and breadth labels are already clean/discrete text
# with no embedded numbers, so they're used as-is.
def signature_label(f):
    if f["label"].startswith("RSI "):
        return {"pos": "RSI oversold", "neg": "RSI overbought"}.get(f["lean"])
    if f["label"].startswith("Vol:"):
        return {"pos": "High volume (same direction)", "neg": "High volume (against move)"}.get(f["lean"])
    return f["label"]


def exact_combo_breakdown(signals, top_n=15):
    buckets = defaultdict(list)
    for s in signals:
        parts = [signature_label(f) for f in s["factors"] if f["lean"] != "neutral"]
        signature = ", ".join(sorted(p for p in parts if p))
        buckets[(s["direction"], signature or "(no non-neutral factors)")].append(s)
    rows = []
    for (direction, signature), sigs in buckets.items():
        rows.append({"direction": direction, "signature": signature, **summarize(sigs)})
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows[:top_n]


def yearly_breakdown(signals):
    by_year = defaultdict(list)
    for s in signals:
        by_year[s["date"][:4]].append(s)
    return {
        year: {
            "bullish": summarize([s for s in sigs if s["direction"] == "bullish"]),
            "bearish": summarize([s for s in sigs if s["direction"] == "bearish"]),
        }
        for year, sigs in sorted(by_year.items())
    }


def build_report(signals, universe_size, universe, start_date, end_date):
    episodes = dedupe_episodes(signals)
    return {
        "params": {
            "years": BACKTEST_YEARS,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "resolution_days": RESOLUTION_DAYS,
            "min_sample_size": MIN_SAMPLE_SIZE,
            "universe_size": universe_size,
            "universe": sorted(universe),
            "earnings_factor": "always neutral — see module docstring for why",
        },
        "overall": {
            "bullish_daily": summarize([s for s in signals if s["direction"] == "bullish"]),
            "bearish_daily": summarize([s for s in signals if s["direction"] == "bearish"]),
            "bullish_episodes": summarize([s for s in episodes if s["direction"] == "bullish"]),
            "bearish_episodes": summarize([s for s in episodes if s["direction"] == "bearish"]),
        },
        "by_factor_daily": factor_breakdown(signals),
        "by_factor_episodes": factor_breakdown(episodes),
        "top_exact_combos_daily": exact_combo_breakdown(signals),
        "by_year_daily": yearly_breakdown(signals),
        "by_year_episodes": yearly_breakdown(episodes),
    }


# --- Output ----------------------------------------------------------------------


def fmt_summary(s):
    if s["n"] == 0:
        return "n=0 (no resolved signals)"
    flag = " ⚠ SMALL SAMPLE" if s["small_sample"] else ""
    return f"{s['win_rate_pct']}% win rate (n={s['n']}){flag}"


def render_markdown(report, all_signals):
    p = report["params"]
    lines = [
        "# Signal Backtest Report",
        "",
        f"Generated {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Parameters",
        "",
        f"- Period: {p['start_date']} to {p['end_date']} ({p['years']} years)",
        f"- Universe: {p['universe_size']} tickers",
        f"- Resolution window: {p['resolution_days']} calendar days (same as the live accuracy tracker)",
        f"- Small-sample threshold: n < {p['min_sample_size']}",
        f"- Earnings factor: {p['earnings_factor']}",
        "",
        "**Two views throughout:** *daily* counts every day a ticker showed a directional "
        "signal, including consecutive days during one sustained trend. *episodes* counts only "
        "the first day of each such streak — a stricter, de-autocorrelated view. Daily signals "
        "aren't independent trials; if the two views disagree substantially, trust *episodes* "
        "more for judging whether the edge is real.",
        "",
        "## Overall win rates",
        "",
        "| | Daily | Episodes |",
        "|---|---|---|",
        f"| LEANS POSITIVE (bullish) | {fmt_summary(report['overall']['bullish_daily'])} | {fmt_summary(report['overall']['bullish_episodes'])} |",
        f"| LEANS NEGATIVE (bearish) | {fmt_summary(report['overall']['bearish_daily'])} | {fmt_summary(report['overall']['bearish_episodes'])} |",
        "",
        "A `correct` bearish signal means price fell over the following window; `correct` "
        "bullish means it rose. Flat moves are excluded from n, same as live.",
        "",
        "## By factor (does a specific factor being present change the win rate?)",
        "",
    ]

    for direction in ("bullish", "bearish"):
        label = "LEANS POSITIVE" if direction == "bullish" else "LEANS NEGATIVE"
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"Overall (daily): {fmt_summary(report['by_factor_daily'][direction]['overall'])}")
        lines.append(f"Overall (episodes): {fmt_summary(report['by_factor_episodes'][direction]['overall'])}")
        lines.append("")
        lines.append("| Factor | Reading | Daily | Episodes |")
        lines.append("|---|---|---|---|")
        daily_bf = report["by_factor_daily"][direction]["by_factor"]
        ep_bf = report["by_factor_episodes"][direction]["by_factor"]
        for dim in FACTOR_DIMENSIONS:
            for lean in ("pos", "neg", "neutral"):
                d_summary = daily_bf.get(dim, {}).get(lean)
                e_summary = ep_bf.get(dim, {}).get(lean)
                if not d_summary:
                    continue
                lines.append(f"| {dim} | {lean} | {fmt_summary(d_summary)} | {fmt_summary(e_summary) if e_summary else 'n=0'} |")
        lines.append("")

    lines.append("## Most common exact factor combinations (daily)")
    lines.append("")
    lines.append("The specific set of non-neutral factors present, e.g. checking whether "
                  "\"LEANS POSITIVE + Above 50d avg\" outperforms LEANS POSITIVE generally.")
    lines.append("")
    lines.append("| Direction | Factors present | Win rate |")
    lines.append("|---|---|---|")
    for row in report["top_exact_combos_daily"]:
        lines.append(f"| {row['direction']} | {row['signature']} | {fmt_summary(row)} |")
    lines.append("")

    lines.append("## By year (is it consistent, or was it one good/bad stretch?)")
    lines.append("")
    lines.append("| Year | Bullish (daily) | Bearish (daily) | Bullish (episodes) | Bearish (episodes) |")
    lines.append("|---|---|---|---|---|")
    by_year_ep = report["by_year_episodes"]
    for year, row in report["by_year_daily"].items():
        ep_row = by_year_ep.get(year, {"bullish": {"n": 0}, "bearish": {"n": 0}})
        lines.append(
            f"| {year} | {fmt_summary(row['bullish'])} | {fmt_summary(row['bearish'])} "
            f"| {fmt_summary(ep_row['bullish'])} | {fmt_summary(ep_row['bearish'])} |"
        )
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- This backtests the mechanical signal logic only (RSI, volume, 50-day MA, sector "
        "breadth) — never the Claude-written synthesis or news, which don't feed into the "
        "signal itself in the live system either."
    )
    lines.append(
        "- \"Small sample\" buckets (n < {}) are flagged, not hidden — read their win rates as "
        "noisy, not as evidence either way.".format(p["min_sample_size"])
    )
    lines.append(
        "- Full per-signal data (every signal, every factor, every outcome) is in "
        "`results.json` alongside this report."
    )
    lines.append("")

    return "\n".join(lines)


def save_outputs(report, all_signals):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump({"report": report, "signals": all_signals}, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(REPORT_MD, "w") as f:
        f.write(render_markdown(report, all_signals))
    print(f"\nWrote {RESULTS_JSON}")
    print(f"Wrote {REPORT_MD}")


# --- Main --------------------------------------------------------------------


def main():
    end_date = date.today()
    start_date = end_date - timedelta(days=BACKTEST_YEARS * 365)
    fetch_start = start_date - timedelta(days=WARMUP_CALENDAR_DAYS)
    cutoff_date = end_date - timedelta(days=RESOLUTION_DAYS + 5)  # leave room to resolve every generated signal

    universe = load_universe()
    if not universe:
        print("No tickers found in tickers.txt / movers_pool.txt.", file=sys.stderr)
        sys.exit(1)

    histories = fetch_universe_history(universe, fetch_start.isoformat(), end_date.isoformat())
    if not histories:
        print("No usable price history fetched.", file=sys.stderr)
        sys.exit(1)

    avg_daily_pct_by_date = compute_daily_breadth(histories)

    all_signals = []
    for symbol, df in sorted(histories.items()):
        raw = replay_ticker(symbol, df, avg_daily_pct_by_date, start_date, cutoff_date)
        resolved = resolve_signals(df, raw)
        all_signals.extend(resolved)
        print(f"  {symbol}: {len(raw)} signals, {len(resolved)} resolved")

    print(f"\nTotal resolved signals: {len(all_signals)}")

    report = build_report(all_signals, len(histories), histories.keys(), start_date, end_date)
    save_outputs(report, all_signals)


if __name__ == "__main__":
    main()
