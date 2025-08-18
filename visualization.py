# visualization.py
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

# --- small helper, duplicated locally to avoid tight coupling ---
def _calculate_max_drawdown(prices: pd.Series) -> float:
    if prices is None or prices.empty:
        return float("nan")
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    cum_max = s.cummax()
    drawdown = (s / cum_max) - 1.0
    return float(drawdown.min() * 100.0)


def _coerce_numeric_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all cells are numeric where possible (silently coerce)."""
    out = df.copy()
    for c in out.columns:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _sort_columns_as_dates_if_possible(df: pd.DataFrame) -> pd.DataFrame:
    """If columns look like dates, sort them chronologically; else keep as-is."""
    cols = list(df.columns)
    try:
        as_dt = pd.to_datetime(cols, errors="raise")
        order = np.argsort(as_dt.values)
        return df.iloc[:, order]
    except Exception:
        return df


def _last_valid_numeric(series: pd.Series) -> float:
    """Return last non-NaN numeric value in a row (or NaN)."""
    vals = pd.to_numeric(series, errors="coerce").dropna()
    return float(vals.iloc[-1]) if not vals.empty else np.nan


def _top_n_by_last_value(wide_df: pd.DataFrame, n: int | None) -> pd.DataFrame:
    """
    Keep only the top-n rows by their LAST VALID column value (descending).
    Assumes rows = symbols, columns = dates. Handles NaNs and unordered columns.
    """
    if wide_df is None or wide_df.empty or n is None:
        return wide_df

    df = _coerce_numeric_df(_sort_columns_as_dates_if_possible(wide_df))

    scores = df.apply(_last_valid_numeric, axis=1)
    keep_idx = scores.sort_values(ascending=False).head(n).index
    return df.loc[keep_idx]


def render_weekly_pct_heatmap(weekly_pct: pd.DataFrame):
    """Heatmap-like styled DataFrame."""
    if weekly_pct is None or weekly_pct.empty:
        st.info("Weekly % Change table is empty — nothing to show.")
        return
    try:
        sty = (
            weekly_pct.style
            .format("{:.2f}")
            .background_gradient(axis=None)
        )
        st.dataframe(sty, use_container_width=True, height=480)
    except Exception:
        st.dataframe(weekly_pct, use_container_width=True, height=480)


def render_normalized_chart(norm_df: pd.DataFrame, top_n: int | None = None):
    """
    Interactive line chart of normalized prices (start=100).
    - norm_df: rows = symbols (index), columns = dates (strings)
    - top_n: if set, show only top N symbols by latest valid value.
    """
    if norm_df is None or norm_df.empty:
        st.info("Normalized table is empty — nothing to plot.")
        return

    # Safeguards: sort date columns & coerce numbers
    df = _sort_columns_as_dates_if_possible(norm_df.copy())
    df = _coerce_numeric_df(df)

    # Filter to Top-N BEFORE plotting
    df = _top_n_by_last_value(df, top_n)

    # Ensure index has a name
    if df.index.name is None or str(df.index.name).strip() == "":
        df.index.name = "Symbol"
    idx_col = df.index.name

    # Long form
    long = (
        df.reset_index()
          .melt(id_vars=idx_col, var_name="Date", value_name="Value")
          .rename(columns={idx_col: "Symbol"})
          .dropna(subset=["Value"])
    )

    # Parse Date for temporal axis
    try:
        long["Date"] = pd.to_datetime(long["Date"])
    except Exception:
        pass

    # Display how many lines are shown
    shown = long["Symbol"].nunique()
    st.caption(f"Showing {shown} series" + (f" (Top {top_n})" if top_n else " (All)"))

    # Plot
    try:
        import altair as alt
        chart = (
            alt.Chart(long)
            .mark_line()
            .encode(
                x="Date:T",
                y=alt.Y("Value:Q", title="Index (Start=100)"),
                color="Symbol:N",
                tooltip=["Symbol", "Date:T", alt.Tooltip("Value:Q", format=".2f")],
            )
            .properties(height=420)
            .interactive()
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        wide = long.pivot(index="Date", columns="Symbol", values="Value").sort_index()
        st.line_chart(wide, height=420, use_container_width=True)


def render_drawdown_table(price_df: pd.DataFrame):
    """
    Compute & render max drawdown per symbol using raw weekly closes in `price_df`.
    `price_df` is expected as rows=symbols, first col 'Symbol', others = dates.
    """
    if (price_df is None or price_df.empty or
        "Symbol" not in price_df.columns or price_df.shape[1] <= 2):
        st.info("Not enough data to compute drawdowns.")
        return

    dd_rows = []
    for sym, row in price_df.set_index("Symbol").iterrows():
        series = pd.to_numeric(row.dropna(), errors="coerce")
        dd = _calculate_max_drawdown(series)
        dd_rows.append({"Symbol": sym, "Max Drawdown %": dd})

    dd_df = pd.DataFrame(dd_rows).sort_values("Max Drawdown %")
    st.subheader("Max Drawdown (based on weekly closes)")
    st.dataframe(dd_df, use_container_width=True, height=360)
