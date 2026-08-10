#!/usr/bin/env python3
"""
Stock watchlist monitor.

Reads tickers.txt, checks price moves (day + week) via Yahoo Finance and
recent news via Finnhub, and:
  1. Emails a summary ONLY when something crosses a threshold or there's
     notable new news (state.json prevents repeat emails about the same
     drop/article).
  2. Writes docs/data.json with a richer set of technical metrics (RSI,
     volume, 50-day MA, sector breadth, earnings proximity) plus a
     one-line Claude-generated synthesis per ticker, for the GitHub Pages
     dashboard to render.

This script only reads data and sends an email — it never places trades.
"""

import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.mime.text import MIMEText

import pandas as pd
import requests
import yfinance as yf

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - only missing if requirements.txt not installed
    Anthropic = None

# --- Configuration (env vars, set in the workflow file / repo settings) ---

TICKERS_FILE = os.environ.get("TICKERS_FILE", "tickers.txt")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
DASHBOARD_DATA_FILE = os.environ.get("DASHBOARD_DATA_FILE", "docs/data.json")

DAILY_DROP_PCT = float(os.environ.get("DAILY_DROP_PCT", "5"))
WEEKLY_DROP_PCT = float(os.environ.get("WEEKLY_DROP_PCT", "8"))

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", EMAIL_ADDRESS)
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.mail.me.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Headlines only count as "notable" (for the email) if they contain one of
# these keywords, UNLESS the ticker's price already crossed a threshold (in
# which case any recent headline is shown for context). Edit freely.
NEWS_KEYWORDS = [
    kw.strip().lower()
    for kw in os.environ.get(
        "NEWS_KEYWORDS",
        "earnings,guidance,downgrade,upgrade,lawsuit,investigation,recall,"
        "sec,merger,acquisition,acquire,bankruptcy,layoff,layoffs,ceo,"
        "resign,fraud,fda,fine,settlement,cut,beats,misses,warns,plunge,"
        "surge,halt,recession,antitrust,strike,default,delist",
    ).split(",")
    if kw.strip()
]

MAX_SEEN_IDS_PER_TICKER = 200
NEWS_LOOKBACK_DAYS = 2
MAX_NEWS_PER_TICKER = 3

# Dashboard / technical-metrics tuning.
HISTORY_PERIOD = "6mo"  # comfortably covers 50-day MA + 14-day RSI + volume avg
CANDLE_POINTS = 20  # trading days of OHLC history sent to the dashboard's charts
RSI_PERIOD = 14
VOLUME_AVG_DAYS = 20
MA_PERIOD = 50
EARNINGS_LOOKAHEAD_DAYS = 14
# A ticker's daily move counts as "sector-wide" rather than "stock-specific"
# if it's within this many percentage points of the watchlist average move
# and points the same direction.
BREADTH_DIFF_THRESHOLD_PCT = 2.0
# Must match the workflow's cron window (13-21 UTC, every 15 min, Mon-Fri).
CHECKS_PER_DAY = 36


def load_tickers(path):
    tickers = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tickers.append(line.upper())
    return tickers


def load_state(path):
    if not os.path.exists(path):
        return {"tickers": {}, "seen_news_ids": {}}
    with open(path) as f:
        state = json.load(f)
    state.setdefault("tickers", {})
    state.setdefault("seen_news_ids", {})
    return state


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


# --- Price history + technical metrics ------------------------------------


def fetch_history(symbol):
    hist = yf.Ticker(symbol).history(period=HISTORY_PERIOD, interval="1d")
    if hist.empty or len(hist) < 2:
        return None
    return hist


def compute_price_moves(closes):
    current_price = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    daily_pct = (current_price - prev_close) / prev_close * 100
    week_idx = -6 if len(closes) >= 6 else 0
    week_ago_close = float(closes.iloc[week_idx])
    weekly_pct = (current_price - week_ago_close) / week_ago_close * 100
    return current_price, daily_pct, weekly_pct


