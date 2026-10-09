"""Q4 (Oct-Dec) analysis over the last N completed years + a plain-language summary."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from categories import categorize


@dataclass
class QuarterStats:
    year: int
    ret: float          # Q4 price return (fraction)
    volatility: float   # annualised daily-return stdev
    max_drawdown: float # worst peak-to-trough inside the quarter (negative fraction)
    revenue_yoy: float | None = None  # Q4 revenue growth vs prior-year Q4, if known


@dataclass
class TickerReport:
    ticker: str
    name: str
    category: str
    quarters: list[QuarterStats] = field(default_factory=list)
    summary: str = ""
    error: str | None = None

    @property
    def avg_return(self) -> float | None:
        return float(np.mean([q.ret for q in self.quarters])) if self.quarters else None

    @property
    def hit_rate(self) -> float | None:
        return float(np.mean([q.ret > 0 for q in self.quarters])) if self.quarters else None


def last_completed_q4_years(n: int = 3, today: dt.date | None = None) -> list[int]:
    """Years of the last `n` completed Q4s, oldest first."""
    today = today or dt.date.today()
    latest = today.year - 1 if today <= dt.date(today.year, 12, 31) else today.year
    return list(range(latest - n + 1, latest + 1))


def q4_stats(prices: pd.Series, years: list[int]) -> list[QuarterStats]:
    """Compute Q4 stats from a daily close series. The baseline is the last close
    before Oct 1 (i.e. the Sept 30 close), so the return covers the full quarter."""
    prices = prices.dropna()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    out = []
    for y in years:
        base = prices[prices.index < pd.Timestamp(y, 10, 1)]
        q = prices[(prices.index >= pd.Timestamp(y, 10, 1)) & (prices.index <= pd.Timestamp(y, 12, 31))]
        if base.empty or len(q) < 20:  # not enough data (e.g. IPO'd mid-quarter)
            continue
        path = pd.concat([base.iloc[[-1]], q])
        rets = path.pct_change().dropna()
        dd = (path / path.cummax() - 1).min()
        out.append(QuarterStats(y, float(path.iloc[-1] / path.iloc[0] - 1),
                                float(rets.std() * np.sqrt(252)), float(dd)))
    return out


def q4_revenue_growth(quarterly_income: pd.DataFrame | None, years: list[int]) -> dict[int, float]:
    """Q4 revenue YoY growth keyed by year, from a yfinance quarterly income statement
    (columns = quarter-end dates). Only Dec quarter-ends are used, so non-calendar fiscal
    years are skipped rather than mislabelled."""
    if quarterly_income is None or quarterly_income.empty:
        return {}
    row = next((r for r in ("Total Revenue", "Operating Revenue") if r in quarterly_income.index), None)
    if row is None:
        return {}
    rev = quarterly_income.loc[row].dropna()
    rev.index = pd.to_datetime(rev.index)
    dec = {d.year: v for d, v in rev.items() if d.month == 12}
    return {y: dec[y] / dec[y - 1] - 1 for y in years if y in dec and dec.get(y - 1)}


def summarize(r: TickerReport) -> str:
    if not r.quarters:
        return "Not enough price history for the requested Q4 periods."
    wins = sum(q.ret > 0 for q in r.quarters)
    n = len(r.quarters)
    best = max(r.quarters, key=lambda q: q.ret)
    worst = min(r.quarters, key=lambda q: q.ret)
    avg_vol = np.mean([q.volatility for q in r.quarters])
    avg_dd = np.mean([q.max_drawdown for q in r.quarters])
    parts = [f"{r.ticker} rose in {wins} of {n} recent Q4s (avg {r.avg_return:+.1%}).",
             f"Best: Q4 {best.year} ({best.ret:+.1%}); worst: Q4 {worst.year} ({worst.ret:+.1%})."]
    parts.append(f"Volatility ~{avg_vol:.0%} annualised, typical in-quarter drawdown {avg_dd:.1%}.")
    growth = [q.revenue_yoy for q in r.quarters if q.revenue_yoy is not None]
    if growth:
        parts.append(f"Q4 revenue growth averaged {np.mean(growth):+.1%} YoY.")
    if wins == n and n >= 3:
        parts.append("Consistent Q4 strength.")
    elif wins == 0:
        parts.append("Q4 has been consistently weak.")
    return " ".join(parts)


def analyse(ticker: str, years: list[int], source) -> TickerReport:
    """`source` provides .history(ticker, start, end) -> close Series, .info(ticker) -> dict,
    .quarterly_income(ticker) -> DataFrame|None. See data_sources.py."""
    ticker = ticker.upper().strip()
    try:
        info = source.info(ticker)
        report = TickerReport(ticker, info.get("shortName") or info.get("longName") or ticker,
                              categorize(ticker, info))
        prices = source.history(ticker, dt.date(years[0] - 1, 9, 1), dt.date(years[-1], 12, 31))
        report.quarters = q4_stats(prices, years)
        growth = q4_revenue_growth(source.quarterly_income(ticker), years)
        for q in report.quarters:
            q.revenue_yoy = growth.get(q.year)
        report.summary = summarize(report)
    except Exception as e:  # one bad ticker shouldn't kill the batch
        report = TickerReport(ticker, ticker, "Other", error=str(e))
    return report
