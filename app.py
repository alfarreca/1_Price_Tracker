# app.py
import streamlit as st
import pandas as pd

from data_loader import read_first_sheet_names, read_sheet, apply_sidebar_filters
from analysis import (
    fetch_all_prices, assemble_price_tables, compute_rankings,
    score_tickers, compute_drawdown_table
)
from visualization import (
    plot_price_trend, plot_normalized, plot_drawdown_bar, pie_breakdowns
)

st.set_page_config(layout="wide")
st.title("📈 Weekly Price Tracker (Modular)")

uploaded_file = st.file_uploader("Upload your Excel file", type="xlsx")

if uploaded_file:
    xls = pd.ExcelFile(uploaded_file)
    sheet_names = read_first_sheet_names(xls)
    sheet_choice = st.selectbox("Select sheet to analyze", [""] + sheet_names)

    if sheet_choice:
        raw_df = read_sheet(xls, sheet_choice)
        if "Symbol" not in raw_df.columns:
            st.error("Excel must contain a 'Symbol' column.")
            st.stop()

        df, selected = apply_sidebar_filters(raw_df.copy(), st)

        st.write("### Filtered List Preview (metadata only):")
        st.dataframe(df.head(25), use_container_width=True)
        st.info(f"Filtered tickers: {len(df)} (showing first 25 rows)")

        if st.button("Fetch Data for Filtered Symbols"):
            symbols = df["Symbol"].dropna().unique().tolist()
            if not symbols:
                st.warning("No symbols to fetch data for.")
                st.stop()

            # ---- Fetch & assemble core tables
            weeks, last_friday, labels, intraday_price, intraday_change, all_data = fetch_all_prices(symbols)
            price_df, norm_df, normed, weekly_pct, labels = assemble_price_tables(
                all_data, labels, intraday_price, intraday_change
            )
            total_pct_change, pct_change_from_start, top_symbols = compute_rankings(norm_df)

            tabs = st.tabs([
                "📈 Price Trend",
                "📊 Normalized Performance",
                "📈 % Weekly Change",
                "🎯 Ticker Scores",
                "📉 Max Drawdown",
                "📉 Volatility",
            ])

            with tabs[0]:
                st.subheader("📈 Price Trend")
                plot_price_trend(norm_df, pct_change_from_start, labels, top_symbols)

            with tabs[1]:
                st.subheader("📊 Normalized Performance (Start = 100)")
                plot_normalized(norm_df, labels, top_symbols)

            with tabs[2]:
                st.subheader("📈 Weekly % Change")
                st.dataframe(weekly_pct.round(2).reset_index(), use_container_width=True)

            with tabs[3]:
                st.subheader("🎯 Ticker Scores")
                combined_scores = score_tickers(norm_df, df)
                st.dataframe(combined_scores.round(2).sort_values("All-Around", ascending=False).reset_index(),
                             use_container_width=True)

            with tabs[4]:
                st.subheader("📉 Max Drawdown")
                dd_df = compute_drawdown_table(norm_df, top_symbols)
                plot_drawdown_bar(dd_df)
                st.dataframe(dd_df.round(2).reset_index(), use_container_width=True)

            with tabs[5]:
                st.subheader("📉 Volatility (StdDev of Weekly % Change)")
                vol = weekly_pct.std(axis=1).fillna(0).rename("Volatility (%)")
                st.dataframe(vol.round(2).reset_index(), use_container_width=True)

            with st.expander("📌 Live Intraday Data"):
                cols = ["Symbol", "Live Price", "Intraday % Change", "Live % Change"]
                show_cols = [c for c in cols if c in price_df.columns]
                st.dataframe(price_df[show_cols].sort_values("Intraday % Change", ascending=False),
                             use_container_width=True)

            # Pies
            pie_breakdowns(df)
