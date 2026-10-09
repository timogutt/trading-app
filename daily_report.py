"""Daily portfolio report: what moved, by how much, and likely why. Optionally emailed.

Usage:  python daily_report.py [--portfolio portfolio.json] [--demo] [--send]
Without --send the report is just printed. Email settings come from env vars:
SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS, REPORT_TO (default SMTP_USER).
Holdings can also be given via the PORTFOLIO_JSON env var (handy for CI secrets).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage

from analysis import ma_stats
from data_sources import DemoSource, YahooSource

BENCHMARK = "SPY"
SPIKE = 1.5          # volume > 1.5x its 20-day average counts as unusual
BIG_MOVE = 0.03      # |daily move| >= 3% is flagged
MARKET_LED = 0.01    # within 1pt of the market's move => "mostly the market"


@dataclass
class Holding:
    ticker: str
    shares: float = 0
    cost: float | None = None


@dataclass
class Line:
    ticker: str
    price: float
    day_pct: float
    day_value: float | None
    pl_pct: float | None
    vs_ma52: float | None
    reasons: list[str] = field(default_factory=list)
    headlines: list[dict] = field(default_factory=list)


def load_holdings(path: str | None) -> list[Holding]:
    raw = os.environ.get("PORTFOLIO_JSON")
    data = json.loads(raw) if raw else json.load(open(path))
    return [Holding(d["ticker"].upper(), d.get("shares", 0), d.get("cost")) for d in data]


def day_change(prices) -> float | None:
    p = prices.dropna()
    return float(p.iloc[-1] / p.iloc[-2] - 1) if len(p) >= 2 else None


def explain(day: float, market: float | None, vol_ratio: float | None, vs_ma: float | None,
            prev_vs_ma: float | None) -> list[str]:
    """Rule-based hints. These are correlations, not proven causes."""
    out = []
    if market is not None:
        rel = day - market
        if abs(rel) <= MARKET_LED and abs(market) >= 0.005:
            out.append(f"Mostly market-driven: {BENCHMARK} moved {market:+.1%}.")
        elif abs(rel) > MARKET_LED:
            out.append(f"Stock-specific: {rel:+.1%} vs {BENCHMARK} ({market:+.1%}).")
    if vol_ratio and vol_ratio >= SPIKE:
        out.append(f"Unusual volume ({vol_ratio:.1f}x the 20-day average) - news or institutional activity likely.")
    if vs_ma is not None and prev_vs_ma is not None and (vs_ma >= 0) != (prev_vs_ma >= 0):
        out.append("Crossed its 52-week moving average " + ("upward." if vs_ma >= 0 else "downward."))
    if abs(day) >= BIG_MOVE and not out:
        out.append("Large move without a clear market or volume signal - check the headlines.")
    return out


def build_lines(holdings: list[Holding], source) -> list[Line]:
    end = dt.date.today() + dt.timedelta(days=1)
    start = dt.date.today() - dt.timedelta(days=420)
    try:
        market = day_change(source.history(BENCHMARK, start, end))
    except Exception:
        market = None
    lines = []
    for h in holdings:
        try:
            prices = source.history(h.ticker, start, end).dropna()
            day = day_change(prices)
            if day is None:
                continue
            st = ma_stats(prices)
            prev = ma_stats(prices.iloc[:-1])
            vs = st["price"] / st["ma52"] - 1 if st.get("ma52") else None
            pvs = prev["price"] / prev["ma52"] - 1 if prev.get("ma52") else None
            try:
                vol = source.volume(h.ticker).dropna()
                ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
            except Exception:
                ratio = None
            price = st["price"]
            lines.append(Line(
                h.ticker, price, day,
                h.shares * (price - float(prices.iloc[-2])) if h.shares else None,
                price / h.cost - 1 if h.cost else None, vs,
                explain(day, market, ratio, vs, pvs), source.news(h.ticker)[:3]))
        except Exception as e:
            lines.append(Line(h.ticker, float("nan"), 0, None, None, None, [f"Could not fetch data: {e}"]))
    return sorted(lines, key=lambda l: -abs(l.day_pct))


def render_text(lines: list[Line], today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    total = sum(l.day_value for l in lines if l.day_value is not None)
    out = [f"Daily portfolio report - {today:%A %d %B %Y}", f"Estimated P/L today: {total:+,.2f}", ""]
    for l in lines:
        row = f"{l.ticker:<8} {l.price:>10,.2f}  {l.day_pct:+.2%} today"
        if l.day_value is not None:
            row += f" ({l.day_value:+,.2f})"
        if l.pl_pct is not None:
            row += f" | vs cost {l.pl_pct:+.1%}"
        if l.vs_ma52 is not None:
            row += f" | {l.vs_ma52:+.1%} vs 52w MA"
        out.append(row)
        out += [f"    - {r}" for r in l.reasons]
        out += [f"    > {n['title']} ({n['publisher']})" for n in l.headlines]
        out.append("")
    out.append("Reasons are automated hints from price, volume and headlines - not investment advice.")
    return "\n".join(out)


def send_email(body: str, subject: str) -> None:
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, os.environ.get("REPORT_TO", user)
    msg.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
        s.starttls()
        s.login(user, os.environ["SMTP_PASS"])
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", default="portfolio.json")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--send", action="store_true", help="email the report")
    a = ap.parse_args()
    lines = build_lines(load_holdings(a.portfolio), DemoSource() if a.demo else YahooSource())
    text = render_text(lines)
    print(text)
    if a.send:
        send_email(text, f"Portfolio report {dt.date.today():%Y-%m-%d}")


if __name__ == "__main__":
    main()
