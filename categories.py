"""Sort tickers into broad categories (Healthcare, Crypto, Banking, Tech, ETF, Commodities, ...)."""

CATEGORIES = [
    "Healthcare", "Crypto", "Banking & Finance", "Tech", "ETF",
    "Commodities", "Energy", "Consumer", "Industrials", "Real Estate & Utilities", "Other",
]

# Yahoo sector -> our category
SECTOR_MAP = {
    "Healthcare": "Healthcare",
    "Financial Services": "Banking & Finance",
    "Technology": "Tech",
    "Communication Services": "Tech",
    "Energy": "Energy",
    "Consumer Cyclical": "Consumer",
    "Consumer Defensive": "Consumer",
    "Industrials": "Industrials",
    "Basic Materials": "Commodities",
    "Real Estate": "Real Estate & Utilities",
    "Utilities": "Real Estate & Utilities",
}

# Edit freely: manual overrides always win over automatic detection.
OVERRIDES = {
    "GLD": "Commodities", "SLV": "Commodities", "USO": "Commodities", "UNG": "Commodities",
    "DBC": "Commodities", "PDBC": "Commodities", "CPER": "Commodities",
    "IBIT": "Crypto", "FBTC": "Crypto", "ETHA": "Crypto", "COIN": "Crypto", "MSTR": "Crypto",
}


def categorize(ticker: str, info: dict | None = None) -> str:
    """Return a category for `ticker`, using Yahoo `info` when available."""
    t = ticker.upper().strip()
    info = info or {}
    if t in OVERRIDES:
        return OVERRIDES[t]
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type == "CRYPTOCURRENCY" or t.endswith("-USD"):
        return "Crypto"
    if quote_type == "FUTURE" or t.endswith("=F"):
        return "Commodities"
    if quote_type in ("ETF", "MUTUALFUND"):
        return "ETF"
    return SECTOR_MAP.get(info.get("sector") or "", "Other")
