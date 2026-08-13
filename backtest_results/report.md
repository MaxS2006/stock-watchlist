# Signal Backtest Report

Generated 2026-08-13T18:09:01

## Parameters

- Period: 2021-08-14 to 2026-08-13 (5 years)
- Universe: 104 tickers
- Resolution window: 7 calendar days (same as the live accuracy tracker)
- Small-sample threshold: n < 30
- Earnings factor: always neutral — see module docstring for why
- Signal logic: tally

**Two views throughout:** *daily* counts every day a ticker showed a directional signal, including consecutive days during one sustained trend. *episodes* counts only the first day of each such streak — a stricter, de-autocorrelated view. Daily signals aren't independent trials; if the two views disagree substantially, trust *episodes* more for judging whether the edge is real.

## Overall win rates

| | Daily | Episodes |
|---|---|---|
| LEANS POSITIVE (bullish) | 53.8% win rate (n=37076) | 53.7% win rate (n=12390) |
| LEANS NEGATIVE (bearish) | 45.8% win rate (n=13657) | 45.9% win rate (n=9042) |

A `correct` bearish signal means price fell over the following window; `correct` bullish means it rose. Flat moves are excluded from n, same as live.

## By factor (does a specific factor being present change the win rate?)

### LEANS POSITIVE

Overall (daily): 53.8% win rate (n=37076)
Overall (episodes): 53.7% win rate (n=12390)

| Factor | Reading | Daily | Episodes |
|---|---|---|---|
| rsi | pos | 59.9% win rate (n=1983) | 59.4% win rate (n=1165) |
| rsi | neg | 54.4% win rate (n=4500) | 53.6% win rate (n=1351) |
| rsi | neutral | 53.3% win rate (n=30593) | 53.0% win rate (n=9874) |
| volume | pos | 53.7% win rate (n=4984) | 53.2% win rate (n=2127) |
| volume | neg | 56.7% win rate (n=1056) | 50.2% win rate (n=243) |
| volume | neutral | 53.7% win rate (n=31036) | 53.9% win rate (n=10020) |
| ma50 | pos | 53.5% win rate (n=34266) | 53.1% win rate (n=10545) |
| ma50 | neg | 57.7% win rate (n=2810) | 57.2% win rate (n=1845) |
| breadth | pos | 53.8% win rate (n=35378) | 53.7% win rate (n=11870) |
| breadth | neutral | 54.3% win rate (n=1698) | 53.8% win rate (n=520) |

### LEANS NEGATIVE

Overall (daily): 45.8% win rate (n=13657)
Overall (episodes): 45.9% win rate (n=9042)

| Factor | Reading | Daily | Episodes |
|---|---|---|---|
| rsi | pos | 40.8% win rate (n=1326) | 41.4% win rate (n=669) |
| rsi | neg | 44.7% win rate (n=671) | 44.8% win rate (n=616) |
| rsi | neutral | 46.5% win rate (n=11660) | 46.4% win rate (n=7757) |
| volume | neg | 44.9% win rate (n=4874) | 45.2% win rate (n=3152) |
| volume | neutral | 46.3% win rate (n=8783) | 46.3% win rate (n=5890) |
| ma50 | pos | 45.0% win rate (n=1599) | 45.0% win rate (n=1472) |
| ma50 | neg | 45.9% win rate (n=12058) | 46.1% win rate (n=7570) |
| breadth | pos | 45.5% win rate (n=1340) | 45.4% win rate (n=735) |
| breadth | neg | 45.9% win rate (n=12317) | 46.0% win rate (n=8307) |

## Most common exact factor combinations (daily)

The specific set of non-neutral factors present, e.g. checking whether "LEANS POSITIVE + Above 50d avg" outperforms LEANS POSITIVE generally.

