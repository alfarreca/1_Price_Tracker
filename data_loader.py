# data_loader.py
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# ---------- Dates ----------
def get_last_n_weeks(n: int):
    """
    Returns:
      weeks: list[(monday, friday)] for the last n completed Friday weeks
      last_friday: datetime for the most recent Friday
    """
    today = datetime.today()
    offset = (today.weekday() - 4) % 7  # 4=Friday
    last_friday = today - timedelta(days=offset)
    weeks = [
        (last_friday - timedelta(weeks=i) - timedelta(days=4),  # Monday
         last_friday - timedelta(weeks=i))                      # Friday
        for i in reversed(range(n))
    ]
    return weeks, last_friday

# ---------- Yahoo fetchers ----------
def fetch_friday_closes(symbol: str, weeks):
    start_date, end_date = weeks[0][0], weeks[-1][1]
    df = yf.download(symbol, start=start_date, end=end_date + timedelta(days=1),
                     interval="1d", progress=False)
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

def fetch_current_week_close(symbol: str, current_week_start):
    today = datetime.today()
    df = yf.download(symbol, start=current_week_start, end=today + timedelta(days=1),
                     interval="1d", progress=False)
    if df.empty or "Close" not in df.columns:
        return np.nan
    closes = df["Close"].dropna()
    return round(float(closes.iloc[-1]), 3) if not closes.empty else np.nan

def fetch_intraday_live_price(symbol: str):
    try:
        info = yf.Ticker(symbol).info
        current_price = info.get("regularMarketPrice")
        prev_close = info.get("regularMarketPreviousClose")
        if current_price is not None and prev_close not in (None, 0):
            pct_change = ((current_price - prev_close) / prev_close) * 100
        else:
            pct_change = np.nan
        return round(current_price, 3) if current_price is not None else np.nan, \
               round(pct_change, 2) if not np.isnan(pct_change) else np.nan
    except Exception:
        return np.nan, np.nan

# ---------- Analytics helpers ----------
def calculate_max_drawdown(series_like):
    """series_like: iterable of numeric prices (already aligned by week). Returns drawdown % (negative)."""
    values = pd.to_numeric(pd.Series(series_like), errors="coerce").to_numpy(dtype=np.float64)
    if values.size < 2 or np.all(~np.isfinite(values)):
        return 0.0
    running_max = np.maximum.accumulate(values)
    drawdowns = (values - running_max) / running_max
    return float(np.nanmin(drawdowns) * 100)

# ---------- IO / filtering ----------
def read_first_sheet_names(xls: pd.ExcelFile):
    return xls.sheet_names

def read_sheet(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(xls, sheet_name=sheet_name)

def apply_sidebar_filters(df: pd.DataFrame, st):
    """Interactive filtering. Returns filtered df and the dict of selections."""
    filter_cols = ["Sector", "Industry Group", "Industry", "Theme", "Country", "Asset_Type"]
    selections = {}
    for col in filter_cols:
        if col in df.columns:
            unique_vals = df[col].dropna().unique().tolist()
            chosen = st.sidebar.multiselect(f"Filter by {col}", sorted(unique_vals))
            if chosen:
                df = df[df[col].isin(chosen)]
                selections[col] = chosen
    return df, selections
