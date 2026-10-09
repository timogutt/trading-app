import datetime as dt

import pandas as pd

from analysis import analyse, last_completed_q4_years, q4_revenue_growth, q4_stats
from categories import categorize
from data_sources import DemoSource


def test_years():
    assert last_completed_q4_years(3, dt.date(2026, 10, 9)) == [2023, 2024, 2025]


def test_q4_return_uses_sept30_baseline():
    idx = pd.bdate_range("2024-09-01", "2024-12-31")
    s = pd.Series(100.0, index=idx)
    s[s.index >= "2024-10-01"] = 110.0
    (q,) = q4_stats(s, [2024])
    assert abs(q.ret - 0.10) < 1e-9 and q.max_drawdown == 0


def test_short_history_skipped():
    s = pd.Series(1.0, index=pd.bdate_range("2024-12-01", "2024-12-31"))
    assert q4_stats(s, [2024]) == []


def test_revenue_growth_only_december_quarters():
    df = pd.DataFrame({pd.Timestamp("2024-12-31"): [120.0], pd.Timestamp("2023-12-31"): [100.0],
                       pd.Timestamp("2024-09-30"): [999.0]}, index=["Total Revenue"])
    assert abs(q4_revenue_growth(df, [2024])[2024] - 0.2) < 1e-9


def test_categories():
    assert categorize("BTC-USD") == "Crypto"
    assert categorize("GC=F") == "Commodities"
    assert categorize("SPY", {"quoteType": "ETF"}) == "ETF"
    assert categorize("GLD", {"quoteType": "ETF"}) == "Commodities"
    assert categorize("PFE", {"sector": "Healthcare"}) == "Healthcare"
    assert categorize("JPM", {"sector": "Financial Services"}) == "Banking & Finance"


def test_analyse_demo_and_error():
    r = analyse("AAPL", [2023, 2024, 2025], DemoSource())
    assert len(r.quarters) == 3 and r.category == "Tech" and r.summary
    class Broken(DemoSource):
        def history(self, *a): raise ValueError("No price data")
    assert analyse("ZZZZ", [2024], Broken()).error
