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

# ---------------- Excel engine fallback ----------------
try:
    import xlsxwriter  # noqa: F401
    _EXCEL_ENGINE = "xlsxwriter"
except Exception:
    try:
        import openpyxl  # noqa: F401
        _EXCEL_ENGINE = "openpyxl"
    except Exception:
        _EXCEL_ENGINE = None

# ---------------- Page setup & style ----------------
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

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("⚙️ Controls")
    weeks = st.selectbox("Lookback (weeks)", [6, 13, 26, 52], index=2, key="weeks_sel")  # default=26w

    src = st.radio("Symbols source", ["Upload Excel", "Paste manually"], index=0, key="src_sel")

    uploaded = None
    sheet_name = None
    pasted = ""

    if src == "Upload Excel":
        uploaded = st.file_uploader("Upload Excel with a 'Symbol' column", type=["xlsx", "xls"], key="upl_file")
        sheet_name = st.text_input("Sheet name (optional; leave blank for first sheet)", value="", key="sheet_name")
    else:
        pasted = st.text_area("Paste symbols (comma/space/newline-separated)", key="pasted_syms")

    st.caption("Tip: Use correct Yahoo suffixes (e.g., `.AS`, `.L`, `.PA`, `.MI`, `.SW`, `.TO`).")

    build_clicked = st.button("📦 Build Tables", use_container_width=True, key="build_btn")


# ---------------- Helpers ----------------
def parse_symbols_from_text(txt: str) -> List[str]:
    if not txt:
        return []
    for sp in [",", ";", "\n", "\t"]:
        txt = txt.replace(sp, " ")
    return [t.strip() for t in txt.split(" ") if t.strip()]


def _get_symbols_from_inputs() -> List[str]:
    if st.session_state.get("src_sel") == "Upload Excel":
        if st.session_state.get("upl_file") is None:
            return []
        sheet = st.session_state.get("sheet_name") or None
        df = read_excel_to_df(st.session_state["upl_file"], sheet_name=sheet)
        if "Symbol" not in df.columns:
            st.error("Uploaded sheet must contain a 'Symbol' column.")
            return []
        # Optional metadata filters if present
        filt_cols = get_available_filters(df)
        if filt_cols:
            with st.expander("🔎 Filters (optional)", expanded=False):
                selections = {}
                for c in filt_cols:
                    vals = sorted([v for v in df[c].dropna().unique()])
                    pick = st.multiselect(f"{c}", vals, default=[], key=f"filt_{c}")
                    selections[c] = pick
            df = apply_filter_selections(df, selections)
        return [str(s) for s in df["Symbol"].dropna().astype(str).tolist()]
    else:
        return parse_symbols_from_text(st.session_state.get("pasted_syms", ""))


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=True).encode("utf-8")


def _to_excel_bytes(dfs: dict) -> bytes | None:
    if _EXCEL_ENGINE is None:
        st.error(
            "No Excel engine installed. Add `xlsxwriter` or `openpyxl` to requirements.txt "
            "to enable Excel export."
        )
        return None
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine=_EXCEL_ENGINE) as writer:
        for name, d in dfs.items():
            d = d if isinstance(d, pd.DataFrame) else pd.DataFrame(d)
            d.to_excel(writer, sheet_name=name[:31], index=True)
    return output.getvalue()


# ---------------- Build on click (store in session) ----------------
if build_clicked:
    symbols = _get_symbols_from_inputs()
    if not symbols:
        st.warning("No symbols found. Please upload a sheet with a 'Symbol' column or paste symbols.")
    else:
        with st.spinner("Fetching data from Yahoo Finance…"):
            try:
                pack = build_price_tables(symbols, weeks=st.session_state["weeks_sel"])
                st.session_state["price_pack"] = pack
                st.session_state["built_symbols"] = symbols
                st.session_state["built_weeks"] = st.session_state["weeks_sel"]
            except Exception as e:
                st.error(f"Build failed: {e}")

# Retrieve last built results (so UI persists when toggling controls)
pack = st.session_state.get("price_pack")

if not pack:
    st.info("Load symbols and click **Build Tables** to see results.")
    st.stop()

# ---------------- Unpack results ----------------
labels = pack["labels"]
price_df = pack["price_df"].copy()
weekly_pct = pack["weekly_pct"].copy()
norm_df = pack["norm_df"].copy()
live_pct_df = pack["live_pct_df"].copy()
intraday_df = pack["intraday_df"].copy()

