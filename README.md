# Stock Watchlist Monitor

Checks your watchlist every 15 minutes during US market hours and emails you
a summary **only** when a stock drops sharply or has notable news. It never
places trades — it just alerts you.

- **Prices:** [Yahoo Finance](https://finance.yahoo.com) via the `yfinance`
  library — free, no signup.
- **News:** [Finnhub](https://finnhub.io) free tier — needs a free API key.
- **Email:** sent via iCloud SMTP using an app-specific password.
- **Dedup:** `state.json` tracks what's already been alerted so you don't
  get repeat emails about the same drop or article every 15 minutes.

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

## 4. Add repo secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add:

| Secret | Value |
|---|---|
| `FINNHUB_API_KEY` | your Finnhub API key |
| `EMAIL_ADDRESS` | `maxjsharman@icloud.com` |
| `EMAIL_APP_PASSWORD` | the app-specific password from step 3 |
| `ALERT_EMAIL_TO` | `maxjsharman@icloud.com` (where alerts get sent — can differ from `EMAIL_ADDRESS`) |

## 5. Enable Actions and test it

1. Go to the **Actions** tab in your repo, and enable workflows if prompted.
2. Click **Stock Watchlist Monitor** → **Run workflow** to trigger it
   manually and confirm it works (check the run logs for errors, and check
   your inbox if anything was flagged that day).
3. After that, it runs automatically every 15 minutes, 13:00–21:45 UTC,
   Monday–Friday (covers 9:30am–4:00pm ET with margin either side of
   daylight saving, so no seasonal adjustment needed).

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

## Notes / limits

- Runs on GitHub's free Actions minutes. At ~35 runs/day, 5 days/week, each
  taking under a minute, this comfortably fits within the free tier even on
  a private repo.
- Yahoo Finance's data via `yfinance` is unofficial and can occasionally
  hiccup for a given ticker — the script skips a failed ticker rather than
  failing the whole run, and logs a warning in the Action's run output.
- This is informational only, not investment advice, and it never executes
  any trade.
