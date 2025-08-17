import plotly.graph_objs as go
import pandas as pd
from data_loader import calculate_max_drawdown  # absolute import for Streamlit Cloud


# ---------- Line charts ----------
def plot_price_trend(norm_df: pd.DataFrame, labels, top_symbols, pct_change_from_start: pd.DataFrame):
    """
    Line chart of raw price series (not normalized) for top_symbols.
    Hover shows per-point % change from start.
    """
    fig = go.Figure()
    for sym in top_symbols:
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=norm_df.loc[sym],
                customdata=pct_change_from_start.loc[sym].values.reshape(-1, 1),
                mode="lines+markers",
                name=sym,
                text=[sym] * len(labels),
                hovertemplate="<b>%{text}</b><br>Price: %{y:.2f}"
                              "<br>Change from start: %{customdata[0]:.2f}%"
            )
        )
    fig.update_layout(hovermode="x unified", height=500, title="Price Trend — Top 20 by Return")
    return fig


def plot_normalized_performance(norm_df: pd.DataFrame, labels, top_symbols):
    """
    Normalizes each series to 100 at the first column and plots Top N.
    """
    start_values = norm_df.iloc[:, 0]
    total_pct_change = ((norm_df.iloc[:, -1] - start_values) / start_values) * 100
    pct_change_from_start = norm_df.subtract(start_values, axis=0).divide(start_values, axis=0) * 100

    normed_pct = norm_df.divide(start_values, axis=0) * 100

    fig = go.Figure()
    for sym in top_symbols:
        change = total_pct_change[sym]
        label_name = f"{sym} ({change:+.2f}%)"
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=normed_pct.loc[sym],
                customdata=pct_change_from_start.loc[sym].values.reshape(-1, 1),
                mode="lines",
                name=label_name,
                text=[label_name] * len(labels),
                hovertemplate="<b>%{text}</b><br>Normalized: %{y:.2f}"
                              "<br>Change from start: %{customdata[0]:.2f}%"
            )
        )
    fig.update_layout(hovermode="closest", height=500, title="Normalized — Top 20 by Return (Start=100)")
    return fig


# ---------- Bars / Pies ----------
def plot_drawdowns(norm_df: pd.DataFrame, top_symbols):
    """
    Computes max drawdown (%) per symbol and returns (figure, table_df).
    """
    drawdowns = norm_df.loc[top_symbols].apply(
        lambda row: calculate_max_drawdown(row.dropna()), axis=1
    ).dropna()

    fig = go.Figure(
        go.Bar(
            x=drawdowns.index,
            y=drawdowns.values,
            marker_color="crimson",
            hovertemplate="%{x}<br>Drawdown: %{y:.2f}%"
        )
    )
    fig.update_layout(title="Max Drawdown (%) — Top 20 by Return", yaxis_title="Drawdown (%)", height=500)

    dd_table = drawdowns.rename("Drawdown (%)").round(2).reset_index()
    return fig, dd_table


def pie_distribution(series: pd.Series, title: str):
    """
    Simple pie chart for a categorical series .value_counts().
    """
    fig = go.Figure(data=[go.Pie(labels=series.index, values=series.values, hole=0.3)])
    fig.update_layout(title_text=title)
    return fig
