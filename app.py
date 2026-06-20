import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Stock Dashboard", layout="wide")

st.title("📊 Stock Analysis Dashboard")

# Fallback list used only if the live Yahoo search API is unavailable
FALLBACK_COMPANIES = {
    "apple": "AAPL", "tesla": "TSLA", "microsoft": "MSFT", "google": "GOOGL",
    "alphabet": "GOOGL", "amazon": "AMZN", "meta": "META", "facebook": "META",
    "netflix": "NFLX", "nvidia": "NVDA", "intel": "INTC", "amd": "AMD",
    "ibm": "IBM", "oracle": "ORCL", "salesforce": "CRM", "adobe": "ADBE",
    "paypal": "PYPL", "uber": "UBER", "disney": "DIS", "coca cola": "KO",
    "pepsi": "PEP", "walmart": "WMT", "nike": "NKE", "starbucks": "SBUX",
    "boeing": "BA", "jpmorgan": "JPM", "visa": "V", "mastercard": "MA",
}

PERIOD_OPTIONS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "5 Years": "5y",
}


@st.cache_data(ttl=600)
def search_company(query):
    """Look up a company name and return possible ticker matches."""
    try:
        results = yf.Search(query, max_results=5).quotes
        matches = [
            {"symbol": r.get("symbol"), "name": r.get("shortname") or r.get("longname") or ""}
            for r in results if r.get("symbol")
        ]
        if matches:
            return matches
    except Exception:
        pass

    key = query.strip().lower()
    if key in FALLBACK_COMPANIES:
        return [{"symbol": FALLBACK_COMPANIES[key], "name": query.title()}]
    return []


@st.cache_data(ttl=600)
def load_data(symbol, period):
    return yf.download(symbol, period=period, interval="1d")


def resolve_input(raw, period):
    raw = raw.strip()
    candidate = raw.upper()

    data = load_data(candidate, period)
    if not data.empty:
        return candidate, candidate, []

    matches = search_company(raw)
    if matches:
        best = matches[0]
        symbol = best["symbol"]
        name = best["name"] or symbol
        check = load_data(symbol, period)
        if not check.empty:
            return symbol, name, matches
    return None, None, matches


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def prep_dataframe(data):
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.copy()
    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["RSI"] = compute_rsi(data["Close"])
    bb_std = data["Close"].rolling(20).std()
    data["BB_Upper"] = data["MA20"] + 2 * bb_std
    data["BB_Lower"] = data["MA20"] - 2 * bb_std
    return data


@st.cache_data(ttl=600)
def get_news(symbol):
    """Fetch recent news headlines for a ticker. Returns list of (title, link, publisher)."""
    try:
        items = yf.Ticker(symbol).news or []
    except Exception:
        return []

    results = []
    for item in items[:5]:
        content = item.get("content", item)
        title = content.get("title") or item.get("title") or "Untitled"
        link = None
        canonical = content.get("canonicalUrl")
        if isinstance(canonical, dict):
            link = canonical.get("url")
        link = link or content.get("link") or item.get("link")
        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher") or item.get("publisher")
        results.append((title, link, publisher))
    return results


# ---------------- Sidebar: date range + watchlist ----------------
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []

with st.sidebar:
    st.header("Settings")

    range_label = st.selectbox("Date range", list(PERIOD_OPTIONS.keys()), index=2)
    period = PERIOD_OPTIONS[range_label]

    st.divider()
    st.header("⭐ Watchlist")

    if st.session_state.watchlist:
        for wl_symbol in st.session_state.watchlist:
            c1, c2 = st.columns([3, 1])
            c1.write(wl_symbol)
            if c2.button("✕", key=f"remove_{wl_symbol}"):
                st.session_state.watchlist.remove(wl_symbol)
                st.rerun()
        if st.button("Load watchlist"):
            st.session_state.load_watchlist = True
            st.rerun()
        if st.button("Clear watchlist"):
            st.session_state.watchlist = []
            st.rerun()
    else:
        st.caption("No saved tickers yet. Add some below.")

    st.caption("Note: watchlist is saved for this browser session only and resets if you close the tab.")