def compute_rsi(closes, period=RSI_PERIOD):
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    last_avg_loss = avg_loss.iloc[-1]
    last_avg_gain = avg_gain.iloc[-1]
    if pd.isna(last_avg_gain) or pd.isna(last_avg_loss):
        return None
    if last_avg_loss == 0:
        return 100.0
    rs = last_avg_gain / last_avg_loss
    return 100 - (100 / (1 + rs))


def rsi_label(rsi):
    if rsi is None:
        return None
    if rsi <= 30:
        return "oversold"
    if rsi >= 70:
        return "overbought"
    return "neutral"


def compute_volume_ratio(volumes):
    if len(volumes) < VOLUME_AVG_DAYS + 1:
        return None
    today_vol = float(volumes.iloc[-1])
    avg_vol = float(volumes.iloc[-(VOLUME_AVG_DAYS + 1):-1].mean())
    if avg_vol == 0:
        return None
    return today_vol / avg_vol


def build_candles(hist, points=CANDLE_POINTS):
    """OHLC bars (date + open/high/low/close) for the dashboard's candlestick charts."""
    ohlc = hist[["Open", "High", "Low", "Close"]].dropna()
    tail = ohlc.tail(points)
    return [
        {
            "t": idx.strftime("%Y-%m-%d"),
            "o": round(float(row["Open"]), 2),
            "h": round(float(row["High"]), 2),
            "l": round(float(row["Low"]), 2),
            "c": round(float(row["Close"]), 2),
        }
        for idx, row in tail.iterrows()
    ]


def compute_ma50_pct(closes):
    if len(closes) < MA_PERIOD:
        return None
    ma = float(closes.rolling(MA_PERIOD).mean().iloc[-1])
    current = float(closes.iloc[-1])
    if ma == 0:
        return None
    return (current - ma) / ma * 100


def get_earnings_info(ticker_obj):
    try:
        ed = ticker_obj.get_earnings_dates(limit=8)
    except Exception:
        return {"flag": False, "text": "No earnings soon"}
    if ed is None or ed.empty:
        return {"flag": False, "text": "No earnings soon"}
    now = pd.Timestamp.now(tz=ed.index.tz) if ed.index.tz is not None else pd.Timestamp.now()
    for ts in sorted(ed.index):
        days = (ts.date() - now.date()).days
        if -3 <= days < 0:
            return {"flag": True, "text": "Earnings just passed"}
        if 0 <= days <= EARNINGS_LOOKAHEAD_DAYS:
            return {"flag": True, "text": f"Earnings in {days}d"}
    return {"flag": False, "text": "No earnings soon"}


def classify_breadth(daily_pct, avg_daily_pct):
    if daily_pct is None or avg_daily_pct is None:
        return "unknown"
    same_direction = (daily_pct >= 0) == (avg_daily_pct >= 0) or abs(avg_daily_pct) < 0.3
    diff = abs(daily_pct - avg_daily_pct)
    return "sector" if (diff <= BREADTH_DIFF_THRESHOLD_PCT and same_direction) else "specific"


# --- Factors / signal scoring ----------------------------------------------


def build_factors(metrics):
    factors = []

    if metrics["rsi"] is not None:
        lean = {"oversold": "pos", "overbought": "neg", "neutral": "neutral"}[metrics["rsi_label"]]
        factors.append({"label": f"RSI {metrics['rsi']:.0f}", "lean": lean})

    if metrics["volume_ratio"] is not None:
        if metrics["volume_ratio"] >= 1.5:
            lean = "pos" if metrics["daily_pct"] >= 0 else "neg"
            factors.append({"label": f"Vol: {metrics['volume_ratio']:.1f}x avg", "lean": lean})
        else:
            factors.append({"label": "Vol: avg", "lean": "neutral"})

    if metrics["ma50_pct"] is not None:
        if metrics["ma50_pct"] >= 0:
            factors.append({"label": "Above 50d avg", "lean": "pos"})
        else:
            factors.append({"label": "Below 50d avg", "lean": "neg"})

    breadth = metrics["breadth"]
    if breadth == "sector":
        if metrics["daily_pct"] is not None and metrics["daily_pct"] < 0:
            factors.append({"label": "Sector-wide dip", "lean": "pos"})
        else:
            factors.append({"label": "Sector-wide rally", "lean": "neutral"})
    elif breadth == "specific":
        if metrics["daily_pct"] is not None and metrics["daily_pct"] < 0:
            factors.append({"label": "Stock-specific move", "lean": "neg"})
        else:
            factors.append({"label": "Stock-specific move", "lean": "pos"})

    earnings = metrics["earnings"]
    if earnings["flag"]:
        factors.append({"label": earnings["text"], "lean": "neg"})
    else:
        factors.append({"label": "No earnings soon", "lean": "neutral"})

    return factors


