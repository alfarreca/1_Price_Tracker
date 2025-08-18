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


def render_weekly_pct_heatmap(weekly_pct: pd.DataFrame):
    """Heatmap-like styled DataFrame."""
    try:
        sty = (weekly_pct
               .style
               .format("{:.2f}")
               .background_gradient(axis=None))
        st.dataframe(sty, use_container_width=True, height=480)
    except Exception:
        st.dataframe(weekly_pct, use_container_width=True, height=480)


def render_normalized_chart(norm_df: pd.DataFrame):
    """Interactive line chart of normalized prices."""
    long = (
        norm_df.reset_index()
               .melt(id_vars="index", var_name="Date", value_name="Value")
               .rename(columns={"index": "Symbol"})
               .dropna()
    )
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
        st.line_chart(norm_df.T, height=420, use_container_width=True)


def render_drawdown_table(price_df: pd.DataFrame):
    """
    Compute & render max drawdown per symbol using raw weekly closes in `price_df`.
    `price_df` is expected as rows=symbols, first col 'Symbol', others = dates.
    """
    if "Symbol" not in price_df.columns or price_df.shape[1] <= 2:
        st.info("Not enough data to compute drawdowns.")
        return

    syms = price_df["Symbol"].tolist()
    dd_rows = []
    for sym, row in price_df.set_index("Symbol").iterrows():
        series = row.dropna().astype(float)
        dd = _calculate_max_drawdown(series)
        dd_rows.append({"Symbol": sym, "Max Drawdown %": dd})

    dd_df = pd.DataFrame(dd_rows).sort_values("Max Drawdown %")
    st.subheader("Max Drawdown (based on weekly closes)")
    st.dataframe(dd_df, use_container_width=True, height=360)