if pack.get("skipped"):
    msg = f"Skipped {len(pack['skipped'])} symbols with no data: {', '.join(pack['skipped'][:10])}"
    if len(pack["skipped"]) > 10:
        msg += " ..."
    st.warning(msg)

# ---------------- Top metrics ----------------
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("✅ Symbols with data", value=f"{price_df.shape[0]}")
with c2:
    st.metric("🗓 Weeks", value=f"{len(labels)}")
with c3:
    st.metric("⚠️ Skipped", value=f"{len(pack.get('skipped', []))}")

# ---------------- Tabs ----------------
tabs = st.tabs([
    "Overview",
    "Weekly % Heatmap",
    "Normalized (Start=100)",
    "Live & Intraday",
    "Drawdowns",
    "Downloads",
])

# ---- Overview ----
with tabs[0]:
    st.subheader("Raw Friday Close Table")
    st.caption("Rows = Symbols, Columns = Week-ending dates (YYYY-MM-DD)")
    st.dataframe(price_df, use_container_width=True, height=420)

# ---- Weekly % Heatmap ----
with tabs[1]:
    st.subheader("Weekly % Change (W-FRI over previous W-FRI)")
    weekly_pct.index.name = "Symbol"
    render_weekly_pct_heatmap(weekly_pct)

# ---- Normalized (Top-N selector) ----
with tabs[2]:
    st.subheader("Normalized Price (Start = 100)")
    st.caption("Quick relative performance view across symbols.")

    # Segmented control (falls back to radio if not available)
    try:
        top_choice = st.segmented_control(
            "Show",
            options=["All", "Top 5", "Top 10", "Top 20"],
            default="All",
            help="Ranked by latest normalized value (highest = best).",
            key="topn_choice",
        )
    except Exception:
        top_choice = st.radio(
            "Show",
            ["All", "Top 5", "Top 10", "Top 20"],
            index=0,
            help="Ranked by latest normalized value (highest = best).",
            horizontal=True,
            key="topn_choice",
        )

    top_map = {"All": None, "Top 5": 5, "Top 10": 10, "Top 20": 20}
    top_n = top_map.get(top_choice, None)

    # Plot only the requested Top N
    render_normalized_chart(norm_df, top_n=top_n)

    # Underlying table for transparency
    st.dataframe(norm_df, use_container_width=True, height=300)

# ---- Live & Intraday ----
with tabs[3]:
    st.subheader("Live & Intraday Snapshot (latest daily close vs prior close)")
    snap = (live_pct_df.merge(intraday_df, on="Symbol", how="outer"))
    valid_syms = price_df["Symbol"].tolist()
    snap = snap[snap["Symbol"].isin(valid_syms)]
    snap = snap.set_index("Symbol").reindex(valid_syms).reset_index()
    st.dataframe(snap, use_container_width=True, height=380)

# ---- Drawdowns ----
with tabs[4]:
    render_drawdown_table(price_df)

# ---- Downloads ----
with tabs[5]:
    st.subheader("Export")

    cA, cB, cC = st.columns(3)
    with cA:
        st.download_button(
            "Download price_df (CSV)",
            data=_to_csv_bytes(price_df.set_index("Symbol")),
            file_name="price_df.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Download weekly_pct (CSV)",
            data=_to_csv_bytes(weekly_pct),
            file_name="weekly_pct.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with cB:
        st.download_button(
            "Download norm_df (CSV)",
            data=_to_csv_bytes(norm_df),
            file_name="norm_df.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Download live_intraday (CSV)",
            data=_to_csv_bytes(
                live_pct_df.merge(intraday_df, on="Symbol", how="outer").set_index("Symbol")
            ),
            file_name="live_intraday.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with cC:
        excel_blob = _to_excel_bytes({
            "price_df": price_df.set_index("Symbol"),
            "weekly_pct": weekly_pct,
            "norm_df": norm_df,
            "live_pct_df": live_pct_df.set_index("Symbol"),
            "intraday_df": intraday_df.set_index("Symbol"),
        })
        st.download_button(
            "Download ALL (Excel)",
            data=excel_blob if excel_blob is not None else b"",
            file_name="weekly_price_tracker.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=(excel_blob is None),
        )
