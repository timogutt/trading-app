"""Streamlit UI: enter tickers -> Q4 analysis for the last 3 years, grouped by category."""
import pandas as pd
import streamlit as st

from analysis import analyse, last_completed_q4_years
from categories import CATEGORIES
from data_sources import DemoSource, YahooSource

st.set_page_config(page_title="Q4 Ticker Analyzer", layout="wide")
st.title("Q4 Ticker Analyzer")

with st.sidebar:
    raw = st.text_area("Tickers (comma, space or newline separated)",
                       "AAPL, JPM, PFE, XOM, SPY, GLD, BTC-USD", height=120)
    n_years = st.slider("Number of past Q4s", 1, 10, 3)
    demo = st.checkbox("Demo mode (fake offline data)", value=False)
    run = st.button("Analyse", type="primary")

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

reports = st.session_state.get("reports")
if reports:
    years = st.session_state["years"]
    st.caption(f"Q4 = Oct 1 – Dec 31, return measured from the Sept 30 close. Years: {', '.join(map(str, years))}.")
    ok = [r for r in reports if not r.error]

    rows = [{"Category": r.category, "Ticker": r.ticker, "Name": r.name,
             **{f"Q4 {q.year}": q.ret for q in r.quarters},
             "Avg": r.avg_return, "Up years": r.hit_rate} for r in ok]
    if rows:
        df = pd.DataFrame(rows)
        order = {c: i for i, c in enumerate(CATEGORIES)}
        df = df.sort_values(["Category", "Avg"], key=lambda s: s.map(order) if s.name == "Category" else s,
                            ascending=[True, False])
        pct = {c: "{:+.1%}" for c in df.columns if c.startswith("Q4 ") or c == "Avg"}
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
