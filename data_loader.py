import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import streamlit as st

@st.cache_data(ttl=600, show_spinner=False)
def _dl(symbol, start, end, interval="1d"):
    # Single, non-threaded download to avoid Cloud hangs
    return yf.download(
        symbol, start=start, end=end + timedelta(days=1),
        interval=interval, progress=False, threads=False, auto_adjust=False
    )

def fetch_friday_closes(symbol: str, weeks):
    start_date, end_date = weeks[0][0], weeks[-1][1]
    df = _dl(symbol, start_date, end_date, interval="1d")
    if df.empty or "Close" not in df.columns:
        return [np.nan] * len(weeks)
    closes = []
    for monday, friday in weeks:
        week_data = df[(df.index >= monday) & (df.index <= friday)]
        close = week_data[week_data.index.weekday == 4]["Close"].dropna()
        if not close.empty:
            closes.append(float(round(close.iloc[-1], 3)))
        else:
            fallback = week_data["Close"].dropna()
            closes.append(float(round(fallback.iloc[-1], 3)) if not fallback.empty else np.nan)
    return closes

@st.cache_data(ttl=180, show_spinner=False)
def fetch_current_week_close(symbol: str, current_week_start):
    today = datetime.today()
    df = _dl(symbol, current_week_start, today, interval="1d")
    if df.empty or "Close" not in df.columns:
        return np.nan
    closes = df["Close"].dropna()
    return round(float(closes.iloc[-1]), 3) if not closes.empty else np.nan

@st.cache_data(ttl=30, show_spinner=False)
def fetch_intraday_live_price(symbol: str):
    try:
        info = yf.Ticker(symbol).info  # fast, cached per symbol
        current_price = info.get("regularMarketPrice")
        prev_close = info.get("regularMarketPreviousClose")
        pct_change = ((current_price - prev_close) / prev_close) * 100 if (current_price and prev_close) else np.nan
        return (round(current_price, 3) if current_price else np.nan,
                round(pct_change, 2) if pd.notna(pct_change) else np.nan)
    except Exception:
        return np.nan, np.nan
