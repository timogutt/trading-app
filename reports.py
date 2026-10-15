"""Watchlist reports: monday | earnings | flows | picks | friday.

Usage:  python reports.py <kind> [--watchlist watchlist.json] [--demo] [--send]
The ticker list lives in watchlist.json ({"tickers": [...]}) or the WATCHLIST env var
(comma separated, handy for CI). Email settings are the same as daily_report.py.
Politician trades need a JSON feed in POLITICIAN_TRADES_URL (list of objects with
ticker, politician, type, amount, date); without it that section says so. All output is
rule-based hints from public data - not investment advice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from concurrent.futures import ThreadPoolExecutor
from statistics import mean

import numpy as np
import pandas as pd

from analysis import ma_stats
from daily_report import day_change, send_email
from data_sources import DemoSource, YahooSource
from universe import candidates

BENCH = "SPY"


# ---------- data ----------
class WatchSource(YahooSource):
    def earnings(self, t):
        """DataFrame indexed by date: 'EPS Estimate', 'Reported EPS', 'Surprise(%)'. Includes future dates."""
        try:
            df = self._yf.Ticker(t).get_earnings_dates(limit=20)
            return df.copy() if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def insiders(self, t):
        """Rows: date, insider, position, shares, value, text."""
        try:
            df = self._yf.Ticker(t).insider_transactions
        except Exception:
            return []
        if df is None or df.empty:
            return []
        out = []
        for _, r in df.iterrows():
            out.append({"date": pd.to_datetime(r.get("Start Date")), "insider": r.get("Insider", ""),
                        "position": r.get("Position", ""), "shares": r.get("Shares") or 0,
                        "value": r.get("Value") or 0, "text": str(r.get("Text", "") or "")})
        return out

    def news_dated(self, t):
        try:
            items = self._yf.Ticker(t).news or []
        except Exception:
            return []
        out = []
        for it in items:
            c = it.get("content", it)
            when = c.get("pubDate") or c.get("providerPublishTime")
            ts = pd.to_datetime(when, unit="s", utc=True) if isinstance(when, (int, float)) else pd.to_datetime(when, utc=True, errors="coerce")
            if c.get("title"):
                out.append({"title": c["title"], "publisher": (c.get("provider") or {}).get("displayName", ""), "when": ts})
        return out


class DemoWatch(DemoSource):
    def earnings(self, t):
        r = self._rng(t + "e")
        today = pd.Timestamp.today().normalize()
        dates = [today + pd.Timedelta(days=3)] + [today - pd.Timedelta(days=91 * i + 20) for i in range(12)]
        est = r.uniform(1, 3, len(dates))
        sur = r.normal(4, 6, len(dates))
        rep = est * (1 + sur / 100)
        rep[0] = np.nan
        sur = sur.astype(float)
        sur[0] = np.nan
        return pd.DataFrame({"EPS Estimate": est, "Reported EPS": rep, "Surprise(%)": sur}, index=pd.DatetimeIndex(dates))

    def insiders(self, t):
        r = self._rng(t + "i")
        today = pd.Timestamp.today()
        return [{"date": today - pd.Timedelta(days=int(r.integers(1, 170))), "insider": f"Exec {k}", "position": "CEO" if k == 0 else "Director",
                 "shares": int(r.integers(1000, 50000)), "value": float(r.integers(50_000, 5_000_000)),
                 "text": "Sale at price" if r.random() < 0.7 else "Purchase at price"} for k in range(5)]

    def news_dated(self, t):
        return [{"title": f"{t} demo: weekend analyst note", "publisher": "Demo Wire", "when": pd.Timestamp.now(tz="UTC")}]


# ---------- helpers ----------
def load_watchlist(path: str) -> list[str]:
    env = os.environ.get("WATCHLIST")
    tickers = [t for t in env.split(",")] if env else json.load(open(path)).get("tickers", [])
    return sorted({t.strip().upper() for t in tickers if t.strip()})


def prices_for(src, t, days=800):
    today = dt.date.today()
    return src.history(t, today - dt.timedelta(days=days), today + dt.timedelta(days=1)).dropna()


def ret_over(p: pd.Series, n: int):
    return float(p.iloc[-1] / p.iloc[-1 - n] - 1) if len(p) > n else None


def pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.1%}"


def header(title):
    return [f"# {title} - {dt.date.today():%A %d %B %Y}", ""]


DISCLAIMER = "\n_Automated summary of public data and simple rules - not investment advice._"


# ---------- monday: weekend news + catalysts ----------
def next_earnings(src, t, within_days=None):
    df = src.earnings(t)
    if df.empty:
        return None
    idx = pd.to_datetime(df.index).tz_localize(None).normalize()
    today = pd.Timestamp.today().normalize()
    fut = [d for d in idx if d >= today]
    if not fut:
        return None
    d = min(fut)
    return d if within_days is None or (d - today).days <= within_days else None


def report_monday(tickers, src):
    now = pd.Timestamp.now(tz="UTC")
    since = (now - pd.Timedelta(days=3)).normalize()  # Friday evening onward
    out = header("Monday briefing: weekend news & catalysts")
    for t in tickers:
        out.append(f"## {t}")
        news = [n for n in src.news_dated(t) if pd.notna(n["when"]) and n["when"] >= since]
        if news:
            out += [f"- {n['title']} ({n['publisher']}, {n['when']:%a %H:%M} UTC)" for n in news[:5]]
        else:
            out.append("- No new headlines since Friday.")
        try:
            p = prices_for(src, t, 120)
            out.append(f"- Last close {p.iloc[-1]:,.2f}; last 5 days {pct(ret_over(p, 5))}.")
        except Exception as e:
            out.append(f"- Price data unavailable: {e}")
        ne = next_earnings(src, t, 14)
        if ne is not None:
            out.append(f"- **Catalyst:** earnings on {ne:%a %d %b}.")
        out.append("")
    return "\n".join(out) + DISCLAIMER


# ---------- earnings: this week + last 12 reports ----------
def earnings_history(src, t):
    df = src.earnings(t)
    if df.empty:
        return []
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    today = pd.Timestamp.today().normalize()
    past = df[(df.index < today) & df["Reported EPS"].notna()].sort_index(ascending=False).head(12)
    try:
        p = prices_for(src, t, 4 * 365)
    except Exception:
        p = None
    rows = []
    for d, r in past.iterrows():
        move = None
        if p is not None:
            before = p[p.index.tz_localize(None) < d + pd.Timedelta(days=0)] if p.index.tz is not None else p[p.index < d]
            after = p[p.index.tz_localize(None) >= d] if p.index.tz is not None else p[p.index >= d]
            if len(before) and len(after):
                move = float(after.iloc[min(1, len(after) - 1)] / before.iloc[-1] - 1)
        rows.append({"date": d, "est": r["EPS Estimate"], "act": r["Reported EPS"], "sur": r.get("Surprise(%)"), "move": move})
    return rows


def catalyst_view(hist, est_next):
    if not hist:
        return "Not enough history to say what would be a catalyst."
    beats = [h for h in hist if h["act"] >= h["est"]]
    moves_up = [h["move"] for h in hist if h["move"] is not None and h["move"] > 0]
    moves = [abs(h["move"]) for h in hist if h["move"] is not None]
    sur = [h["sur"] for h in hist if pd.notna(h["sur"])]
    bits = [f"Beat EPS in {len(beats)}/{len(hist)} of the last reports"]
    if sur:
        bits.append(f"average surprise {mean(sur):+.1f}%")
    if moves:
        bits.append(f"typical 1-day reaction +/-{mean(moves):.1%}")
    txt = ", ".join(bits) + ". "
    if est_next is not None and sur:
        bar = est_next * (1 + mean(sur) / 100)
        txt += f"Consensus EPS {est_next:.2f}: a plain beat is the base case (the market likely prices in about {bar:.2f}); "
        txt += f"to act as a positive catalyst it probably needs to clear ~{bar:.2f} AND come with solid guidance. "
    if moves_up and len(moves_up) / max(len(moves), 1) < 0.4:
        txt += "Note: the stock often falls even after beats, so guidance matters more than the EPS number."
    return txt


def report_earnings(tickers, src):
    out = header("Earnings this week")
    today = pd.Timestamp.today().normalize()
    week_end = today + pd.Timedelta(days=7 - today.weekday())
    due = []
    for t in tickers:
        ne = next_earnings(src, t)
        if ne is not None and ne <= week_end:
            due.append((ne, t))
    if not due:
        return "\n".join(out + ["No watchlist companies report this week."]) + DISCLAIMER
    for ne, t in sorted(due):
        df = src.earnings(t)
        idx = pd.to_datetime(df.index).tz_localize(None).normalize()
        est = df.loc[idx == ne, "EPS Estimate"]
        est = float(est.iloc[0]) if len(est) and pd.notna(est.iloc[0]) else None
        hist = earnings_history(src, t)
        out.append(f"## {t} - reports {ne:%a %d %b}" + (f" (consensus EPS {est:.2f})" if est else ""))
        out.append("| Date | EPS est | EPS actual | Surprise | 1-day move |\n|---|---|---|---|---|")
        for h in hist:
            out.append(f"| {h['date']:%Y-%m-%d} | {h['est']:.2f} | {h['act']:.2f} | {h['sur']:+.1f}% | {pct(h['move'])} |"
                       if pd.notna(h["sur"]) else f"| {h['date']:%Y-%m-%d} | {h['est']:.2f} | {h['act']:.2f} | n/a | {pct(h['move'])} |")
        out += ["", "**What it needs to announce:** " + catalyst_view(hist, est), ""]
    return "\n".join(out) + DISCLAIMER


# ---------- flows: insiders + politicians ----------
def insider_summary(rows, days=180):
    cut = pd.Timestamp.today() - pd.Timedelta(days=days)
    buy = sell = 0.0
    ceo = []
    for r in rows:
        if pd.isna(r["date"]) or r["date"] < cut:
            continue
        txt = r["text"].lower()
        sign = 1 if "purchase" in txt or "buy" in txt else -1 if "sale" in txt or "sold" in txt else 0
        v = float(r["value"] or 0)
        buy += v if sign > 0 else 0
        sell += v if sign < 0 else 0
        if sign and any(k in r["position"].lower() for k in ("ceo", "chief executive", "cfo", "chief financial")):
            ceo.append(f"{r['position']} {r['insider']} {'bought' if sign > 0 else 'sold'} ${v:,.0f} on {r['date']:%Y-%m-%d}")
    return buy, sell, ceo


def politician_trades(tickers):
    url = os.environ.get("POLITICIAN_TRADES_URL")
    if not url:
        return None
    import urllib.request
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    return [d for d in data if str(d.get("ticker", "")).upper() in tickers]


def report_flows(tickers, src):
    out = header("Big money flows: insiders & politicians")
    out += ["## Corporate insiders (last 180 days)", "| Ticker | Insider buys | Insider sells | Net | Signal |", "|---|---|---|---|---|"]
    notes = []
    for t in tickers:
        buy, sell, ceo = insider_summary(src.insiders(t))
        net = buy - sell
        sig = "buying" if net > 0 else "heavy selling" if sell > 2 * max(buy, 1) and sell > 1e6 else "selling" if net < 0 else "quiet"
        out.append(f"| {t} | ${buy:,.0f} | ${sell:,.0f} | ${net:+,.0f} | {sig} |")
        notes += [f"- {t}: {c}" for c in ceo[:3]]
    out += ["", "Executive (CEO/CFO) transactions:"] + (notes or ["- none found"])
    out += ["", "_Selling is weak evidence (taxes, scheduled 10b5-1 plans); open-market buying is the stronger signal._", "",
            "## Politicians (Trump, Congress, ...)"]
    try:
        pol = politician_trades(set(tickers))
    except Exception as e:
        pol = None
        out.append(f"Feed failed: {e}")
    if pol is None:
        out.append("No politician-trade feed configured. Set POLITICIAN_TRADES_URL to a JSON feed "
                   "(ticker, politician, type, amount, date). Disclosures are filed up to 45 days late.")
    elif not pol:
        out.append("No disclosed politician trades for your tickers.")
    else:
        out += [f"- {d.get('date')}: {d.get('politician')} {d.get('type')} {d['ticker']} ({d.get('amount')})" for d in pol[:40]]
    return "\n".join(out) + DISCLAIMER


# ---------- picks: monthly, 3 horizons, ranked by risk ----------
def metrics(src, t, full=True):
    """full=False skips the slow earnings/insider calls (used to pre-screen outside candidates)."""
    p = prices_for(src, t)
    r = p.pct_change().dropna()
    st = ma_stats(p)
    sur, buy, sell = [], 0, 0
    if full:
        sur = [h["sur"] for h in earnings_history(src, t) if pd.notna(h["sur"])]
        buy, sell, _ = insider_summary(src.insiders(t))
    return {"t": t, "m1": ret_over(p, 21) or 0, "m6": ret_over(p, 126) or 0, "y1": ret_over(p, 252) or 0,
            "vol": float(r.tail(252).std() * np.sqrt(252)), "dd": float((p.tail(252) / p.tail(252).cummax() - 1).min()),
            "vs_ma": (st["price"] / st["ma52"] - 1) if st.get("ma52") else 0, "sur": mean(sur) if sur else 0,
            "net_ins": 1 if buy > sell else -1 if sell > 2 * max(buy, 1) else 0, "price": st["price"]}


SCORES = {
    "Short term (weeks)": lambda m: m["m1"] * 2 + m["vs_ma"] + m["sur"] / 100,
    "Mid term (3-12 months)": lambda m: m["m6"] + m["y1"] * 0.5 + m["sur"] / 50 + 0.05 * m["net_ins"] - 0.3 * m["dd"] * -1,
    "Long term (3+ years)": lambda m: m["vs_ma"] + m["y1"] * 0.3 - m["vol"] * 0.8 + m["dd"] + 0.05 * m["net_ins"],
}


SHORTLIST = 6  # outside candidates kept per horizon after the cheap price-only screen


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception:
        return None


def report_picks(tickers, src):
    out = header("Monthly top picks")
    wl = set(tickers)
    ms = [m for m in map(lambda t: _safe(metrics, src, t), tickers) if m]
    scope_all = os.environ.get("PICKS_SCOPE", "all") != "watchlist"
    n_out = 0
    if scope_all:
        extra = candidates(src, tickers)
        with ThreadPoolExecutor(max_workers=8) as ex:
            cheap = [m for m in ex.map(lambda t: _safe(metrics, src, t, False), extra) if m]
        short = {m["t"] for f in SCORES.values() for m in sorted(cheap, key=f, reverse=True)[:SHORTLIST]}
        with ThreadPoolExecutor(max_workers=8) as ex:
            full = [m for m in ex.map(lambda t: _safe(metrics, src, t), sorted(short)) if m]
        ms += full
        n_out = len(cheap)
    if not ms:
        return "\n".join(out + ["Not enough data (is the watchlist empty?)."]) + DISCLAIMER
    picks = []
    for horizon, f in SCORES.items():
        m = max(ms, key=f)
        risk = m["vol"] * 0.6 + abs(m["dd"]) * 0.4
        picks.append((risk, horizon, m))
    out += [f"Scanned {len(tickers)} watchlist names" + (f" + {n_out} outside candidates (broad universe & Yahoo screeners)" if scope_all else " (watchlist only)") + ".",
            "Ranked from MOST to LEAST risky (risk = volatility + max drawdown over 1y):", ""]
    for i, (risk, horizon, m) in enumerate(sorted(picks, key=lambda x: -x[0]), 1):
        tag = "" if m["t"] in wl else " - NEW, not in your watchlist"
        out.append(f"{i}. **{horizon}: {m['t']}**{tag} (risk score {risk:.2f}) - 1m {pct(m['m1'])}, 6m {pct(m['m6'])}, 1y {pct(m['y1'])}, "
                   f"vs 52w MA {pct(m['vs_ma'])}, vol {m['vol']:.0%}, max drawdown {pct(m['dd'])}, avg EPS surprise {m['sur']:+.1f}%.")
    out += ["", "Picks come from your watchlist plus a broad universe, using momentum, trend, earnings surprises and insider flow. "
            "Short-term favours momentum, mid-term earnings quality + 6-12m trend, long-term trend with low volatility. "
            "Set PICKS_SCOPE=watchlist to restrict to your own list."]
    return "\n".join(out) + DISCLAIMER


# ---------- friday: week in review ----------
def report_friday(tickers, src):
    out = header("Weekly review")
    rows = []
    try:
        bench = ret_over(prices_for(src, BENCH, 60), 5)
    except Exception:
        bench = None
    for t in tickers:
        try:
            p = prices_for(src, t, 120)
            vol = src.volume(t).dropna()
            ratio = float(vol.iloc[-5:].mean() / vol.iloc[-25:-5].mean())
            rows.append((t, ret_over(p, 5), ratio, max(abs(x) for x in p.pct_change().tail(5).dropna())))
        except Exception:
            pass
    out.append(f"Market ({BENCH}) this week: {pct(bench)}")
    out += ["", "| Ticker | Week | vs market | Volume vs avg | Biggest 1-day move |", "|---|---|---|---|---|"]
    for t, w, ratio, big in sorted(rows, key=lambda r: -(r[1] or 0)):
        out.append(f"| {t} | {pct(w)} | {pct(w - bench) if bench is not None and w is not None else 'n/a'} | {ratio:.1f}x | {big:.1%} |")
    shook = [r for r in rows if r[3] >= 0.05 or r[2] >= 1.5]
    out += ["", "## Events that shook things"]
    if shook:
        for t, w, ratio, big in shook:
            heads = [n["title"] for n in src.news_dated(t)[:2]]
            out.append(f"- **{t}**: biggest daily move {big:.1%}, volume {ratio:.1f}x" + ("; " + " | ".join(heads) if heads else ""))
    else:
        out.append("- No watchlist name had a 5%+ daily move or unusual volume.")
    out += ["", "## Next week"]
    nxt = [(next_earnings(src, t, 7), t) for t in tickers]
    nxt = sorted((d, t) for d, t in nxt if d is not None)
    out += [f"- {t} reports {d:%a %d %b}" for d, t in nxt] or ["- No watchlist earnings."]
    return "\n".join(out) + DISCLAIMER


REPORTS = {"monday": report_monday, "earnings": report_earnings, "flows": report_flows,
           "picks": report_picks, "friday": report_friday}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", type=str.strip, choices=list(REPORTS) + ["monday-all"])  # strip: manual-dispatch input may carry a trailing space
    ap.add_argument("--watchlist", default="watchlist.json")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()
    tickers = load_watchlist(a.watchlist)
    if not tickers:
        raise SystemExit("Watchlist is empty - add tickers to watchlist.json")
    src = DemoWatch() if a.demo else WatchSource()
    kinds = ["monday", "earnings", "flows"] if a.kind == "monday-all" else [a.kind]
    text = "\n\n---\n\n".join(REPORTS[k](tickers, src) for k in kinds)
    print(text)
    if a.send:
        send_email(text, f"{a.kind} report {dt.date.today():%Y-%m-%d}")


if __name__ == "__main__":
    main()
