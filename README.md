# Stock Watchlist Monitor

Checks your watchlist every 15 minutes during US market hours, emails you a
summary **only** when a stock drops sharply or has notable news, and
publishes a live dashboard on GitHub Pages. It never places trades — it
just alerts you.

- **Prices:** [Yahoo Finance](https://finance.yahoo.com) via the `yfinance`
  library — free, no signup.
- **News:** [Finnhub](https://finnhub.io) free tier — needs a free API key.
- **Email:** sent via iCloud SMTP using an app-specific password.
- **Dashboard synthesis:** [Claude Haiku](https://www.anthropic.com) writes
  a one-line read per stock combining the technicals and news — the only
  paid piece of this stack (pay-per-token, but cheap; see below on cost).
- **Dedup:** `state.json` tracks what's already been alerted/synthesized so
  you don't get repeat emails or repeat API calls for the same drop, RSI
  state, or article every 15 minutes.

## 1. Create the GitHub repo

From this folder:

```bash
git init
git add .
git commit -m "Initial watchlist monitor"
```

Then create a new (private is fine) repo on GitHub and push:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

## 2. Get a free Finnhub API key

1. Sign up at [finnhub.io/register](https://finnhub.io/register) (free, no
   card required).
2. Copy your API key from the dashboard.

## 3. Create an iCloud app-specific password

1. Go to [appleid.apple.com](https://appleid.apple.com) → sign in →
   **Sign-In and Security** → **App-Specific Passwords** → generate one.
2. Save the generated password — you won't be able to view it again.

## 4. Get an Anthropic API key (for the dashboard synthesis)

1. Go to [console.anthropic.com](https://console.anthropic.com), sign in
   (or create an account), and make sure billing is set up.
2. Create an API key and copy it.
3. This is the one piece of the stack that costs money, but it's cheap: the
   script only calls Claude Haiku for a ticker when something actually
   changed since the last run (new news, an RSI-category flip, or a
   flag state change), not on every 15-minute tick — typically well under a
   dollar a month for a 10-stock watchlist.

## 5. Add repo secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add:

| Secret | Value |
|---|---|
| `FINNHUB_API_KEY` | your Finnhub API key |
| `ANTHROPIC_API_KEY` | your Anthropic API key |
| `EMAIL_ADDRESS` | `maxjsharman@icloud.com` |
| `EMAIL_APP_PASSWORD` | the app-specific password from step 3 |
| `ALERT_EMAIL_TO` | `maxjsharman@icloud.com` (where alerts get sent — can differ from `EMAIL_ADDRESS`) |

## 6. Enable GitHub Pages

1. In your repo, go to **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Set branch to **main** and folder to **/docs**, then **Save**.
4. GitHub will give you a live URL like
   `https://<your-username>.github.io/<repo-name>/` — that's your shareable
   dashboard link. It can take a minute or two to go live the first time.

## 7. Enable Actions and test it

1. Go to the **Actions** tab in your repo, and enable workflows if prompted.
2. Click **Stock Watchlist Monitor** → **Run workflow** to trigger it
   manually and confirm it works (check the run logs for errors, and check
   your inbox if anything was flagged that day).
3. Refresh your Pages URL from step 6 — it should now show live data instead
   of the "waiting for the first run" placeholder.
4. After that, it runs automatically every 15 minutes, 13:00–21:45 UTC,
   Monday–Friday (covers 9:30am–4:00pm ET with margin either side of
   daylight saving, so no seasonal adjustment needed), and the dashboard
   updates itself each run.

## Editing your watchlist

Edit [`tickers.txt`](tickers.txt) — one ticker per line, `#` for comments.
You can edit it directly on GitHub.com from your phone; no code changes
needed. Commit the change and the next scheduled run picks it up.

## Adjusting thresholds

Open [`.github/workflows/watchlist.yml`](.github/workflows/watchlist.yml)
and edit the `DAILY_DROP_PCT` (default `5`) and `WEEKLY_DROP_PCT` (default
`8`) values under `env:`. These are the % drops (day-over-day and
week-over-week) that trigger an alert.

You can also tune `NEWS_KEYWORDS` there (comma-separated) — headlines only
count as "notable" if they match one of these keywords, unless the ticker's
price already crossed a threshold, in which case any recent headline is
included for context.

## The dashboard

Each ticker card shows price, day/week % change, a sparkline, RSI(14) with
an Oversold/Overbought/Neutral label, volume vs. its own 20-day average,
position vs. its 50-day moving average, whether the move looks stock-specific
or sector-wide (compared against the rest of your watchlist), earnings-date
proximity, a Claude-written one-line synthesis, and a signal bar.

The signal bar counts how many of those five factors lean positive, negative,
or neutral and labels the mix — **LEANS POSITIVE**, **LEANS NEGATIVE**,
**MIXED SIGNALS**, or **NOTHING COMPELLING** — deliberately never using
buy/sell language. It's a mechanical tally of technical factors, not
investment advice.

`monitor.py` writes [`docs/data.json`](docs/data.json) fresh every run;
[`docs/index.html`](docs/index.html) is a static page that fetches it
client-side, so the dashboard updates automatically — no rebuild step.

## Notes / limits

- Runs on GitHub's free Actions minutes. At ~35 runs/day, 5 days/week, each
  taking under a minute, this comfortably fits within the free tier even on
  a private repo.
- GitHub Pages on the free plan only serves from **public** repos, so this
  repo needs to stay public for the dashboard link to work (no secrets live
  in the code — only in Actions secrets — so nothing sensitive is exposed).
- Yahoo Finance's data via `yfinance` is unofficial and can occasionally
  hiccup for a given ticker — the script skips a failed ticker rather than
  failing the whole run, and logs a warning in the Action's run output.
- This is informational only, not investment advice, and it never executes
  any trade.
