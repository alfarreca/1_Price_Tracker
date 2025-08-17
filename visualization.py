# visualization.py
import plotly.graph_objs as go
import pandas as pd
import streamlit as st

def plot_price_trend(norm_df: pd.DataFrame, pct_change_from_start: pd.DataFrame, labels, top_symbols):
    fig = go.Figure()
    for sym in top_symbols:
        fig.add_trace(go.Scatter(
            x=labels,
            y=norm_df.loc[sym],
            customdata=pct_change_from_start.loc[sym].values.reshape(-1, 1),
            mode='lines+markers',
            name=sym,
            text=[sym]*len(labels),
            hovertemplate="<b>%{text}</b><br>Price: %{y:.2f}<br>Change: %{customdata[0]:.2f}%"
        ))
    fig.update_layout(hovermode="x unified", height=500, title="Price Trend — Top 20 by Return")
    st.plotly_chart(fig, use_container_width=True)

def plot_normalized(norm_df: pd.DataFrame, labels, top_symbols):
    start_values = norm_df.iloc[:, 0]
    total_pct_change = ((norm_df.iloc[:, -1] - norm_df.iloc[:, 0]) / norm_df.iloc[:, 0] * 100).fillna(0)
    normed_pct = norm_df.divide(start_values, axis=0) * 100
    fig = go.Figure()
    for sym in top_symbols:
        label_name = f"{sym} ({total_pct_change[sym]:+.2f}%)"
        fig.add_trace(go.Scatter(
            x=labels,
            y=normed_pct.loc[sym],
            mode="lines",
            name=label_name,
            text=[label_name]*len(labels),
            hovertemplate="<b>%{text}</b><br>Normalized: %{y:.2f}"
        ))
    fig.update_layout(hovermode="closest", height=500, title="Normalized — Top 20 by Return")
    st.plotly_chart(fig, use_container_width=True)

def plot_drawdown_bar(drawdown_df: pd.DataFrame):
    fig = go.Figure(go.Bar(
        x=drawdown_df.index,
        y=drawdown_df.iloc[:, 0].values,
        hovertemplate="%{x}<br>Drawdown: %{y:.2f}%"
    ))
    fig.update_layout(title="Drawdown (%) — Top 20 by Return", yaxis_title="Drawdown", height=500)
    st.plotly_chart(fig, use_container_width=True)

def pie_breakdowns(meta_df: pd.DataFrame):
    with st.expander("📊 Composition Breakdown (Pie Charts)"):
        if "Sector" in meta_df.columns:
            c = meta_df["Sector"].value_counts()
            st.plotly_chart(go.Figure([go.Pie(labels=c.index, values=c.values, hole=.3)])
                            .update_layout(title_text="Sector Distribution"),
                            use_container_width=True)
        if "Industry Group" in meta_df.columns:
            c = meta_df["Industry Group"].value_counts()
            st.plotly_chart(go.Figure([go.Pie(labels=c.index, values=c.values, hole=.3)])
                            .update_layout(title_text="Industry Group Distribution"),
                            use_container_width=True)
        if "Industry" in meta_df.columns:
            c = meta_df["Industry"].value_counts()
            st.plotly_chart(go.Figure([go.Pie(labels=c.index, values=c.values, hole=.3)])
                            .update_layout(title_text="Industry Distribution"),
                            use_container_width=True)
