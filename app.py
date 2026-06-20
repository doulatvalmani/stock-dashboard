import streamlit as st
import yfinance as yf
import pandas as pd
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

    # Fallback for common companies if live search fails or returns nothing
    key = query.strip().lower()
    if key in FALLBACK_COMPANIES:
        return [{"symbol": FALLBACK_COMPANIES[key], "name": query.title()}]
    return []


@st.cache_data(ttl=600)
def load_data(symbol):
    return yf.download(symbol, period="6mo", interval="1d")


def resolve_input(raw):
    """
    Takes raw user text (ticker OR company name) and returns:
    (resolved_symbol, display_name, suggestions_if_any)
    """
    raw = raw.strip()
    candidate = raw.upper()

    # Try treating it as a direct ticker first
    data = load_data(candidate)
    if not data.empty:
        return candidate, candidate, []

    # Otherwise treat it as a company name and search
    matches = search_company(raw)
    if matches:
        best = matches[0]
        symbol = best["symbol"]
        name = best["name"] or symbol
        check = load_data(symbol)
        if not check.empty:
            return symbol, name, matches
    return None, None, matches


def prep_dataframe(data):
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.copy()
    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    return data


raw_input = st.text_input(
    "Enter ticker(s) or company name(s) — separate multiple with commas",
    "AAPL, Tesla, Microsoft",
)

entries = [t.strip() for t in raw_input.split(",") if t.strip()]

resolved = []   # list of (symbol, display_name)
failed = []     # list of (original_text, suggestions)

for entry in entries:
    symbol, name, suggestions = resolve_input(entry)
    if symbol:
        resolved.append((symbol, name))
    else:
        failed.append((entry, suggestions))

# Show friendly errors / suggestions for anything that didn't resolve
for original, suggestions in failed:
    if suggestions:
        options = ", ".join(f"{s['symbol']} ({s['name']})" for s in suggestions[:3])
        st.warning(f"Couldn't find an exact match for **{original}**. Did you mean: {options}?")
    else:
        st.error(f"No matches found for **{original}**. Check the spelling or try the ticker symbol directly.")

if not resolved:
    st.info("Enter at least one valid ticker or company name above to see the dashboard.")
    st.stop()


@st.fragment(run_every="10m")
def render_dashboard(resolved_tickers):

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_data = {}
    for symbol, name in resolved_tickers:
        with st.spinner(f"Fetching {symbol}..."):
            raw = load_data(symbol)
        if raw.empty:
            st.error(f"No data available for {symbol} right now.")
            continue
        all_data[symbol] = {"name": name, "df": prep_dataframe(raw)}

    if not all_data:
        st.stop()

    # ---- Summary metrics row, one block per ticker ----
    cols = st.columns(len(all_data))
    for col, (symbol, info) in zip(cols, all_data.items()):
        df = info["df"]
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        price = float(latest["Close"])
        change_pct = ((price - float(prev["Close"])) / float(prev["Close"])) * 100 if len(df) > 1 else 0
        with col:
            st.metric(f"{symbol} — {info['name']}", f"${price:.2f}", f"{change_pct:+.2f}%")
            ma20 = latest["MA20"]
            ma50 = latest["MA50"]
            st.caption(f"MA20: ${ma20:.2f}" if pd.notna(ma20) else "MA20: N/A")
            st.caption(f"MA50: ${ma50:.2f}" if pd.notna(ma50) else "MA50: N/A")

    # ---- Comparison chart (normalized % change so different price scales compare fairly) ----
    if len(all_data) > 1:
        st.subheader("Comparison — Normalized % Change")
        norm_df = pd.DataFrame({
            symbol: (info["df"]["Close"] / info["df"]["Close"].iloc[0] - 1) * 100
            for symbol, info in all_data.items()
        })
        st.line_chart(norm_df)

    # ---- Individual detailed charts, one tab per ticker ----
    st.subheader("Individual Price Charts")
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
            with st.expander(f"View raw data — {symbol}"):
                st.dataframe(df.tail(50))


render_dashboard(resolved)