# ---------------- Main input ----------------
default_input = ", ".join(st.session_state.watchlist) if st.session_state.get("load_watchlist") else "AAPL, Tesla, Microsoft"
st.session_state.load_watchlist = False

raw_input = st.text_input(
    "Enter ticker(s) or company name(s) — separate multiple with commas",
    default_input,
)

entries = [t.strip() for t in raw_input.split(",") if t.strip()]

resolved = []
failed = []

for entry in entries:
    symbol, name, suggestions = resolve_input(entry, period)
    if symbol:
        resolved.append((symbol, name))
    else:
        failed.append((entry, suggestions))

for original, suggestions in failed:
    if suggestions:
        options = ", ".join(f"{s['symbol']} ({s['name']})" for s in suggestions[:3])
        st.warning(f"Couldn't find an exact match for **{original}**. Did you mean: {options}?")
    else:
        st.error(f"No matches found for **{original}**. Check the spelling or try the ticker symbol directly.")

if not resolved:
    st.info("Enter at least one valid ticker or company name above to see the dashboard.")
    st.stop()

# Add-to-watchlist buttons
wl_cols = st.columns(len(resolved))
for col, (symbol, name) in zip(wl_cols, resolved):
    if symbol in st.session_state.watchlist:
        col.caption(f"⭐ {symbol} saved")
    else:
        if col.button(f"☆ Save {symbol}", key=f"save_{symbol}"):
            st.session_state.watchlist.append(symbol)
            st.rerun()


