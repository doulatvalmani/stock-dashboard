import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Stock Dashboard", layout="centered")

st.title("📊 Stock Analysis Dashboard")

ticker = st.text_input("Enter Stock Ticker", "AAPL").strip().upper()


# Cache the download itself for 10 minutes, so even if the fragment below
# reruns, it won't re-hit Yahoo Finance more often than that.
@st.cache_data(ttl=600)
def load_data(symbol):
    return yf.download(symbol, period="6mo", interval="1d")


# This fragment auto-reruns every 10 minutes on its own, without any
# user interaction, and without needing to restart Streamlit.
@st.fragment(run_every="10m")
def render_dashboard(ticker):

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Download data
    with st.spinner(f"Fetching data for {ticker}..."):
        data = load_data(ticker)

    # FIX 1: No data / invalid ticker
    if data.empty:
        st.error(f"No data found for ticker '{ticker}'. Please check the symbol and try again.")
        st.stop()

    # FIX 2: Flatten MultiIndex columns (yfinance sometimes returns
    # columns like ('Close', 'AAPL') even for a single ticker)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Ensure Close exists
    if "Close" not in data.columns:
        st.error("Close price not found in data. The ticker symbol may be invalid.")
        st.stop()

    # Moving averages
    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()

    # FIX 3: Only drop rows missing MA50 (need 50 days of history).
    # Using plain dropna() on the whole frame can wipe everything out
    # if the ticker has less than 50 days of data (e.g. recent IPO).
    chart_data = data.dropna(subset=["MA50"])

    if chart_data.empty:
        st.warning(
            f"Not enough trading history for {ticker} to compute a 50-day moving average. "
            "Showing available price data instead."
        )
        chart_data = data.dropna(subset=["Close"])

    latest = data.iloc[-1]

    # FIX 4: Safe scalar extraction, with NaN guards for MA20/MA50
    price = float(latest["Close"])
    ma20 = float(latest["MA20"]) if pd.notna(latest["MA20"]) else None
    ma50 = float(latest["MA50"]) if pd.notna(latest["MA50"]) else None

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Current Price", f"${price:.2f}")
    with col2:
        st.metric("MA20", f"${ma20:.2f}" if ma20 is not None else "N/A")
    with col3:
        st.metric("MA50", f"${ma50:.2f}" if ma50 is not None else "N/A")

    st.subheader("Price Chart")

    # FIX 5: Only chart columns that actually have data
    chart_cols = [c for c in ["Close", "MA20", "MA50"] if chart_data[c].notna().any()]
    st.line_chart(chart_data[chart_cols])

    # Optional: raw data viewer
    with st.expander("View raw data"):
        st.dataframe(data.tail(50))


if ticker:
    render_dashboard(ticker)
else:
    st.info("Enter a stock ticker above to get started.")
