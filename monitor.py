#!/usr/bin/env python3
"""
Stock watchlist monitor.

Reads tickers.txt, checks price moves (day + week) via Yahoo Finance and
recent news via Finnhub, and emails a summary ONLY when something crosses
a threshold or there's notable new news. Keeps state.json so the same
drop/article doesn't trigger a fresh email every run.

This script only reads data and sends an email — it never places trades.
"""

import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText

import requests
import yfinance as yf

# --- Configuration (env vars, set in the workflow file / repo settings) ---

TICKERS_FILE = os.environ.get("TICKERS_FILE", "tickers.txt")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")

DAILY_DROP_PCT = float(os.environ.get("DAILY_DROP_PCT", "5"))
WEEKLY_DROP_PCT = float(os.environ.get("WEEKLY_DROP_PCT", "8"))

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", EMAIL_ADDRESS)
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.mail.me.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Headlines only count as "notable" if they contain one of these keywords,
# UNLESS the ticker's price already crossed a threshold (in which case any
# recent headline is shown for context). Edit freely.
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


def get_price_move(symbol):
    """Return (current_price, daily_pct, weekly_pct) or None if unavailable."""
    hist = yf.Ticker(symbol).history(period="10d", interval="1d")
    if hist.empty or len(hist) < 2:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    current_price = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    week_ago_close = float(closes.iloc[0])
    daily_pct = (current_price - prev_close) / prev_close * 100
    weekly_pct = (current_price - week_ago_close) / week_ago_close * 100
    return current_price, daily_pct, weekly_pct


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
    # Most recent first.
    articles.sort(key=lambda a: a.get("datetime", 0), reverse=True)
    return articles


def is_notable(headline):
    headline_lower = (headline or "").lower()
    return any(kw in headline_lower for kw in NEWS_KEYWORDS)


def process_ticker(symbol, state, today_str):
    ticker_state = state["tickers"].setdefault(symbol, {})
    seen_ids = set(state["seen_news_ids"].get(symbol, []))

    result = {
        "symbol": symbol,
        "current_price": None,
        "daily_pct": None,
        "weekly_pct": None,
        "daily_flag": False,
        "weekly_flag": False,
        "news": [],
        "error": None,
    }

    try:
        price_move = get_price_move(symbol)
    except Exception as exc:  # noqa: BLE001 - one bad ticker shouldn't kill the run
        price_move = None
        result["error"] = f"price lookup failed: {exc}"
        print(f"[warn] {symbol}: {result['error']}", file=sys.stderr)

    daily_flag = weekly_flag = False
    if price_move is not None:
        current_price, daily_pct, weekly_pct = price_move
        result["current_price"] = current_price
        result["daily_pct"] = daily_pct
        result["weekly_pct"] = weekly_pct
        daily_flag = daily_pct <= -DAILY_DROP_PCT
        weekly_flag = weekly_pct <= -WEEKLY_DROP_PCT

    try:
        articles = get_news(symbol)
    except Exception as exc:  # noqa: BLE001
        articles = []
        print(f"[warn] {symbol}: news lookup failed: {exc}", file=sys.stderr)

    # Any headline counts as context once price already flagged; otherwise
    # require a notable keyword match so routine reposts don't spam you.
    if daily_flag or weekly_flag:
        candidates = articles
    else:
        candidates = [a for a in articles if is_notable(a.get("headline"))]

    new_articles = []
    all_ids_this_run = []
    for article in candidates:
        article_id = str(article.get("id") or article.get("url") or article.get("headline"))
        all_ids_this_run.append(article_id)
        if article_id not in seen_ids and len(new_articles) < MAX_NEWS_PER_TICKER:
            new_articles.append(article)

    # Mark every candidate headline as "seen" so it's never re-flagged, even
    # if it wasn't notable enough to include this run.
    for article in articles:
        article_id = str(article.get("id") or article.get("url") or article.get("headline"))
        seen_ids.add(article_id)
    seen_list = list(seen_ids)[-MAX_SEEN_IDS_PER_TICKER:]
    state["seen_news_ids"][symbol] = seen_list

    last_daily_alert = ticker_state.get("last_daily_alert_date")
    last_weekly_alert = ticker_state.get("last_weekly_alert_date")

    send_daily = daily_flag and last_daily_alert != today_str
    send_weekly = weekly_flag and last_weekly_alert != today_str

    result["daily_flag"] = send_daily
    result["weekly_flag"] = send_weekly
    result["news"] = new_articles

    should_alert = send_daily or send_weekly or bool(new_articles)

    if send_daily:
        ticker_state["last_daily_alert_date"] = today_str
    if send_weekly:
        ticker_state["last_weekly_alert_date"] = today_str

    return result, should_alert


def format_email(alerts, today_str):
    lines = [
        f"Stock watchlist summary — {today_str}",
        "",
    ]
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


def main():
    today_str = date.today().isoformat()
    tickers = load_tickers(TICKERS_FILE)
    state = load_state(STATE_FILE)

    alerts = []
    for symbol in tickers:
        result, should_alert = process_ticker(symbol, state, today_str)
        if should_alert:
            alerts.append(result)

    save_state(STATE_FILE, state)

    if alerts:
        subject = f"Stock Watchlist Alert — {len(alerts)} flagged — {today_str}"
        body = format_email(alerts, today_str)
        send_email(subject, body)
        print(f"Sent alert email for: {', '.join(a['symbol'] for a in alerts)}")
    else:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] No alerts — nothing sent.")


if __name__ == "__main__":
    main()
