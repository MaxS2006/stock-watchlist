# Stock Watchlist Monitor

A self-updating stock watchlist that runs entirely on free infrastructure — no server, no database, no hosting bill. A scheduled script checks your stocks every ~15 minutes during market hours, runs some real technical analysis on them, asks Claude to synthesize a plain-English read, and publishes the result to a live dashboard. It emails you only when something actually crosses a threshold — never a constant stream of noise. It never places a trade.

[![Tests](https://github.com/MaxS2006/stock-watchlist/actions/workflows/tests.yml/badge.svg)](https://github.com/MaxS2006/stock-watchlist/actions/workflows/tests.yml)
[![Stock Watchlist Monitor](https://github.com/MaxS2006/stock-watchlist/actions/workflows/watchlist.yml/badge.svg)](https://github.com/MaxS2006/stock-watchlist/actions/workflows/watchlist.yml)

**[→ View the live dashboard](https://maxs2006.github.io/stock-watchlist/)**

> **Not financial advice.** This is a personal informational project. It never executes a trade, and nothing it displays is a recommendation to buy or sell anything — see [Disclaimer](#disclaimer).

---

## What it does

Point it at a list of tickers and it will, on its own, every ~15 minutes during US market hours:

- Pull current price history from Yahoo Finance and recent company news from Finnhub
- Compute real technical indicators — RSI(14), volume vs. its own average, position relative to the 50-day moving average, and whether a move looks stock-specific or sector-wide
- Tally those into a plain signal (`LEANS POSITIVE`, `LEANS NEGATIVE`, `MIXED SIGNALS`, `NOTHING COMPELLING`) — deliberately never buy/sell language
- Ask Claude to write a one-line synthesis combining the technicals with the news, but *only* when something actually changed since the last check (keeps API cost negligible)
- Track its own track record: every directional call gets checked against what the price actually did about a week later
- Update a live dashboard, and send an email **only** if a stock crosses a drop threshold or has notable news — not on every run

It also scans a wider pool of ~80 large-cap tickers for notable movers, and shows a compact market-context strip (S&P 500, Nasdaq, Dow, and four sector ETFs) — both clearly separated from the core watchlist so they never get confused with an actual tracked signal.

## Architecture

```mermaid
flowchart TD
    A["GitHub Actions cron<br/>~every 15 min, market hours"] --> B["monitor.py"]

    B --> C["Yahoo Finance<br/>(yfinance)"]
    B --> D["Finnhub<br/>(company news)"]

    C --> E["Technical analysis<br/>RSI · volume · 50-day MA · sector breadth"]
    E --> F["Signal scoring<br/>bullish / bearish / mixed tally"]
    D --> F

    F --> G["Claude API (Haiku)<br/>1-line plain-English synthesis"]
    D --> G

    F --> H["Accuracy tracker<br/>resolves past signals vs. real price, ~7 days later"]

    E --> I["docs/data.json"]
    F --> I
    G --> I
    H --> I

    E --> J["Email alert<br/>iCloud SMTP — only if flagged"]
    D --> J

    I --> K["GitHub Pages<br/>static dashboard"]
    K --> L["Live in your browser"]
```

Everything runs inside a single scheduled GitHub Actions job — there's no backend to host or pay for. `monitor.py` does the work and writes `docs/data.json`; `docs/index.html` is a static page with no build step that fetches that JSON client-side and renders it (candlestick charts, signal bars, tooltips, the works). A second, independent GitHub Actions workflow runs the test suite on every push, regardless of the schedule.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Price data | [Yahoo Finance](https://finance.yahoo.com) via `yfinance` (free, no key) |
| News data | [Finnhub](https://finnhub.io) API (free tier) |
| AI synthesis | [Claude API](https://www.anthropic.com) (Haiku) |
| Technical analysis | `pandas` (Wilder-smoothed RSI, moving averages, breadth classification) |
| Testing | `pytest` — fixture-based, zero network calls |
| Automation | GitHub Actions (scheduled monitor run + CI on push) |
| Hosting | GitHub Pages (static, free) |
| Dashboard | Vanilla HTML/CSS/JS, no framework, no build step |
| Charts | [lightweight-charts](https://github.com/tradingview/lightweight-charts) (TradingView's open-source library) |
| Alerts | Email via iCloud SMTP |

## Engineering notes

A few things about how this was actually built, not just what it does:

**The test suite caught a real bug.** Writing a "known dataset" test for the RSI calculation — cross-validating it against an independently-written reference implementation of the classic Wilder-smoothed formula — surfaced that the production code was actually using pandas' default `.ewm(...).mean()` weighting instead. That's a different, non-standard formula that diverged from the values TradingView or StockCharts would show by a meaningful margin on real price data. Fixed, and verified: I reverted the fix, watched the test fail against the buggy version, then restored it — confirming the test suite actually has teeth, not just passing vacuously.

**GitHub Actions' cron scheduler needed a workaround.** The scheduled workflow ran fine manually but never fired on its own schedule — every run in the history was `workflow_dispatch`, none `schedule`, across multiple full trading days. After ruling out the usual culprits (invalid YAML, a fork, a disabled workflow, a platform incident), the fix was GitHub's own documented behavior: scheduled runs are most likely to be delayed or dropped right at the top of the hour, which is exactly where the original cron (`*/15 13-21 * * 1-5`) landed every time. Offsetting it by a few minutes (`7,22,37,52 13-21 * * 1-5`) fixed it — confirmed by watching real scheduled runs start appearing in the Actions history afterward.

**Signals are checked against reality, not just displayed and forgotten.** Every `LEANS POSITIVE` / `LEANS NEGATIVE` call gets recorded with the price at signal time, then automatically resolved about a week later against what the price actually did — `correct: true/false`, or `null` if the move was flat. It's intentionally scoped down to just this: no dashboard UI for it yet, just the tracked data in `state.json`/`docs/data.json`, ready for a future accuracy view once enough history accumulates.

**API usage is deliberately cheap.** The only paid dependency (Claude) is called per-ticker only when something changed since the last check — new news, an RSI category flip, or a threshold crossed — not on every 15-minute tick. The wider market scans (Notable Movers, Market Overview) use a single batched Yahoo Finance call rather than one request per ticker, so scanning ~90 extra tickers alongside the core watchlist adds a few seconds to the run, not minutes.

**The GitHub Contents API doesn't reliably support CORS — a real API limitation found by testing, not assumed.** The dashboard's editable watchlist first called the Contents API directly (`GET`+`PUT /repos/{owner}/{repo}/contents/tickers.txt`) from client-side JS to read and commit changes. In testing, that endpoint intermittently failed with a browser CORS error, while other API endpoints on the same domain — `/rate_limit`, `/repos/{owner}/{repo}`, `/repos/{owner}/{repo}/actions/...` — worked reliably, across two unrelated repos. GitHub's own docs confirm the Contents endpoint is one of the ones it "may proactively restrict… from browser-based requests." The fix: reads go through `raw.githubusercontent.com` (a different, CORS-reliable service), and writes dispatch a `repository_dispatch` event (confirmed CORS-reliable) that a dedicated workflow picks up to actually edit the file server-side — the same commit pattern the scheduled monitor already uses.

## The dashboard

Each watchlist card shows price, day/week % change, a real interactive candlestick chart, RSI with an Oversold/Overbought/Neutral read, volume vs. its 20-day average, position vs. the 50-day moving average, sector-wide vs. stock-specific classification, earnings-date proximity, the Claude-written synthesis, and the signal bar — every technical term has a hover/tap tooltip explaining it in plain English, aimed at someone with no trading background. A light/dark theme toggle and three accent colors are available, but the green/red up-down colors never change — the one thing that has to stay unambiguous, always does. A dashed, muted "EXPERIMENTAL" badge beneath the main signal bar shows the [weighted signal](#weighted-signal-experimental) as a second opinion — deliberately styled to never compete with the primary signal. An amber "🎯 OVERSOLD BOUNCE SETUP" badge appears near the ticker when the exact combination the backtest found strongest — below 50-day average, RSI oversold, and a sector-wide dip, all at once — is present; its tooltip states the 59.5% backtested win rate (n=1,618) plainly as a historical result, not a live prediction.

Every `LEANS POSITIVE` card also gets a **Move Maturity** read directly under the signal bar — a full plain-English sentence, not a badge you have to interpret, on whether the signal looks like it's catching a move early ("Fresh") or arriving after it's already largely played out ("Extended" / "Overextended"). It's a points-based read on how far price has already run (1-day/1-week/1-month % change, distance from the 52-week high, RSI overbought specifically *combined with* a bullish signal, and how many days the signal itself has held positive), scored against thresholds that reuse numbers already meaningful elsewhere in this codebase (`WEEKLY_DROP_PCT` mirrored for gains, `ACCURACY_RESOLUTION_DAYS` for "how long has this held") rather than arbitrary cutoffs — see `compute_move_maturity` in `monitor.py`. Every sentence ends by stating plainly that it's a read on historical positioning, not a prediction of what happens next.

A **Manage Watchlist** panel lets you add or remove tickers straight from the dashboard — no editing `tickers.txt` by hand. Adding/removing triggers [`watchlist-edit.yml`](.github/workflows/watchlist-edit.yml) via the GitHub API, which commits the change for you; a newly added ticker gets full price/RSI/signal analysis after the next scheduled run. This needs a GitHub personal access token with permission to trigger a workflow on the repo — the dashboard prompts for it only when you use the feature, and it's kept, at most, in that browser tab's session storage. It is never written into the page's shipped code, so nothing is there for a random visitor to the public dashboard to extract.

## Tests

```bash
pip install -r requirements-test.txt
pytest -v
```

64 tests, fixture data only, no network calls or API keys — they run in under a second and pass identically on a laptop or in CI. Covers RSI calculation, the daily/weekly drop-threshold flagging, the signal-scoring tally, the weighted signal's scoring/labeling, Move Maturity's scoring/labeling, and the accuracy-tracking resolution logic. `.github/workflows/tests.yml` runs this on every push, independent of the scheduled monitor workflow, so a logic regression fails a check before it ever reaches the live dashboard.

## Backtesting

```bash
python backtest.py
```

Replays the exact same signal logic monitor.py uses live (`build_factors`/`compute_signal` — literally imported and called, not a re-derived copy) against 5 years of daily history for ~100 tickers (`tickers.txt` + `movers_pool.txt`, one batched `yfinance` call), day by day, using only data that would have been available on that historical day. Each directional signal is checked against what price actually did over the following 7 days (same window and resolution function the live accuracy tracker uses), and the results are broken down by factor, by exact factor combination, and by calendar year — so a strategy that only worked during one bull run shows up as such rather than blending into an overall average.

Two views are reported throughout: every day a ticker showed a signal ("daily"), and only the first day of each consecutive same-direction streak ("episodes") — a stricter, de-autocorrelated view, since ten straight days of one sustained trend aren't ten independent trials. Any bucket with fewer than 30 resolved signals is flagged as too small to draw conclusions from, not silently included.

Known limitation: the earnings-proximity factor is always treated as neutral here. yfinance's earnings-dates endpoint only reflects earnings as currently known, not a point-in-time historical view, so there's no safe way to reconstruct "what earnings were upcoming as of some past date" without risking the exact lookahead bias this exists to avoid — so this tests 4 of the 5 live factors faithfully, and excludes the fifth rather than faking it.

Results go to [`backtest_results/report.md`](backtest_results/report.md) (human-readable summary, committed) and `backtest_results/results.json` / `all_days.json` (every signal/day, factor, and outcome — tens of MB, gitignored rather than committed). Tune via env vars: `BACKTEST_YEARS` (default `5`), `BACKTEST_OUTPUT_DIR`.

## Weighted signal (experimental)

The backtest above showed the live tally logic has a real but uneven edge: `LEANS POSITIVE` is concentrated in specific states (RSI oversold alone: ~60% win rate) rather than spread evenly across the ~45% of bullish calls that make up its largest bucket, and `LEANS NEGATIVE` is unreliable overall (46% — worse than a coin flip). Rather than guess at a fix, the dashboard now also runs a second, clearly-labeled **experimental** signal alongside the live one, built directly from that backtest data:

- **Weights are fit, not hand-picked.** [`fit_weights.py`](fit_weights.py) runs a small logistic regression (hand-rolled Newton-Raphson, `numpy` only — no new dependency) over `backtest_results/all_days.json`, predicting whether price rose over the following week from that day's factor readings. Critically, this trains on *every* trading day in the 5-year backtest, not just the days the live tally already called directional — training only on tally-flagged days would bake the tally's own selection bias into the new weights. The fitted coefficients are pasted into `monitor.py` as a plain constant (`WEIGHTED_FACTOR_WEIGHTS`), regenerated by hand whenever the analysis is redone — nothing is loaded at runtime.
- **Market regime is a fitted input, not a hardcoded rule.** The original plan was to gate `LEANS NEGATIVE` behind a "SPY is in a confirmed downtrend" check (added as `compute_spy_regime`, SPY vs. its own 200-day MA). Backtesting that rule directly showed the opposite of what was assumed: bearish signals were *less* reliable, not more, when SPY itself was trending down — likely because real downtrends are choppy and produce the oversold bounces that already hurt bearish calls the most. Regime is instead included as just another weighted dimension, so its real, non-obvious effect gets sized by the regression.
- **`LEANS NEGATIVE` is honestly rare.** With the fitted weights, no combination of the four factors produces a net negative score — every weight is positive except `ma50`'s (-0.0134), and the intercept alone (+0.0856, the sample's base rate of price rising over the window) already clears it. This isn't a bug: it's the same thing the backtest already showed (`LEANS NEGATIVE`'s raw win rate was under 46%) confirmed from a different angle. Within this factor set, there's no real recipe for betting on a decline.
- **The label is relative to baseline, not absolute.** Since every day's score is technically positive, thresholding at zero would make this an always-on classifier (it was, briefly, during development — 99.9% `LEANS POSITIVE`, discriminating nothing). Instead, `LEANS POSITIVE` requires a score *meaningfully above* the intercept (what's actually distinctive about that day); at-or-below-baseline days fall to `MIXED SIGNALS` instead of being relabeled `LEANS NEGATIVE` — `MIXED SIGNALS` asserts no direction, so nothing is overstated in either direction.

To compare the two approaches on the same historical window, run `SIGNAL_LOGIC=weighted python backtest.py` — it produces `backtest_results/report_weighted.md` alongside the original `report.md`. That comparison is **in-sample** (fit and tested on the same data), which is expected to look decent almost by construction — it's a sanity check, not validation. Real validation is walk-forward testing (fit on earlier data, test on strictly later, unseen data), which hasn't been done yet and is the planned next step before this could ever become the primary signal.

## Repo structure

```
.
├── monitor.py                 # the scheduled script: fetch, analyze, synthesize, alert
├── backtest.py                # replays the signal logic against historical data
├── fit_weights.py             # fits WEIGHTED_FACTOR_WEIGHTS from a backtest run (one-off analysis tool)
├── tickers.txt                # core watchlist (edit freely, one ticker per line)
├── movers_pool.txt            # wider large-cap pool for Notable Movers + backtest universe
├── state.json                 # dedup + signal-history state, committed back each run
├── docs/
│   ├── index.html             # the dashboard — static, no build step
│   └── data.json              # regenerated fresh every run, fetched client-side
├── backtest_results/
│   └── report.md              # latest backtest summary (committed); raw JSON outputs are gitignored
├── tests/
│   ├── test_rsi.py
│   ├── test_flags.py
│   ├── test_signal.py
│   ├── test_weighted_signal.py
│   └── test_accuracy.py
├── requirements.txt
├── requirements-test.txt
└── .github/workflows/
    ├── watchlist.yml          # the scheduled monitor run
    ├── watchlist-edit.yml     # dashboard-triggered watchlist add/remove
    └── tests.yml              # pytest on every push
```

## Running your own copy

<details>
<summary>Full setup steps</summary>

1. **Fork or clone this repo**, then push it to your own GitHub repo (public — GitHub Pages on the free plan only serves from public repos).
2. **Get a free [Finnhub](https://finnhub.io/register) API key** (no card required).
3. **Get an [Anthropic API key](https://console.anthropic.com)** for the synthesis step — the one piece of this stack that costs money, but usage is capped to only re-synthesize when something changed, so it's typically well under a dollar a month for a 10-stock watchlist.
4. **Create an iCloud app-specific password** at [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords (or adapt `monitor.py`'s SMTP settings for a different provider).
5. **Add repo secrets** (Settings → Secrets and variables → Actions): `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY`, `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, `ALERT_EMAIL_TO`.
6. **Enable GitHub Pages** (Settings → Pages → Deploy from a branch → `main` / `/docs`).
7. **Enable Actions** and run the `Stock Watchlist Monitor` workflow manually once to confirm it works, then let the schedule take over.

Edit [`tickers.txt`](tickers.txt) to change your watchlist, [`movers_pool.txt`](movers_pool.txt) to change the wider scan pool, and the `DAILY_DROP_PCT` / `WEEKLY_DROP_PCT` / `NEWS_KEYWORDS` env values in [`.github/workflows/watchlist.yml`](.github/workflows/watchlist.yml) to tune alert thresholds — all without touching Python.

</details>

## Notes / limits

- Runs entirely on GitHub's free Actions minutes — comfortably within the free tier even on a private-turned-public repo, at ~35 runs/day.
- Yahoo Finance's data via `yfinance` is unofficial and can occasionally hiccup for a given ticker; the script skips a failed ticker rather than failing the whole run.
- Accuracy tracking uses a simple calendar-day window (not a trading-day calendar) — a deliberate simplification, not an oversight.

## Disclaimer

This is a personal, informational side project — not a product, not investment advice, and not built or reviewed by a licensed financial advisor. It never places a trade or connects to a brokerage; it only reads public price/news data and displays what it found. Every number and signal on the dashboard is mechanically generated from technical indicators and should be independently verified before you make any decision with real money.

---

Built by [@MaxS2006](https://github.com/MaxS2006).
