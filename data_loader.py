import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# ---------- Date helpers ----------
def get_last_n_weeks(n: int):
    """
    Returns a list of (monday, friday) tuples for the last n weeks
    aligned to Friday, and the last Friday date.
    """
    today = datetime.today()
    offset = (today.weekday() - 4) % 7  # 4 = Friday
    last_friday = today - timedelta(days=offset)
    weeks = [
        (last_friday - timedelta(weeks=i) - timedelta(days=4),  # Monday
         last_friday - timedelta(weeks=i))                      # Friday
        for i in reversed(range(n))
    ]
    return weeks, last_friday

# ---------- Yahoo helpers ----------
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
    if closes.empty:
        return np.nan
    return round(float(closes.iloc[-1]), 3)

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
               round(pct_change, 2) if isinstance(pct_change, (int, float, np.floating)) else np.nan
    except Exception:
        return np.nan, np.nan

# ---------- Analytics ----------
def calculate_max_drawdown(prices):
    """
    prices: 1D iterable of prices (floats). Returns drawdown in % (negative number).
    """
    if prices is None or len(prices) < 2:
        return 0.0
    arr = np.array(prices, dtype=np.float64)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    return float(drawdowns.min() * 100)

# ---------- IO / Filtering ----------
def read_excel_to_df(uploaded_file, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(uploaded_file, sheet_name=sheet_name)

def get_available_filters(df: pd.DataFrame):
    candidates = ["Sector", "Industry Group", "Industry", "Theme", "Country", "Asset_Type"]
    return [c for c in candidates if c in df.columns]

def apply_filter_selections(df: pd.DataFrame, selections: dict) -> pd.DataFrame:
    out = df.copy()
    for col, vals in selections.items():
        if col in out.columns and vals:
            out = out[out[col].isin(vals)]
    return out

# ---------- Pipeline to build all tables ----------
def build_price_tables(symbols):
    """
    Given a list of symbols, compute:
    - labels (list of week labels)
    - price_df (wide table with weekly Friday closes + current)
    - weekly_pct (weekly % changes)
    - live_pct_df (df with Live % Change vs last Friday close)
    - intraday_df (df with Live Price and Intraday % Change vs prev close)
    - norm_df (prices only, indexed by Symbol; columns=labels)
    """
    weeks, last_friday = get_last_n_weeks(6)
    current_week_start = last_friday

    intraday_price, intraday_change, all_data = {}, {}, {}
    for sym in symbols:
        price, change = fetch_intraday_live_price(sym)
        intraday_price[sym] = price
        intraday_change[sym] = change

        closes = fetch_friday_closes(sym, weeks)
        current = fetch_current_week_close(sym, current_week_start)
        all_data[sym] = closes + [current]

    labels = [f"{m.strftime('%b %d')}→{f.strftime('%b %d')}" for m, f in weeks]
    labels += [f"{current_week_start.strftime('%b %d')}→{datetime.today().strftime('%b %d')}"]

    price_df = pd.DataFrame(all_data).T
    price_df.columns = labels
    price_df.index.name = "Symbol"
    price_df = price_df.reset_index()

    # ensure numeric
    for col in labels:
        price_df[col] = pd.to_numeric(price_df[col], errors="coerce")

    # Live % change vs last Friday close
    live_pct_change = {}
    for sym in all_data:
        last_friday_close = all_data[sym][-2] if len(all_data[sym]) >= 2 else np.nan
        current_price = all_data[sym][-1]
        if pd.notna(last_friday_close) and pd.notna(current_price) and last_friday_close != 0:
            live_change = ((current_price - last_friday_close) / last_friday_close) * 100
        else:
            live_change = np.nan
        live_pct_change[sym] = round(live_change, 2) if pd.notna(live_change) else np.nan

    live_pct_df = pd.DataFrame.from_dict(live_pct_change, orient='index', columns=["Live % Change"]).reset_index().rename(columns={"index": "Symbol"})
    intraday_df = pd.DataFrame({"Symbol": list(intraday_price.keys()),
                                "Live Price": list(intraday_price.values()),
                                "Intraday % Change": list(intraday_change.values())})

    # Build normalized tables
    norm_df = price_df.set_index("Symbol")[labels]
    safe_norm = norm_df.copy()
    safe_norm = safe_norm.where(norm_df.iloc[:, 0] != 0)
    normed = safe_norm.div(norm_df.iloc[:, 0], axis=0)  # not returned but used for checks

    weekly_pct = norm_df.pct_change(axis=1) * 100

    # Remove degenerate last column if it's “start==end” or all equal
    last_label = weekly_pct.columns[-1]
    left, right = last_label.split("→")
    if left == right or weekly_pct.iloc[:, -1].nunique() <= 1:
        weekly_pct = weekly_pct.iloc[:, :-1]
        norm_df = norm_df.iloc[:, :-1]
        labels = labels[:-1]

    return {
        "labels": labels,
        "price_df": price_df,
        "weekly_pct": weekly_pct,
        "live_pct_df": live_pct_df,
        "intraday_df": intraday_df,
        "norm_df": norm_df
    }