def compute_signal(factors):
    up = sum(1 for f in factors if f["lean"] == "pos")
    down = sum(1 for f in factors if f["lean"] == "neg")
    neutral = sum(1 for f in factors if f["lean"] == "neutral")

    # A tie or near-silence (<=1 total non-neutral factor) isn't a real lean.
    if up + down <= 1:
        label, cls, icon = "NOTHING COMPELLING", "mixed", "◆"
    elif up == down:
        label, cls, icon = "MIXED SIGNALS", "mixed", "⚠"
    elif up > down:
        label, cls, icon = "LEANS POSITIVE", "bullish", "▲"
    else:
        label, cls, icon = "LEANS NEGATIVE", "bearish", "▼"

    return {"label": label, "class": cls, "icon": icon, "up": up, "down": down, "neutral": neutral}


# --- Claude synthesis --------------------------------------------------------

_anthropic_client = None
_anthropic_client_loaded = False


def get_anthropic_client():
    global _anthropic_client, _anthropic_client_loaded
    if not _anthropic_client_loaded:
        _anthropic_client_loaded = True
        if Anthropic is not None and ANTHROPIC_API_KEY:
            _anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def fallback_read_line(symbol, metrics):
    """Deterministic, free fallback used if Claude is unavailable or errors."""
    parts = []
    if metrics["rsi"] is not None:
        parts.append(f"RSI {metrics['rsi']:.0f} ({metrics['rsi_label']})")
    if metrics["ma50_pct"] is not None:
        side = "above" if metrics["ma50_pct"] >= 0 else "below"
        parts.append(f"{abs(metrics['ma50_pct']):.1f}% {side} its 50-day average")
    if metrics["breadth"] in ("sector", "specific"):
        parts.append("part of a broader sector move" if metrics["breadth"] == "sector" else "a stock-specific move")
    if metrics["earnings"]["flag"]:
        parts.append(metrics["earnings"]["text"].lower())
    if not parts:
        return f"{symbol}: not enough data this run to summarize."
    return f"{symbol}: " + ", ".join(parts) + "."


def synthesize_read_line(symbol, metrics, news_headlines):
    client = get_anthropic_client()
    if client is None:
        return fallback_read_line(symbol, metrics)

    headlines_text = "\n".join(f"- {h}" for h in news_headlines) or "(no recent news found)"
    breadth_text = {"sector": "sector-wide", "specific": "stock-specific"}.get(metrics["breadth"], "unclear")

    lines = [
        f"Ticker: {symbol}",
        f"Price: ${metrics['price']:.2f}, day {metrics['daily_pct']:+.1f}%, "
        f"week {metrics['weekly_pct']:+.1f}%",
    ]
    if metrics["rsi"] is not None:
        lines.append(f"RSI(14): {metrics['rsi']:.0f} ({metrics['rsi_label']})")
    if metrics["volume_ratio"] is not None:
        lines.append(f"Volume: {metrics['volume_ratio']:.1f}x its 20-day average")
    if metrics["ma50_pct"] is not None:
        lines.append(f"Price vs 50-day average: {metrics['ma50_pct']:+.1f}%")
    lines.append(f"Move looks: {breadth_text}")
    lines.append(f"Earnings: {metrics['earnings']['text']}")
    lines.append(f"Recent headlines:\n{headlines_text}")
    lines.append("")
    lines.append(
        "In ONE plain-English sentence (max ~28 words), synthesize what's "
        "actually going on for this stock right now, combining the technical "
        "picture with the news context. Be factual and neutral. Do not use "
        "the words 'buy', 'sell', or 'hold', and do not give any investment "
        "recommendation — just describe the situation."
    )
    prompt = "\n".join(lines)

    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        return text or fallback_read_line(symbol, metrics)
    except Exception as exc:  # noqa: BLE001 - never let a bad API call break the run
        print(f"[warn] {symbol}: Claude synthesis failed: {exc}", file=sys.stderr)
        return fallback_read_line(symbol, metrics)