@st.fragment(run_every="10m")
def render_dashboard(resolved_tickers, period):

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Range: {range_label}")

    all_data = {}
    for symbol, name in resolved_tickers:
        with st.spinner(f"Fetching {symbol}..."):
            raw = load_data(symbol, period)
        if raw.empty:
            st.error(f"No data available for {symbol} right now.")
            continue
        all_data[symbol] = {"name": name, "df": prep_dataframe(raw)}

    if not all_data:
        st.stop()

    # ---- Summary metrics row ----
    cols = st.columns(len(all_data))
    for col, (symbol, info) in zip(cols, all_data.items()):
        df = info["df"]
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        price = float(latest["Close"])
        change_pct = ((price - float(prev["Close"])) / float(prev["Close"])) * 100 if len(df) > 1 else 0

        open_p = float(latest["Open"])
        high_p = float(latest["High"])
        low_p = float(latest["Low"])
        volume = int(latest["Volume"])
        rsi = latest["RSI"]
        ma20 = latest["MA20"]
        ma50 = latest["MA50"]

        with col:
            st.metric(f"{symbol} — {info['name']}", f"${price:.2f}", f"{change_pct:+.2f}%")
            st.caption(f"MA20: ${ma20:.2f}" if pd.notna(ma20) else "MA20: N/A")
            st.caption(f"MA50: ${ma50:.2f}" if pd.notna(ma50) else "MA50: N/A")
            if pd.notna(rsi):
                rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
                st.caption(f"RSI(14): {rsi:.1f} ({rsi_label})")
            else:
                st.caption("RSI(14): N/A")
            st.caption(f"Open: ${open_p:.2f}  •  High: ${high_p:.2f}  •  Low: ${low_p:.2f}")
            st.caption(f"Volume: {volume:,}")

    # ---- Portfolio Tracker ----
    with st.expander("💼 Portfolio Tracker — enter shares & buy price to see gain/loss"):
        st.caption("Values are not saved permanently — they reset if you close this tab.")
        portfolio_rows = []
        pf_cols = st.columns(len(all_data))
        for pf_col, (symbol, info) in zip(pf_cols, all_data.items()):
            with pf_col:
                st.markdown(f"**{symbol}**")
                shares = st.number_input(
                    f"Shares owned", min_value=0.0, value=0.0, step=1.0, key=f"shares_{symbol}"
                )
                buy_price = st.number_input(
                    f"Avg buy price ($)", min_value=0.0, value=0.0, step=0.01, key=f"buyprice_{symbol}"
                )
                if shares > 0 and buy_price > 0:
                    current_price = float(info["df"]["Close"].iloc[-1])
                    cost = shares * buy_price
                    value = shares * current_price
                    gain = value - cost
                    gain_pct = (gain / cost) * 100
                    st.metric("Current Value", f"${value:,.2f}", f"{gain_pct:+.2f}%")
                    st.caption(f"Cost basis: ${cost:,.2f}  •  Gain/Loss: ${gain:,.2f}")
                    portfolio_rows.append({"symbol": symbol, "cost": cost, "value": value})

        if portfolio_rows:
            total_cost = sum(r["cost"] for r in portfolio_rows)
            total_value = sum(r["value"] for r in portfolio_rows)
            total_gain = total_value - total_cost
            total_gain_pct = (total_gain / total_cost) * 100 if total_cost else 0
            st.divider()
            st.subheader("Total Portfolio")
            st.metric("Total Value", f"${total_value:,.2f}", f"{total_gain_pct:+.2f}%")
            st.caption(f"Total Cost: ${total_cost:,.2f}  •  Total Gain/Loss: ${total_gain:,.2f}")

    # ---- Comparison chart ----
    if len(all_data) > 1:
        st.subheader("Comparison — Normalized % Change")
        norm_df = pd.DataFrame({
            symbol: (info["df"]["Close"] / info["df"]["Close"].iloc[0] - 1) * 100
            for symbol, info in all_data.items()
        })
        st.line_chart(norm_df)

    # ---- Individual detailed view, one tab per ticker ----
    st.subheader("Individual Stock Details")
    tabs = st.tabs(list(all_data.keys()))
    for tab, (symbol, info) in zip(tabs, all_data.items()):
        with tab:
            df = info["df"]

            chart_data = df.dropna(subset=["MA50"])
            if chart_data.empty:
                st.warning(f"Not enough history for {symbol} to show MA50. Showing price only.")
                chart_data = df.dropna(subset=["Close"])
            chart_cols = [c for c in ["Close", "MA20", "MA50"] if chart_data[c].notna().any()]
            st.line_chart(chart_data[chart_cols])

            with st.expander("🕯️ Candlestick chart"):
                fig = go.Figure(data=[go.Candlestick(
                    x=df.index,
                    open=df["Open"], high=df["High"],
                    low=df["Low"], close=df["Close"],
                )])
                fig.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True, key=f"candle_{symbol}")

            with st.expander("📐 Bollinger Bands"):
                bb_data = df.dropna(subset=["BB_Upper", "BB_Lower"])
                if bb_data.empty:
                    st.caption("Not enough history in this date range to compute Bollinger Bands.")
                else:
                    st.caption("Bands widen during high volatility, narrow during low volatility.")
                    st.line_chart(bb_data[["Close", "BB_Upper", "BB_Lower"]])

            with st.expander(f"📰 Latest news — {symbol}"):
                news_items = get_news(symbol)
                if not news_items:
                    st.caption("No recent news found.")
                else:
                    for title, link, publisher in news_items:
                        byline = f" — *{publisher}*" if publisher else ""
                        if link:
                            st.markdown(f"- [{title}]({link}){byline}")
                        else:
                            st.markdown(f"- {title}{byline}")

            st.caption("Volume")
            st.bar_chart(df["Volume"])

            rsi_data = df.dropna(subset=["RSI"])
            if not rsi_data.empty:
                st.caption("RSI(14) — above 70 = overbought, below 30 = oversold")
                st.line_chart(rsi_data["RSI"])

            csv_bytes = df.to_csv().encode("utf-8")
            st.download_button(
                label=f"📥 Download {symbol} data as CSV",
                data=csv_bytes,
                file_name=f"{symbol}_data.csv",
                mime="text/csv",
                key=f"download_{symbol}",
            )

            with st.expander(f"View raw data — {symbol}"):
                st.dataframe(df.tail(50))


render_dashboard(resolved, period)
