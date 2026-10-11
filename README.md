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

## 52-week moving average
The overview shows price, 52-week SMA (252 trading days), and % above/below it; the summary mentions the trend.

## Daily email report
`daily_report.py` reports, for each holding, today's move, P/L, distance to the 52w MA, a rule-based
hint at *why* it moved (market-wide vs stock-specific vs `SPY`, unusual volume, 52w-MA crossover) and recent headlines.

```
cp portfolio.example.json portfolio.json      # your holdings (git-ignored)
python daily_report.py --demo                 # preview with fake data
export SMTP_HOST=smtp.gmail.com SMTP_USER=you@gmail.com SMTP_PASS=<app-password> REPORT_TO=you@gmail.com
python daily_report.py --send                 # email it (run daily via cron)
```
Automatic option: `.github/workflows/daily-report.yml` sends it every weekday. Add the repo secrets
`PORTFOLIO_JSON` (the JSON contents), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `REPORT_TO`.
Use an app password, never your main password. The "why" is a hint from correlations, not a verified cause.

## Watchlist reports
Add tickers to `watchlist.json` (`{"tickers": ["AAPL", "JPM"]}`) or set the repo variable `WATCHLIST` (comma separated).
`python reports.py <kind> [--demo] [--send]`:

| kind | when (workflow) | content |
|---|---|---|
| `monday` | Mon | weekend headlines, 5-day move, earnings catalysts in the next 14 days |
| `earnings` | Mon | watchlist reports due this week, their last 12 reports (EPS est/actual/surprise, 1-day move) and what the new report needs to be a catalyst |
| `flows` | Mon | insider buying/selling (CEO/CFO highlighted) + politician trades (needs `POLITICIAN_TRADES_URL` JSON feed) |
| `picks` | 1st of month | top pick per horizon (short/mid/long) ranked most to least risky |
| `friday` | Fri | week vs market, volume spikes, events that shook names, next week's earnings |

`monday-all` = monday + earnings + flows. Schedules: `.github/workflows/watchlist-reports.yml`. Not financial advice.
