"""Streamlit UI: enter tickers -> Q4 analysis for the last 3 years, grouped by category."""
import pandas as pd
import streamlit as st

from analysis import analyse, last_completed_q4_years
from categories import CATEGORIES
from daily_report import Holding, build_lines, render_text
from data_sources import DemoSource, YahooSource

st.set_page_config(page_title="Q4 Ticker Analyzer", layout="wide")
st.title("Q4 Ticker Analyzer")

with st.sidebar:
    raw = st.text_area("Tickers (comma, space or newline separated)",
                       "AAPL, JPM, PFE, XOM, SPY, GLD, BTC-USD", height=120)
    n_years = st.slider("Number of past Q4s", 1, 10, 3)
    demo = st.checkbox("Demo mode (fake offline data)", value=False)
    run = st.button("Analyse", type="primary")

tab_q4, tab_pf = st.tabs(["Q4 analysis", "My portfolio & daily report"])

if run:
    tickers = list(dict.fromkeys(t for t in raw.replace(",", " ").upper().split() if t))
    years = last_completed_q4_years(n_years)
    source = DemoSource() if demo else YahooSource()
    reports = []
    bar = st.progress(0.0)
    for i, t in enumerate(tickers):
        reports.append(analyse(t, years, source))
        bar.progress((i + 1) / len(tickers))
    bar.empty()
    st.session_state["reports"], st.session_state["years"] = reports, years

with tab_q4:
    reports = st.session_state.get("reports")
    if reports:
        years = st.session_state["years"]
        st.caption(f"Q4 = Oct 1 – Dec 31, return measured from the Sept 30 close. Years: {', '.join(map(str, years))}.")
        ok = [r for r in reports if not r.error]

        rows = [{"Category": r.category, "Ticker": r.ticker, "Name": r.name,
                 "Price": r.price, "52w MA": r.ma52, "vs 52w MA": r.vs_ma52,
                 **{f"Q4 {q.year}": q.ret for q in r.quarters},
                 "Avg": r.avg_return, "Up years": r.hit_rate} for r in ok]
        if rows:
            df = pd.DataFrame(rows)
            order = {c: i for i, c in enumerate(CATEGORIES)}
            df = df.sort_values(["Category", "Avg"], key=lambda s: s.map(order) if s.name == "Category" else s,
                                ascending=[True, False])
            pct = {c: "{:+.1%}" for c in df.columns if c.startswith("Q4 ") or c in ("Avg", "vs 52w MA")}
            pct.update({"Price": "{:,.2f}", "52w MA": "{:,.2f}"})
            st.subheader("Overview")
            st.dataframe(df.style.format({**pct, "Up years": "{:.0%}"}, na_rep="–"),
                         width="stretch", hide_index=True)

            st.subheader("Summaries by category")
            for cat in [c for c in CATEGORIES if c in set(df["Category"])]:
                with st.expander(cat, expanded=True):
                    for r in (x for x in ok if x.category == cat):
                        st.markdown(f"**{r.ticker}** · {r.name}  \n{r.summary}")

        for r in reports:
            if r.error:
                st.warning(f"{r.ticker}: {r.error}")
    else:
        st.info("Enter tickers in the sidebar and click **Analyse**.")

with tab_pf:
    st.write("One holding per line: `TICKER shares cost-per-share` (shares and cost optional).")
    pf_raw = st.text_area("Holdings", "AAPL 10 150\nJPM 5 140", height=120)
    if st.button("Preview today's report"):
        holdings = []
        for ln in pf_raw.splitlines():
            parts = ln.replace(",", " ").split()
            if parts:
                holdings.append(Holding(parts[0].upper(),
                                        float(parts[1]) if len(parts) > 1 else 0,
                                        float(parts[2]) if len(parts) > 2 else None))
        with st.spinner("Fetching prices and news..."):
            lines = build_lines(holdings, DemoSource() if demo else YahooSource())
        st.code(render_text(lines), language=None)
    st.caption("To get this by email every weekday, see 'Daily email report' in the README.")