| Direction | Factors present | Win rate |
|---|---|---|
| bullish | Above 50d avg, Sector-wide dip | 52.8% win rate (n=18605) |
| bearish | Below 50d avg, Stock-specific move | 46.7% win rate (n=7522) |
| bullish | Above 50d avg, Stock-specific move | 53.9% win rate (n=7485) |
| bearish | Below 50d avg, High volume (against move), Stock-specific move | 46.8% win rate (n=1870) |
| bullish | Above 50d avg, RSI overbought, Stock-specific move | 53.8% win rate (n=1697) |
| bullish | Below 50d avg, RSI oversold, Sector-wide dip | 59.5% win rate (n=1618) |
| bullish | Above 50d avg, High volume (same direction), Stock-specific move | 53.7% win rate (n=1491) |
| bullish | Above 50d avg, RSI overbought, Sector-wide dip | 57.1% win rate (n=1467) |
| bearish | Below 50d avg, High volume (against move), Sector-wide dip | 45.5% win rate (n=1340) |
| bullish | Above 50d avg, High volume (same direction) | 54.7% win rate (n=1129) |
| bullish | Above 50d avg, High volume (against move), Sector-wide dip | 56.7% win rate (n=1056) |
| bearish | Above 50d avg, High volume (against move), Stock-specific move | 45.3% win rate (n=928) |
| bullish | Above 50d avg, High volume (same direction), RSI overbought, Stock-specific move | 52.7% win rate (n=894) |
| bullish | Below 50d avg, High volume (same direction), Stock-specific move | 52.5% win rate (n=827) |
| bearish | Below 50d avg, High volume (against move), RSI oversold, Stock-specific move | 38.6% win rate (n=674) |

## By market regime (does SPY's own trend explain the bearish edge?)

Regime is SPY price vs. its own 200-day MA on the signal date — "downtrend" below, "uptrend" at or above. Checks whether bearish's edge is really concentrated in confirmed downtrends rather than spread evenly across all conditions.

| Direction | Regime | Daily | Episodes |
|---|---|---|---|
| LEANS POSITIVE | downtrend | 55.6% win rate (n=7179) | 57.0% win rate (n=2218) |
| LEANS POSITIVE | uptrend | 53.3% win rate (n=29897) | 53.0% win rate (n=10172) |
| LEANS NEGATIVE | downtrend | 44.0% win rate (n=3294) | 44.4% win rate (n=2110) |
| LEANS NEGATIVE | uptrend | 46.4% win rate (n=10363) | 46.4% win rate (n=6932) |

## By year (is it consistent, or was it one good/bad stretch?)

| Year | Bullish (daily) | Bearish (daily) | Bullish (episodes) | Bearish (episodes) |
|---|---|---|---|---|
| 2021 | 54.5% win rate (n=2850) | 44.0% win rate (n=993) | 55.2% win rate (n=967) | 45.3% win rate (n=674) |
| 2022 | 49.9% win rate (n=7150) | 50.3% win rate (n=2735) | 49.6% win rate (n=2115) | 50.6% win rate (n=1778) |
| 2023 | 54.9% win rate (n=7265) | 44.7% win rate (n=2425) | 54.5% win rate (n=2659) | 44.5% win rate (n=1720) |
| 2024 | 55.1% win rate (n=8220) | 43.9% win rate (n=2370) | 54.9% win rate (n=2725) | 44.0% win rate (n=1638) |
| 2025 | 55.3% win rate (n=7436) | 43.9% win rate (n=2842) | 55.7% win rate (n=2407) | 43.8% win rate (n=1867) |
| 2026 | 52.9% win rate (n=4155) | 46.7% win rate (n=2292) | 51.7% win rate (n=1517) | 47.3% win rate (n=1365) |

## Notes

- This backtests the mechanical signal logic only (RSI, volume, 50-day MA, sector breadth) — never the Claude-written synthesis or news, which don't feed into the signal itself in the live system either.
- "Small sample" buckets (n < 30) are flagged, not hidden — read their win rates as noisy, not as evidence either way.
- Full per-signal data (every signal, every factor, every outcome) is in `results.json` alongside this report. The broader unbiased per-day dataset (`all_days.json`) that `fit_weights.py` trains on covers every trading day, not just days a signal fired.
