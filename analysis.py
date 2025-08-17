import streamlit as st
import pandas as pd

from data_loader import (
    read_excel_to_df,
    get_available_filters,
    apply_filter_selections,
    build_price_tables,
)

from visualization import (
    plot_price_trend,
    plot_normalized_performance,
    plot_drawdowns,
    pie_distribution,
)

st.set_page_config(layout="wide")
st.title("📈 Weekly Price Tracker (Efficient Mode)")

uploaded_file = st.file_uploader("Upload your Excel file", type="xlsx")

if uploaded_file:
    # Let user pick sheet
    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names
    sheet_choice = st.selectbox("Select sheet to analyze", [""] + sheet_names)

    if sheet_choice:
        df = read_excel_to_df(uploaded_file, sheet_choice)

        if "Symbol" not in df.columns:
            st.error("Excel must contain a 'Symbol' column.")
            st.stop()

        # Sidebar filters
        available_filters = get_available_filters(df)
        selections = {}
        for col in available_filters:
            unique_vals = sorted(df[col].dropna().unique().tolist())
            selections[col] = st.sidebar.multiselect(f"Filter by {col}", unique_vals)

        filtered_df = apply_filter_selections(df, selections)

        st.write("### Filtered List Preview (metadata only):")
        st.dataframe(filtered_df.head(25), use_container_width=True)
        st.info(f"Filtered tickers: {len(filtered_df)} (showing first 25 rows)")

        if st.button("Fetch Data for Filtered Symbols"):
            symbols = filtered_df["Symbol"].dropna().unique().tolist()
            if not symbols:
                st.warning("No symbols to fetch data for.")
                st.stop()

            pack = build_price_tables(symbols)
            labels = pack["labels"]
            price_df = pack["price_df"]
            weekly_pct = pack["weekly_pct"]
            live_pct_df = pack["live_pct_df"]
            intraday_df = pack["intraday_df"]
            norm_df = pack["norm_df"]

            # Ranking (Top 20 by total return)
            start_values = norm_df.iloc[:, 0]
            last_values = norm_df.iloc[:, -1]
            total_pct_change = ((last_values - start_values) / start_values) * 100
            top_n = 20
            top_symbols = total_pct_change.sort_values(ascending=False).head(top_n).index.tolist()
            pct_change_from_start = norm_df.subtract(start_values, axis=0).divide(start_values, axis=0) * 100

            tabs = st.tabs([
                "📈 Price Trend",
                "📊 Normalized Performance",
                "📈 % Weekly Change",
                "🎯 Ticker Scores",
                "📉 Max Drawdown",
                "📉 Volatility"
            ])

            with tabs[0]:
                st.subheader("📈 Price Trend")
                st.plotly_chart(
                    plot_price_trend(norm_df, labels, top_symbols, pct_change_from_start),
                    use_container_width=True
                )

            with tabs[1]:
                st.subheader("📊 Normalized Performance (Start = 100)")
                st.plotly_chart(
                    plot_normalized_performance(norm_df, labels, top_symbols),
                    use_container_width=True
                )

            with tabs[2]:
                st.subheader("📈 Weekly % Change")
                st.dataframe(weekly_pct.round(2).reset_index(), use_container_width=True)

            with tabs[3]:
                st.subheader("🎯 Ticker Scores")
                scores = pd.DataFrame(index=norm_df.index)
                scores["Momentum"] = (norm_df.iloc[:, -1] - norm_df.iloc[:, -2]).fillna(0)
                scores["Volatility"] = norm_df.std(axis=1).fillna(0)
                scores["Trend"] = norm_df.apply(lambda row: sum(row.diff().fillna(0) > 0), axis=1)
                scores["Total Return (%)"] = ((norm_df.iloc[:, -1] - norm_df.iloc[:, 0]) / norm_df.iloc[:, 0] * 100).fillna(0)
                scores["All-Around"] = scores.sum(axis=1)

                metadata_cols = ["Name", "Sector", "Industry Group", "Industry", "Theme", "Country", "Asset_Type", "Notes"]
                avail = [c for c in metadata_cols if c in filtered_df.columns]
                missing = [c for c in metadata_cols if c not in filtered_df.columns]
                if missing:
                    st.warning(f"Missing metadata columns: {missing}")
                meta = filtered_df.set_index("Symbol")[avail].copy()
                combined = meta.join(scores, how="right")

                st.dataframe(combined.round(2).sort_values("All-Around", ascending=False).reset_index(),
                             use_container_width=True)

            with tabs[4]:
                st.subheader("📉 Max Drawdown")
                fig, dd_table = plot_drawdowns(norm_df, top_symbols)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(dd_table, use_container_width=True)

            with tabs[5]:
                st.subheader("📉 Volatility (Standard Deviation of Weekly % Change)")
                volatility = weekly_pct.std(axis=1).fillna(0)
                st.dataframe(volatility.rename("Volatility (%)").round(2).reset_index(), use_container_width=True)

                with st.expander("📌 Live Intraday Data"):
                    merged_live = (
                        price_df[["Symbol"] + labels[-1:]]  # keep last period column for context if you want
                        .merge(live_pct_df, on="Symbol", how="left")
                        .merge(intraday_df, on="Symbol", how="left")
                    )
                    st.dataframe(
                        merged_live[["Symbol", "Live Price", "Intraday % Change", "Live % Change"]]
                        .sort_values("Intraday % Change", ascending=False),
                        use_container_width=True
                    )

            with st.expander("📊 Composition Breakdown (Pie Charts)"):
                if "Sector" in filtered_df.columns:
                    st.plotly_chart(pie_distribution(filtered_df["Sector"].value_counts(), "Sector Distribution"),
                                    use_container_width=True)
                if "Industry Group" in filtered_df.columns:
                    st.plotly_chart(pie_distribution(filtered_df["Industry Group"].value_counts(), "Industry Group Distribution"),
                                    use_container_width=True)
                if "Industry" in filtered_df.columns:
                    st.plotly_chart(pie_distribution(filtered_df["Industry"].value_counts(), "Industry Distribution"),
                                    use_container_width=True)