# --- News (Finnhub) ----------------------------------------------------------


def get_news(symbol):
    if not FINNHUB_API_KEY:
        return []
    to_date = date.today()
    from_date = to_date - timedelta(days=NEWS_LOOKBACK_DAYS)
    resp = requests.get(
        "https://finnhub.io/api/v1/company-news",
        params={
            "symbol": symbol,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": FINNHUB_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    articles = resp.json()
    articles.sort(key=lambda a: a.get("datetime", 0), reverse=True)
    return articles


def is_notable(headline):
    headline_lower = (headline or "").lower()
    return any(kw in headline_lower for kw in NEWS_KEYWORDS)


def article_id(article):
    return str(article.get("id") or article.get("url") or article.get("headline"))


# --- Per-ticker processing ----------------------------------------------------


def gather_ticker_data(symbol):
    """Fetch price history, earnings, and news for one ticker. No side effects."""
    data = {
        "symbol": symbol,
        "current_price": None,
        "daily_pct": None,
        "weekly_pct": None,
        "candles": [],
        "rsi": None,
        "rsi_label": None,
        "volume_ratio": None,
        "ma50_pct": None,
        "earnings": {"flag": False, "text": "No earnings soon"},
        "articles": [],
        "price_error": None,
    }

    ticker_obj = yf.Ticker(symbol)

    try:
        hist = fetch_history(symbol)
    except Exception as exc:  # noqa: BLE001
        hist = None
        data["price_error"] = f"price lookup failed: {exc}"
        print(f"[warn] {symbol}: {data['price_error']}", file=sys.stderr)

    if hist is not None:
        closes = hist["Close"].dropna()
        volumes = hist["Volume"].dropna()
        if len(closes) >= 2:
            current_price, daily_pct, weekly_pct = compute_price_moves(closes)
            data["current_price"] = current_price
            data["daily_pct"] = daily_pct
            data["weekly_pct"] = weekly_pct
            data["candles"] = build_candles(hist)
            rsi = compute_rsi(closes)
            data["rsi"] = rsi
            data["rsi_label"] = rsi_label(rsi)
            data["volume_ratio"] = compute_volume_ratio(volumes)
            data["ma50_pct"] = compute_ma50_pct(closes)

    try:
        data["earnings"] = get_earnings_info(ticker_obj)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] {symbol}: earnings lookup failed: {exc}", file=sys.stderr)

    try:
        data["articles"] = get_news(symbol)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] {symbol}: news lookup failed: {exc}", file=sys.stderr)

    return data


