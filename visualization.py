# visualization.py
from __future__ import annotations

import pandas as pd
import streamlit as st

# Local helper duplicated here to avoid tight coupling/circular imports.
def _calculate_max_drawdown(prices: pd.Series) -> float:
    if prices is None or prices.empty:
        return float("nan")
    s = prices.astype(float).dropna()
    if s.empty:
        return float("nan")
    cum_max = s.cummax()
    drawdown = (s / cum_max) - 1.0
    return float(drawdown.min() * 100.0)


def _top_n_by_last_value(wide_df: pd.DataFrame, n: int | None) -> pd.DataFrame:
    """
    Keep only the top-n rows by their LAST column value (descending).
    Assumes rows = symbols, columns = dates (ascending). If n is None, return as-is.
    """
    if wide_df is None or wide_df.empty or n is None:
        return wide_df
    # last valid column
    last_col = wide_df.columns[-1]
    scores = pd.to_numeric(wide_df[last_col], errors="coerce")
    keep = scores.sort_values(ascending=False).head(n).index
    return wide_df.loc[keep]


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
    - norm_df: rows = symbols (index), columns = dates (YYYY-MM-DD)
    - top_n: if set, show only top N symbols by latest value.
    """
    if norm_df is None or norm_df.empty:
        st.info("Normalized table is empty — nothing to plot.")
        return

    # Filter to top-n before plotting
    df = norm_df.copy()
    df = _top_n_by_last_value(df, top_n)

    # Ensure index has a consistent name before reset_index/melt
    if df.index.name is None or str(df.index.name).strip() == "":
        df.index.name = "Symbol"
    idx_col = df.index.name  # "Symbol"

    # Long-form for plotting
    long = (
        df.reset_index()
          .melt(id_vars=idx_col, var_name="Date", value_name="Value")
          .rename(columns={idx_col: "Symbol"})
          .dropna(subset=["Value"])
    )

    # Coerce Date to datetime for proper temporal axis
    try:
        long["Date"] = pd.to_datetime(long["Date"])
    except Exception:
        pass

    # Plot with Altair if available; fallback to Streamlit line_chart
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
        # Fallback: pivot to wide for line_chart (Date as index)
        wide = long.pivot(index="Date", columns="Symbol", values="Value").sort_index()
        st.line_chart(wide, height=420, use_container_width=True)


def render_drawdown_table(price_df: pd.DataFrame):
    """
    Compute & render max drawdown per symbol using raw weekly closes in `price_df`.
    `price_df` is expected as rows=symbols, first col 'Symbol', others = dates.
    """
    if price_df is None or price_df.empty or "Symbol" not in price_df.columns or price_df.shape[1] <= 2:
        st.info("Not enough data to compute drawdowns.")
        return

    dd_rows = []
    for sym, row in price_df.set_index("Symbol").iterrows():
        series = row.dropna().astype(float)
        dd = _calculate_max_drawdown(series)
        dd_rows.append({"Symbol": sym, "Max Drawdown %": dd})

    dd_df = pd.DataFrame(dd_rows).sort_values("Max Drawdown %")
    st.subheader("Max Drawdown (based on weekly closes)")
    st.dataframe(dd_df, use_container_width=True, height=360)
