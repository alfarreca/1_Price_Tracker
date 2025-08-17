# analysis.py
import numpy as np
import pandas as pd
from datetime import datetime
from data_loader import (
    get_last_n_weeks, fetch_friday_closes, fetch_current_week_close,
    fetch_intraday_live_price, calculate_max_drawdown
)

def build_labels(weeks, current_week_start):
    labels = [f"{m.strftime('%b %d')}→{f.strftime('%b %d')}" for m, f in weeks]
    labels += [f"{current_week_start.strftime('%b %d')}→{datetime.today().strftime('%b %d')}"]
    return labels

def fetch_all_prices(symbols, n_weeks: int = 6):
    weeks, last_friday = get_last_n_weeks(n_weeks)
    current_week_start = last_friday

    intraday_price, intraday_change, all_data = {}, {}, {}
    for sym in symbols:
        price, change = fetch_intraday_live_price(sym)
        intraday_price[sym] = price
        intraday_change[sym] = change

        closes = fetch_friday_closes(sym, weeks)
        current = fetch_current_week_close(sym, current_week_start)
        all_data[sym] = closes + [current]

    labels = build_labels(weeks, current_week_start)
    return weeks, last_friday, labels, intraday_price, intraday_change, all_data

def assemble_price_tables(all_data, labels, intraday_price, intraday_change):
    price_df = pd.DataFrame(all_data).T
    price_df.columns = labels
    price_df.index.name = "Symbol"
    price_df = price_df.reset_index()

    for col in labels:
        price_df[col] = pd.to_numeric(price_df[col], errors="coerce")

    # Live % change vs last Friday close
    live_pct = {}
    for sym, row in price_df.set_index("Symbol").iterrows():
        last_friday_close = row.iloc[-2] if len(row) >= 2 else np.nan
        current_price = row.iloc[-1]
        if pd.notna(last_friday_close) and pd.notna(current_price) and last_friday_close != 0:
            live_change = ((current_price - last_friday_close) / last_friday_close) * 100
        else:
            live_change = np.nan
        live_pct[sym] = round(live_change, 2) if pd.notna(live_change) else np.nan
    live_pct_df = pd.DataFrame.from_dict(live_pct, orient="index", columns=["Live % Change"]).reset_index().rename(columns={"index":"Symbol"})

    intraday_df = pd.DataFrame({
        "Symbol": list(intraday_price.keys()),
        "Live Price": list(intraday_price.values()),
        "Intraday % Change": list(intraday_change.values())
    })

    price_df = price_df.merge(live_pct_df, on="Symbol", how="left").merge(intraday_df, on="Symbol", how="left")

    # Normalized / weekly pct change tables
    norm_df = price_df.set_index("Symbol")[labels]
    safe_norm = norm_df.where(norm_df.iloc[:, 0] != 0)
    normed = safe_norm.div(norm_df.iloc[:, 0], axis=0)

    weekly_pct = norm_df.pct_change(axis=1) * 100

    # Handle duplicate/flat last column (current partial week)
    if weekly_pct.shape[1] > 0:
        last_col = weekly_pct.columns[-1]
        left, right = last_col.split("→")
        if left == right or weekly_pct.iloc[:, -1].nunique() <= 1:
            weekly_pct = weekly_pct.iloc[:, :-1]
            norm_df = norm_df.iloc[:, :-1]
            normed = normed.iloc[:, :-1]
            labels = labels[:-1]

    return price_df, norm_df, normed, weekly_pct, labels

def compute_rankings(norm_df: pd.DataFrame):
    start_values = norm_df.iloc[:, 0]
    last_values = norm_df.iloc[:, -1]
    total_pct_change = ((last_values - start_values) / start_values) * 100
    pct_change_from_start = norm_df.subtract(start_values, axis=0).divide(start_values, axis=0) * 100
    top_symbols = total_pct_change.sort_values(ascending=False).head(20).index.tolist()
    return total_pct_change, pct_change_from_start, top_symbols

def score_tickers(norm_df: pd.DataFrame, meta_df: pd.DataFrame):
    scores = pd.DataFrame(index=norm_df.index)
    scores["Momentum"] = (norm_df.iloc[:, -1] - norm_df.iloc[:, -2]).fillna(0)
    scores["Volatility"] = norm_df.std(axis=1).fillna(0)
    scores["Trend"] = norm_df.apply(lambda row: (row.diff().fillna(0) > 0).sum(), axis=1)
    scores["Total Return (%)"] = ((norm_df.iloc[:, -1] - norm_df.iloc[:, 0]) / norm_df.iloc[:, 0] * 100).fillna(0)
    scores["All-Around"] = scores.sum(axis=1)

    metadata_cols = ["Name", "Sector", "Industry Group", "Industry", "Theme", "Country", "Asset_Type", "Notes"]
    available_cols = [c for c in metadata_cols if c in meta_df.columns]
    meta = meta_df.set_index("Symbol")[available_cols].copy() if "Symbol" in meta_df.columns else pd.DataFrame(index=scores.index)
    combined = meta.join(scores, how="right")
    return combined

def compute_drawdown_table(norm_df: pd.DataFrame, symbols: list):
    dd = norm_df.loc[symbols].apply(lambda row: calculate_max_drawdown(row.dropna()), axis=1).dropna()
    return dd.rename("Drawdown (%)").to_frame()
