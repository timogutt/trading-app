"""Data providers. YahooSource is live; DemoSource is deterministic fake data for offline use/tests."""
import hashlib

import numpy as np
import pandas as pd


class YahooSource:
    def __init__(self):
        import yfinance as yf
        self._yf = yf

    def info(self, ticker):
        try:
            return self._yf.Ticker(ticker).info or {}
        except Exception:
            return {}

    def history(self, ticker, start, end):
        h = self._yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if h.empty:
            raise ValueError(f"No price data found for '{ticker}'")
        return h["Close"]

    def quarterly_income(self, ticker):
        try:
            return self._yf.Ticker(ticker).quarterly_income_stmt
        except Exception:
            return None


class DemoSource:
    """Random-walk prices seeded by ticker, so results are stable between runs."""
    SECTORS = {"AAPL": "Technology", "JPM": "Financial Services", "PFE": "Healthcare",
               "XOM": "Energy", "SPY": None, "BTC-USD": None, "GLD": None}

    def _rng(self, ticker):
        return np.random.default_rng(int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16))

    def info(self, ticker):
        qt = "ETF" if ticker in ("SPY", "GLD") else "CRYPTOCURRENCY" if ticker.endswith("-USD") else "EQUITY"
        return {"shortName": f"{ticker} (demo)", "quoteType": qt, "sector": self.SECTORS.get(ticker)}

    def history(self, ticker, start, end):
        idx = pd.bdate_range(start, end)
        steps = self._rng(ticker).normal(0.0004, 0.015, len(idx))
        return pd.Series(100 * np.exp(np.cumsum(steps)), index=idx)

    def quarterly_income(self, ticker):
        return None
