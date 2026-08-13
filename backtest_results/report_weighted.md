# Signal Backtest Report

Generated 2026-08-13T18:18:39

> **Experimental weighted/regime-gated signal.** This report replays `compute_weighted_signal` — weights fit via logistic regression on this same historical window (see `fit_weights.py`) — instead of the live tally logic. That means it's an **in-sample** result: fitting and testing on the same data is expected to look good almost by construction. Treat this as a sanity check, not validation — real validation is walk-forward testing (fit on earlier data, test on strictly later data), not yet done.

## Parameters

- Period: 2021-08-14 to 2026-08-13 (5 years)
- Universe: 104 tickers
- Resolution window: 7 calendar days (same as the live accuracy tracker)
- Small-sample threshold: n < 30
- Earnings factor: always neutral — see module docstring for why
- Signal logic: weighted

**Two views throughout:** *daily* counts every day a ticker showed a directional signal, including consecutive days during one sustained trend. *episodes* counts only the first day of each such streak — a stricter, de-autocorrelated view. Daily signals aren't independent trials; if the two views disagree substantially, trust *episodes* more for judging whether the edge is real.

## Overall win rates

| | Daily | Episodes |
|---|---|---|
| LEANS POSITIVE (bullish) | 53.6% win rate (n=88986) | 52.8% win rate (n=8510) |
| LEANS NEGATIVE (bearish) | n=0 (no resolved signals) | n=0 (no resolved signals) |

A `correct` bearish signal means price fell over the following window; `correct` bullish means it rose. Flat moves are excluded from n, same as live.

## By factor (does a specific factor being present change the win rate?)

### LEANS POSITIVE

Overall (daily): 53.6% win rate (n=88986)
Overall (episodes): 52.8% win rate (n=8510)

| Factor | Reading | Daily | Episodes |
|---|---|---|---|
| rsi | pos | 60.2% win rate (n=4243) | 52.6% win rate (n=19) ⚠ SMALL SAMPLE |
| rsi | neg | 53.9% win rate (n=10195) | 54.7% win rate (n=603) |
| rsi | neutral | 53.2% win rate (n=74548) | 52.7% win rate (n=7888) |
| volume | pos | 53.2% win rate (n=4861) | 51.3% win rate (n=347) |
| volume | neg | 55.9% win rate (n=6515) | 50.5% win rate (n=424) |
| volume | neutral | 53.5% win rate (n=77610) | 53.0% win rate (n=7739) |
| ma50 | pos | 53.1% win rate (n=44635) | 53.3% win rate (n=5719) |
| ma50 | neg | 54.2% win rate (n=44351) | 51.8% win rate (n=2791) |
| breadth | pos | 53.7% win rate (n=60310) | 52.5% win rate (n=7194) |
| breadth | neg | 53.8% win rate (n=13175) | 54.1% win rate (n=907) |
| breadth | neutral | 53.3% win rate (n=15501) | 55.7% win rate (n=409) |

### LEANS NEGATIVE

Overall (daily): n=0 (no resolved signals)
Overall (episodes): n=0 (no resolved signals)

| Factor | Reading | Daily | Episodes |
|---|---|---|---|

## Most common exact factor combinations (daily)

The specific set of non-neutral factors present, e.g. checking whether "LEANS POSITIVE + Above 50d avg" outperforms LEANS POSITIVE generally.

| Direction | Factors present | Win rate |
|---|---|---|
| bullish | Above 50d avg, Sector-wide dip | 52.8% win rate (n=18605) |
| bullish | Below 50d avg, Sector-wide dip | 52.7% win rate (n=17873) |
| bullish | Below 50d avg, Stock-specific move | 54.2% win rate (n=12656) |
| bullish | Above 50d avg, Stock-specific move | 53.4% win rate (n=8343) |
| bullish | Above 50d avg, RSI overbought | 53.3% win rate (n=4887) |
| bullish | Below 50d avg | 55.1% win rate (n=4661) |
| bullish | Above 50d avg | 50.3% win rate (n=3892) |
| bullish | Above 50d avg, RSI overbought, Stock-specific move | 54.0% win rate (n=2306) |
| bullish | Below 50d avg, High volume (against move), Stock-specific move | 53.2% win rate (n=1870) |
| bullish | Below 50d avg, RSI oversold, Sector-wide dip | 59.5% win rate (n=1618) |
| bullish | Above 50d avg, High volume (same direction), Stock-specific move | 53.7% win rate (n=1491) |
| bullish | Above 50d avg, RSI overbought, Sector-wide dip | 57.1% win rate (n=1467) |
| bullish | Below 50d avg, High volume (against move), Sector-wide dip | 54.5% win rate (n=1340) |
| bullish | Above 50d avg, High volume (against move), Sector-wide dip | 56.7% win rate (n=1056) |
| bullish | Above 50d avg, High volume (against move), Stock-specific move | 54.7% win rate (n=928) |

## By market regime (does SPY's own trend explain the bearish edge?)

Regime is SPY price vs. its own 200-day MA on the signal date — "downtrend" below, "uptrend" at or above. Checks whether bearish's edge is really concentrated in confirmed downtrends rather than spread evenly across all conditions.

| Direction | Regime | Daily | Episodes |
|---|---|---|---|
| LEANS POSITIVE | downtrend | 55.2% win rate (n=28475) | 56.8% win rate (n=132) |
| LEANS POSITIVE | uptrend | 52.9% win rate (n=60511) | 52.8% win rate (n=8378) |

## By year (is it consistent, or was it one good/bad stretch?)

| Year | Bullish (daily) | Bearish (daily) | Bullish (episodes) | Bearish (episodes) |
|---|---|---|---|---|
| 2021 | 55.0% win rate (n=5972) | n=0 (no resolved signals) | 54.4% win rate (n=778) | n=0 (no resolved signals) |
| 2022 | 50.2% win rate (n=24145) | n=0 (no resolved signals) | 34.7% win rate (n=363) | n=0 (no resolved signals) |
| 2023 | 55.5% win rate (n=15838) | n=0 (no resolved signals) | 54.3% win rate (n=2373) | n=0 (no resolved signals) |
| 2024 | 55.2% win rate (n=15795) | n=0 (no resolved signals) | 54.4% win rate (n=2228) | n=0 (no resolved signals) |
| 2025 | 55.5% win rate (n=17120) | n=0 (no resolved signals) | 54.0% win rate (n=1741) | n=0 (no resolved signals) |
| 2026 | 52.6% win rate (n=10116) | n=0 (no resolved signals) | 49.2% win rate (n=1027) | n=0 (no resolved signals) |

## Notes

- This backtests the mechanical signal logic only (RSI, volume, 50-day MA, sector breadth) — never the Claude-written synthesis or news, which don't feed into the signal itself in the live system either.
- "Small sample" buckets (n < 30) are flagged, not hidden — read their win rates as noisy, not as evidence either way.
- Full per-signal data (every signal, every factor, every outcome) is in `results.json` alongside this report. The broader unbiased per-day dataset (`all_days.json`) that `fit_weights.py` trains on covers every trading day, not just days a signal fired.
