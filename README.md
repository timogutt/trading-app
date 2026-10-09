# Q4 Ticker Analyzer

Enter stock/ETF/crypto/commodity tickers; the app analyses the last N (default 3) completed Q4s
(Oct–Dec): price return, volatility, drawdown and (when available) Q4 revenue growth, then writes a
short summary per ticker and groups results by category (Healthcare, Crypto, Banking & Finance, Tech, ETF, Commodities, …).

```
pip install -r requirements.txt
streamlit run app.py
pytest
```

Data comes from Yahoo Finance via `yfinance` (tickers like `AAPL`, `BTC-USD`, `GC=F`). Tick **Demo mode** for fake offline data.
Fix a wrong category by adding it to `OVERRIDES` in `categories.py`. Not financial advice.
