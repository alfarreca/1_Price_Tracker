# app.py
import streamlit as st
import pandas as pd
from typing import List, Iterable

from data_loader import read_first_sheet_names, read_sheet, apply_sidebar_filters
from analysis import (
    fetch_all_prices, assemble_price_tables, compute_rankings,
    score_tickers, compute_drawdown_table
)
from visualization import (
    plot_price_trend, plot_normalized, plot_drawdown_bar, pie_breakdowns
)


# --------------------------- Page Config ---------------------------
st.set_page_config(page_title="Weekly Price Tracker", layout="wide")
st.title("📈 Weekly Price Tracker (Modular)")

st.caption(
    "Upload an Excel file with at least a **Symbol** column. "
    "Use the sidebar filters first, then click **Fetch Data**."
)

# --------------------------- Helpers ---------------------------
def chunk(seq: List[str], size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]

def merge_symbol_dicts(dict_list):
    out = {}
    for d in dict_list:
        out.update(d)
    return out


# --------------------------- Sidebar ---------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    force_refresh = st.checkbox("Force refresh (clear cache)", value=False,
                                help="Clears Streamlit cache before fetching new data.")
    max_batch = st.number_input(
        "Max symbols per batch",
        min_value=10, max_value=200, value=30, step=5,
        help="If you upload many symbols, fetching in batches keeps the app responsive."
    )
    st.markdown("---")
    st.write("Tip: Start with a smaller filtered set if your list is very large.")


# --------------------------- File Upload ---------------------------
uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

if not uploaded_file:
    st.info("Waiting for file…")
    st.stop()

xls = pd.ExcelFile(uploaded_file)
sheet_names = read_first_sheet_names(xls)
sheet_choice = st.selectbox("Select sheet to analyze", options=sheet_names)

if not sheet_choice:
    st.stop()

# --------------------------- Load + Filter Metadata ---------------------------
raw_df = read_sheet(xls, sheet_choice)
if "Symbol" not in raw_df.columns:
    st.error("Excel must contain a 'Symbol' column.")
    st.stop()

meta_df, selected_filters = apply_sidebar_filters(raw_df.copy(), st)

st.write("### Filtered List Preview (metadata only)")
st.dataframe(meta_df.head(25), use_container_width=True)
st.info(f"Filtered tickers: **{len(meta_df)}** (showing first 25 rows above)")

symbols = meta_df["Symbol"].dropna().astype(str).str.strip().unique().tolist()

# --------------------------- Actions ---------------------------
cols_top = st.columns([1, 1, 2])
with cols_top[0]:
    fetch_btn = st.button("🚀 Fetch Data for Filtered Symbols", type="primary")
with cols_top[1]:
    if st.button("Clear Table Output"):
        st.experimental_rerun()

if not fetch_btn:
    st.stop()

# Optional: clear cache to truly refresh live values
if force_refresh:
    try:
        st.cache_data.clear()
        st.success("Cache cleared.")
    except Exception:
        st.warning("Could not clear cache (safe to ignore).")

if len(symbols) == 0:
    st.warning("No symbols to fetch after filtering.")
    st.stop()

# --------------------------- Fetch Phase (batched) ---------------------------
progress = st.progress(0, text="Starting fetch…")
status = st.empty()

weeks_all = None
last_friday_all = None
labels_all = None
all_data_pieces = []
intraday_pieces = []
intraday_change_pieces = []

done = 0
total = len(symbols)
batches = list(chunk(symbols, int(max_batch)))

with st.spinner("Fetching from Yahoo Finance…"):
    for i, batch in enumerate(batches, start=1):
        status.write(f"Batch {i}/{len(batches)} — {len(batch)} symbols")
        weeks, last_friday, labels, intr_price, intr_change, all_data = fetch_all_prices(batch)

        # save one set of calendar labels
        if weeks_all is None:
            weeks_all, last_friday_all, labels_all = weeks, last_friday, labels

        # accumulate
        all_data_pieces.append(all_data)
        intraday_pieces.append(intr_price)
        intraday_change_pieces.append(intr_change)

        done += len(batch)
        progress.progress(min(int(done / total * 100), 100), text=f"Fetched {done}/{total} symbols")

# merge dicts across batches
all_data_merged = {}
for d in all_data_pieces:
    all_data_merged.update(d)

intr_price_merged = merge_symbol_dicts(intraday_pieces)
intr_change_merged = merge_symbol_dicts(intraday_change_pieces)

# --------------------------- Assemble Tables ---------------------------
price_df, norm_df, normed_df, weekly_pct_df, labels_all = assemble_price_tables(
    all_data_merged, labels_all, intr_price_merged, intr_change_merged
)

total_pct_change, pct_change_from_start, top_symbols = compute_rankings(norm_df)

# --------------------------- Tabs UI ---------------------------
tabs = st.tabs([
    "📈 Price Trend",
    "📊 Normalized Performance",
    "📈 % Weekly Change",
    "🎯 Ticker Scores",
    "📉 Max Drawdown",
    "📉 Volatility",
    "🟢 Live Snapshot",
])

with tabs[0]:
    st.subheader("📈 Price Trend — Top 20 by Return")
    plot_price_trend(norm_df, pct_change_from_start, labels_all, top_symbols)

with tabs[1]:
    st.subheader("📊 Normalized (Start = 100) — Top 20 by Return")
    plot_normalized(norm_df, labels_all, top_symbols)

with tabs[2]:
    st.subheader("📈 Weekly % Change (table)")
    st.dataframe(weekly_pct_df.round(2).reset_index(), use_container_width=True)

with tabs[3]:
    st.subheader("🎯 Ticker Scores")
    combined_scores = score_tickers(norm_df, meta_df)
    st.dataframe(
        combined_scores.round(2).sort_values("All-Around", ascending=False).reset_index(),
        use_container_width=True
    )

with tabs[4]:
    st.subheader("📉 Max Drawdown (Top 20)")
    dd_df = compute_drawdown_table(norm_df, top_symbols)
    plot_drawdown_bar(dd_df)
    st.dataframe(dd_df.round(2).reset_index(), use_container_width=True)

with tabs[5]:
    st.subheader("📉 Volatility (StdDev of Weekly % Change)")
    vol = weekly_pct_df.std(axis=1).fillna(0).rename("Volatility (%)")
    st.dataframe(vol.round(2).reset_index(), use_container_width=True)

with tabs[6]:
    st.subheader("🟢 Live Intraday Snapshot")
    cols = ["Symbol", "Live Price", "Intraday % Change", "Live % Change"]
    existing = [c for c in cols if c in price_df.columns]
    if existing:
        st.dataframe(
            price_df[existing].sort_values("Intraday % Change", ascending=False),
            use_container_width=True
        )
    else:
        st.info("Live columns not available for this run.")

# --------------------------- Composition Pies ---------------------------
pie_breakdowns(meta_df)

st.success("Done.")