def process_ticker(raw, state, today_str, avg_daily_pct):
    """Apply email-alert dedup logic, technical scoring, and synthesis caching."""
    symbol = raw["symbol"]
    ticker_state = state["tickers"].setdefault(symbol, {})
    seen_ids_before = set(state["seen_news_ids"].get(symbol, []))

    daily_flag = raw["daily_pct"] is not None and raw["daily_pct"] <= -DAILY_DROP_PCT
    weekly_flag = raw["weekly_pct"] is not None and raw["weekly_pct"] <= -WEEKLY_DROP_PCT

    articles = raw["articles"]
    if daily_flag or weekly_flag:
        email_candidates = articles
    else:
        email_candidates = [a for a in articles if is_notable(a.get("headline"))]

    email_news = []
    for a in email_candidates:
        aid = article_id(a)
        if aid not in seen_ids_before and len(email_news) < MAX_NEWS_PER_TICKER:
            email_news.append(a)

    has_new_news = any(article_id(a) not in seen_ids_before for a in articles)

    # Mark every fetched headline as seen so nothing is re-flagged later, even
    # if it wasn't notable enough to include this run.
    seen_ids = seen_ids_before | {article_id(a) for a in articles}
    state["seen_news_ids"][symbol] = list(seen_ids)[-MAX_SEEN_IDS_PER_TICKER:]

    last_daily_alert = ticker_state.get("last_daily_alert_date")
    last_weekly_alert = ticker_state.get("last_weekly_alert_date")
    send_daily = daily_flag and last_daily_alert != today_str
    send_weekly = weekly_flag and last_weekly_alert != today_str
    if send_daily:
        ticker_state["last_daily_alert_date"] = today_str
    if send_weekly:
        ticker_state["last_weekly_alert_date"] = today_str

    email_result = {
        "symbol": symbol,
        "current_price": raw["current_price"],
        "daily_pct": raw["daily_pct"],
        "weekly_pct": raw["weekly_pct"],
        "daily_flag": send_daily,
        "weekly_flag": send_weekly,
        "news": email_news,
        "error": raw["price_error"],
    }
    should_email = send_daily or send_weekly or bool(email_news)

    # --- Dashboard metrics ---
    breadth = classify_breadth(raw["daily_pct"], avg_daily_pct)
    metrics = {
        "symbol": symbol,
        "price": raw["current_price"],
        "daily_pct": raw["daily_pct"],
        "weekly_pct": raw["weekly_pct"],
        "rsi": raw["rsi"],
        "rsi_label": raw["rsi_label"],
        "volume_ratio": raw["volume_ratio"],
        "ma50_pct": raw["ma50_pct"],
        "breadth": breadth,
        "earnings": raw["earnings"],
    }

    dashboard_entry = None
    if raw["current_price"] is not None:
        factors = build_factors(metrics)
        signal = compute_signal(factors)

        cached_rsi_label = ticker_state.get("last_rsi_label")
        cached_price_flag = ticker_state.get("last_price_flag")
        current_price_flag = bool(daily_flag or weekly_flag)
        needs_resynthesis = (
            not ticker_state.get("last_synthesis")
            or has_new_news
            or raw["rsi_label"] != cached_rsi_label
            or current_price_flag != cached_price_flag
        )

        if needs_resynthesis:
            headlines = [a.get("headline") for a in articles[:5] if a.get("headline")]
            read_line = synthesize_read_line(symbol, metrics, headlines)
            ticker_state["last_synthesis"] = read_line
            ticker_state["last_synthesis_at"] = datetime.now(timezone.utc).isoformat()
        else:
            read_line = ticker_state["last_synthesis"]

        ticker_state["last_rsi_label"] = raw["rsi_label"]
        ticker_state["last_price_flag"] = current_price_flag

        dashboard_entry = {
            "symbol": symbol,
            "price": raw["current_price"],
            "daily_pct": raw["daily_pct"],
            "weekly_pct": raw["weekly_pct"],
            "flagged": current_price_flag,
            "candles": raw["candles"],
            "rsi": raw["rsi"],
            "rsi_label": raw["rsi_label"],
            "volume_ratio": raw["volume_ratio"],
            "ma50_pct": raw["ma50_pct"],
            "breadth": breadth,
            "earnings_text": raw["earnings"]["text"],
            "factors": factors,
            "signal": signal,
            "read_line": read_line,
        }

    return email_result, should_email, dashboard_entry


# --- Email -------------------------------------------------------------------


def format_email(alerts, today_str):
    lines = [f"Stock watchlist summary — {today_str}", ""]
    for r in alerts:
        lines.append(f"=== {r['symbol']} ===")
        if r["current_price"] is not None:
            lines.append(
                f"Price: ${r['current_price']:.2f}  "
                f"(day {r['daily_pct']:+.1f}%, week {r['weekly_pct']:+.1f}%)"
            )
            if r["daily_flag"]:
                lines.append(f"  -> Daily drop threshold breached (>= {DAILY_DROP_PCT}%)")
            if r["weekly_flag"]:
                lines.append(f"  -> Weekly drop threshold breached (>= {WEEKLY_DROP_PCT}%)")
        if r["error"]:
            lines.append(f"  (price data issue: {r['error']})")
        for article in r["news"]:
            headline = article.get("headline", "(no headline)")
            source = article.get("source", "")
            url = article.get("url", "")
            lines.append(f"  - {headline} [{source}]")
            if url:
                lines.append(f"    {url}")
        lines.append("")
    lines.append(
        "This is an automated informational alert only — not investment "
        "advice, and no trades were placed. Edit tickers.txt to change the "
        "watchlist."
    )
    return "\n".join(lines)


