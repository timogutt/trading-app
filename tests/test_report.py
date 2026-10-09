import pandas as pd

from daily_report import Holding, build_lines, day_change, explain, render_text
from data_sources import DemoSource


def test_day_change():
    assert abs(day_change(pd.Series([100.0, 103.0])) - 0.03) < 1e-12
    assert day_change(pd.Series([1.0])) is None


def test_explain_market_vs_specific():
    assert "market-driven" in explain(-0.02, -0.021, None, None, None)[0]
    assert "Stock-specific" in explain(0.05, 0.0, None, None, None)[0]
    assert any("volume" in r for r in explain(0.01, 0.01, 2.0, None, None))
    assert any("52-week" in r for r in explain(0.01, 0.01, None, 0.01, -0.01))


def test_report_demo_and_bad_ticker():
    class Flaky(DemoSource):
        def history(self, t, *a):
            if t == "BAD":
                raise ValueError("nope")
            return super().history(t, *a)
    lines = build_lines([Holding("AAPL", 10, 100), Holding("BAD")], Flaky())
    text = render_text(lines)
    assert "AAPL" in text and "Could not fetch data" in text
