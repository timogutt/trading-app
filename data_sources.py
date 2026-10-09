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

    def volume(self, ticker):
        h = self._yf.Ticker(ticker).history(period="3mo")
        return h["Volume"]

    def news(self, ticker):
        """Recent headlines as [{'title', 'publisher'}]; handles both yfinance news layouts."""
        try:
            items = self._yf.Ticker(ticker).news or []
        except Exception:
            return []
        out = []
        for it in items:
            c = it.get("content", it)
            title = c.get("title")
            pub = (c.get("provider") or {}).get("displayName") or c.get("publisher") or ""
            if title:
                out.append({"title": title, "publisher": pub})
        return out


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

    def volume(self, ticker):
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=60)
        v = pd.Series(self._rng(ticker + "v").integers(900_000, 1_100_000, len(idx)), index=idx)
        v.iloc[-1] *= 2  # exercise the volume-spike path
        return v

    def news(self, ticker):
        return [{"title": f"{ticker} demo headline: analysts update outlook", "publisher": "Demo Wire"}]