def send_email(subject, body):
    if not (EMAIL_ADDRESS and EMAIL_APP_PASSWORD and ALERT_EMAIL_TO):
        print("[error] email not configured (missing secrets); skipping send", file=sys.stderr)
        print(body)
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ALERT_EMAIL_TO

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, [ALERT_EMAIL_TO], msg.as_string())


# --- Dashboard JSON ------------------------------------------------------------


def build_dashboard(entries, generated_at):
    valid = [e for e in entries if e is not None]

    flagged = []
    for e in valid:
        if not e["flagged"]:
            continue
        if e["weekly_pct"] is not None and e["weekly_pct"] <= -WEEKLY_DROP_PCT:
            badge = f"WEEK {e['weekly_pct']:+.1f}%"
        else:
            badge = f"DAY {e['daily_pct']:+.1f}%"
        flagged.append({"symbol": e["symbol"], "badge": badge})

    featured_mover = None
    with_weekly = [e for e in valid if e["weekly_pct"] is not None]
    if with_weekly:
        featured_mover = max(with_weekly, key=lambda e: abs(e["weekly_pct"]))

    best_performer = None
    if with_weekly:
        best_performer = max(with_weekly, key=lambda e: e["weekly_pct"])["symbol"]

    green_count = sum(1 for e in with_weekly if e["weekly_pct"] > 0)
    avg_weekly_pct = sum(e["weekly_pct"] for e in with_weekly) / len(with_weekly) if with_weekly else None

    next_sync = generated_at + timedelta(minutes=15)

    return {
        "generated_at": generated_at.isoformat(),
        "next_sync_at": next_sync.isoformat(),
        "checks_per_day": CHECKS_PER_DAY,
        "tickers_tracked": len(valid),
        "flagged": flagged,
        "featured_mover": featured_mover,
        "best_performer": best_performer,
        "watchlist_health": {
            "green_count": green_count,
            "total": len(with_weekly),
            "avg_weekly_pct": avg_weekly_pct,
        },
        "stocks": valid,
    }


def save_dashboard(path, dashboard):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(dashboard, f, indent=2, sort_keys=True)
        f.write("\n")


# --- Main ----------------------------------------------------------------------


def main():
    today_str = date.today().isoformat()
    generated_at = datetime.now(timezone.utc)
    tickers = load_tickers(TICKERS_FILE)
    state = load_state(STATE_FILE)

    raw_data = [gather_ticker_data(symbol) for symbol in tickers]

    valid_daily = [r["daily_pct"] for r in raw_data if r["daily_pct"] is not None]
    avg_daily_pct = sum(valid_daily) / len(valid_daily) if valid_daily else None

    email_alerts = []
    dashboard_entries = []
    for raw in raw_data:
        email_result, should_email, dashboard_entry = process_ticker(raw, state, today_str, avg_daily_pct)
        if should_email:
            email_alerts.append(email_result)
        dashboard_entries.append(dashboard_entry)

    save_state(STATE_FILE, state)
    save_dashboard(DASHBOARD_DATA_FILE, build_dashboard(dashboard_entries, generated_at))

    if email_alerts:
        subject = f"Stock Watchlist Alert — {len(email_alerts)} flagged — {today_str}"
        body = format_email(email_alerts, today_str)
        send_email(subject, body)
        print(f"Sent alert email for: {', '.join(a['symbol'] for a in email_alerts)}")
    else:
        print(f"[{generated_at.isoformat(timespec='seconds')}] No alerts — nothing sent.")


if __name__ == "__main__":
    main()
