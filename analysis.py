# analysis.py
import io
from typing import List

import pandas as pd
import streamlit as st

from data_loader import (
    read_excel_to_df,
    get_available_filters,
    apply_filter_selections,
    build_price_tables,
)
from visualization import (
    render_weekly_pct_heatmap,
    render_normalized_chart,
    render_drawdown_table,
)

# ---------- Page setup ----------
st.set_page_config(page_title="Weekly Price Tracker", layout="wide")
st.markdown(
    """
    <style>
      .stDataFrame table { font-size: 0.9rem; }
      .metric-small .stMetric { padding: 0.25rem 0.5rem; }
      .block-container { padding-top: 1rem; }
      .stTabs [data-baseweb="tab-list"] { gap: 0.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 Weekly Price Tracker (W-FRI Closes)")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Controls")
    weeks = st.selectbox("Lookback (weeks)", [13, 26, 52], index=1)
    src = st.radio("Symbols source", ["Upload Excel", "Paste manually"], index=0)

    uploaded = None
    sheet_name = None
    pasted = ""

    if src == "Upload Excel":
        uploaded = st.file_uploader("Upload Excel with a 'Symbol' column", type=["xlsx", "xls"])
        sheet_name = st.text_input("Sheet name (optional; leave blank for first sheet)", value="")
    else:
        pasted = st.text_area("Paste symbols (comma/space/newline-separated)")

    st.caption("Tip: Use correct Yahoo suffixes (e.g., `.AS`, `.L`, `.PA`, `.MI`, `.SW`, `.TO`).")

    run = st.button("📦 Build Tables", use_container_width=True)

# ---------- Helpers ----------
def parse_symbols_from_text(txt: str) -> List[str]:
    if not txt:
        return []
    for sp in [",", ";", "\n", "\t"]:
        txt = txt.replace(sp, " ")
    return [t.strip() for t in txt.split(" ") if t.strip()]

# ---------- Ingest ----------
symbols: List[str] = []
meta_df = None

if src == "Upload Excel" and uploaded is not None:
    try:
        sheet = sheet_name if sheet_name.strip() else None
        meta_df = read_excel_to_df(uploaded, sheet_name=sheet)
        if "Symbol" not in meta_df.columns:
            st.error("Uploaded sheet must contain a 'Symbol' column.")
        else:
            filt_cols = get_available_filters(meta_df)
            selections = {}
            if filt_cols:
                with st.expander("🔎 Filters (optional)", expanded=False):
                    for c in filt_cols:
                        vals = sorted([v for v in meta_df[c].dropna().unique()])
                        pick = st.multiselect(f"{c}", vals, default=[])
                        selections[c] = pick
                meta_df = apply_filter_selections(meta_df, selections)
            symbols = [str(s) for s in meta_df["Symbol"].dropna().astype(str).tolist()]
    except Exception as e:
        st.error(f"Failed to read Excel: {e}")
elif src == "Paste manually":
    symbols = parse_symbols_from_text(pasted)

# ---------- Execute ----------
if run:
    if not symbols:
        st.warning("No symbols found. Please upload a sheet with a 'Symbol' column or paste symbols.")
        st.stop()

    with st.spinner("Fetching data from Yahoo Finance…"):
        try:
            pack = build_price_tables(symbols, weeks=weeks)
        except Exception as e:
            st.error(f"Build failed: {e}")
            st.stop()

    if pack.get("skipped"):
        msg = f"Skipped {len(pack['skipped'])} symbols with no data: {', '.join(pack['skipped'][:10])}"
        if len(pack["skipped"]) > 10:
            msg += " ..."
        st.warning(msg)

    labels = pack["labels"]
    price_df = pack["price_df"].copy()
    weekly_pct = pack["weekly_pct"].copy()
    norm_df = pack["norm_df"].copy()
    live_pct_df = pack["live_pct_df"].copy()
    intraday_df = pack["intraday_df"].copy()

    # Top metrics
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("✅ Symbols with data", value=f"{price_df.shape[0]}")
    with c2:
        st.metric("🗓 Weeks", value=f"{len(labels)}")
    with c3:
        st.metric("⚠️ Skipped", value=f"{len(pack.get('skipped', []))}")

    tabs = st.tabs([
        "Overview",
        "Weekly % Heatmap",
        "Normalized (Start=100)",
        "Live & Intraday",
        "Drawdowns",
        "Downloads",
    ])

    # ---------- Overview ----------
    with tabs[0]:
        st.subheader("Raw Friday Close Table")
        st.caption("Rows = Symbols, Columns = Week-ending dates (YYYY-MM-DD)")
        st.dataframe(price_df, use_container_width=True, height=420)

    # ---------- Weekly % ----------
    with tabs[1]:
        st.subheader("Weekly % Change (W-FRI over previous W-FRI)")
        weekly_pct.index.name = "Symbol"
        render_weekly_pct_heatmap(weekly_pct)

    # ---------- Normalized ----------
    with tabs[2]:
        st.subheader("Normalized Price (Start = 100)")
        st.caption("Quick relative performance view across symbols.")
        render_normalized_chart(norm_df)
        st.dataframe(norm_df, use_container_width=True, height=300)

    # ---------- Live & Intraday ----------
    with tabs[3]:
        st.subheader("Live & Intraday Snapshot (latest daily close vs prior close)")
        snap = (live_pct_df.merge(intraday_df, on="Symbol", how="outer"))
        valid_syms = price_df["Symbol"].tolist()
        snap = snap[snap["Symbol"].isin(valid_syms)]
        snap = snap.set_index("Symbol").reindex(valid_syms).reset_index()
        st.dataframe(snap, use_container_width=True, height=380)

    # ---------- Drawdowns ----------
    with tabs[4]:
        render_drawdown_table(price_df)

    # ---------- Downloads ----------
    with tabs[5]:
        st.subheader("Export")
        def to_csv_bytes(df: pd.DataFrame) -> bytes:
            return df.to_csv(index=True).encode("utf-8")

        def to_excel_bytes(dfs: dict) -> bytes:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                for name, d in dfs.items():
                    d = d if isinstance(d, pd.DataFrame) else pd.DataFrame(d)
                    d.to_excel(writer, sheet_name=name[:31], index=True)
            return output.getvalue()

        cA, cB, cC = st.columns(3)
        with cA:
            st.download_button(
                "Download price_df (CSV)",
                data=to_csv_bytes(price_df.set_index("Symbol")),
                file_name="price_df.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "Download weekly_pct (CSV)",
                data=to_csv_bytes(weekly_pct),
                file_name="weekly_pct.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with cB:
            st.download_button(
                "Download norm_df (CSV)",
                data=to_csv_bytes(norm_df),
                file_name="norm_df.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "Download live_intraday (CSV)",
                data=to_csv_bytes(
                    live_pct_df.merge(intraday_df, on="Symbol", how="outer").set_index("Symbol")
                ),
                file_name="live_intraday.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with cC:
            st.download_button(
                "Download ALL (Excel)",
                data=to_excel_bytes({
                    "price_df": price_df.set_index("Symbol"),
                    "weekly_pct": weekly_pct,
                    "norm_df": norm_df,
                    "live_pct_df": live_pct_df.set_index("Symbol"),
                    "intraday_df": intraday_df.set_index("Symbol"),
                }),
                file_name="weekly_price_tracker.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
