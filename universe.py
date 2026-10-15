"""Candidate universe for monthly picks beyond the user's watchlist.

A built-in list of liquid names across categories, plus (best effort) Yahoo's predefined screeners.
Edit UNIVERSE freely. Screener failures are ignored - the built-in list is always available.
"""
UNIVERSE = {
    "Tech": "AAPL MSFT NVDA GOOGL META AMZN AVGO ORCL CRM ADBE AMD QCOM TXN NOW PANW CRWD SNOW PLTR NFLX UBER SHOP",
    "Semis & AI": "TSM ASML MU AMAT LRCX KLAC ARM MRVL SMCI VRT ANET",
    "Healthcare": "LLY NVO UNH JNJ ABBV MRK PFE TMO ISRG VRTX REGN AMGN ABT DHR",
    "Banking & Finance": "JPM BAC WFC GS MS C V MA BRK-B BLK SCHW AXP",
    "Energy": "XOM CVX COP SLB OXY EOG",
    "Consumer": "WMT COST HD MCD NKE SBUX TSLA PG KO PEP LVMH.PA",
    "Industrials": "CAT DE GE RTX LMT BA HON UNP ETN",
    "Europe": "ASML.AS SAP.DE SIE.DE NESN.SW NOVN.SW MC.PA OR.PA",
    "ETF": "SPY QQQ IWM VTI VGK EEM XLK XLF XLV XLE SMH ARKK",
    "Commodities": "GLD SLV USO UNG COPX URA DBC GC=F SI=F HG=F",
    "Crypto": "BTC-USD ETH-USD SOL-USD IBIT",
}
SCREENERS = ["day_gainers", "most_actives", "growth_technology_stocks", "undervalued_growth_stocks",
             "undervalued_large_caps", "aggressive_small_caps"]


def builtin() -> list[str]:
    return sorted({t for group in UNIVERSE.values() for t in group.split()})


def screener_tickers(yf, per_screen: int = 15) -> list[str]:
    """Best-effort Yahoo screener symbols; returns [] if the API is unavailable."""
    out = []
    for name in SCREENERS:
        try:
            res = yf.screen(name, count=per_screen)
            out += [q["symbol"] for q in res.get("quotes", []) if q.get("symbol")]
        except Exception:
            continue
    return out


def candidates(src, watchlist: list[str]) -> list[str]:
    """Universe minus the watchlist (those are always scored anyway)."""
    extra = builtin()
    yf = getattr(src, "_yf", None)
    if yf is not None:
        extra += screener_tickers(yf)
    wl = set(watchlist)
    return sorted({t.upper() for t in extra} - wl)
