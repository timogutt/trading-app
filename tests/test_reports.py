import reports
from reports import DemoWatch

T = ["AAPL", "JPM", "PFE"]


def test_all_reports_run_in_demo():
    for k, f in reports.REPORTS.items():
        assert len(f(T, DemoWatch())) > 50, k


def test_earnings_this_week_and_history():
    txt = reports.report_earnings(T, DemoWatch())
    assert "What it needs to announce" in txt or "No watchlist companies" in txt
    assert len(reports.earnings_history(DemoWatch(), "AAPL")) == 12


def test_picks_ranked_by_risk():
    txt = reports.report_picks(T, DemoWatch())
    assert "MOST to LEAST risky" in txt and txt.count("**") >= 6


def test_insider_summary():
    buy, sell, _ = reports.insider_summary(DemoWatch().insiders("AAPL"))
    assert buy >= 0 and sell >= 0
