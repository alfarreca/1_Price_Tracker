# data_loader.py
import io
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


# ------------ Excel helpers ------------

def read_excel_to_df(uploaded_file, sheet_name: str) -> pd.DataFrame:
    # Works with Streamlit's UploadedFile
    xls = pd.ExcelFile(uploaded_file)
    df = pd.read_excel(xls, sheet_name=sheet_name)
    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]
    return df


def get_available_filters(df: pd.DataFrame) -> List[str]:
    # Offer common metadata filters if they exist and have >1 unique value
    candidates = [
        "Sector", "Industry Group", "Industry", "Theme",
        "Country", "Asset_Type", "Notes", "Name"
    ]
    out = []
    for c in candidates:
        if c in df.columns:
            uniq = df[c].dropna().unique()
            if len(uniq) > 1:
                out.append(c)
    return out


def apply_filter_selections(df: pd.DataFrame, selections: Dict[str, List[str]]) -> pd.DataFrame:
    out = df.copy()
    for col, vals in selections.items():
        if vals:
            out = out[out[col].isin(vals)]
    return out


# ------------ Price fetching & table builders ------------

def _safe_download(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    yfinance sometimes returns empty data; wrap and normalize.
    """
    try:
        df = yf.download(
            symbol,
            start=start,
            end=end + timedelta(days=1),  # inclusive last day
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            # Ensure DatetimeIndex timezone-naive (resample expects that)
            if isinstance(df.index, pd.DatetimeIndex):
                if df.index.tz is not None:
                    df.index = df.index.tz_convert("UTC").tz_localize(None)
            return df
    except Exception:
        pass
    return pd.DataFrame()


def fetch_friday_closes(symbol: str, weeks: int = 26) -> pd.Series | None:
    """
    Return a Series of Friday closes indexed by week-ending date.
    None if there is not enough data.
    """
    today = datetime.now(timezone.utc).date()
    # generous buffer to increase chance of getting enough Fridays
    lookback_days = weeks * 7 + 42
    start_date = datetime.combine(today - timedelta(days=lookback_days), datetime.min.time())
    end_date = datetime.combine(today, datetime.min.time())

    daily = _safe_download(symbol, start_date, end_date)
    if daily.empty or "Close" not in daily.columns:
        return None

    # Resample to W-FRI and take last available Close in each week
    weekly = daily["Close"].resample("W-FRI").last().dropna()

    # In thin markets/holidays, W-FRI can miss a print; try forward-fill within week if needed
    if weekly.empty and not daily.empty:
        # backstop: use business-weekly anchor (W-FRI via asfreq) then fill from last valid close
        idx = pd.date_range(daily.index.min(), daily.index.max(), freq="W-FRI")
        tmp = daily["Close"].reindex(idx, method="pad")
        weekly = tmp.dropna()

    if weekly.empty:
        return None

    # Keep the last `weeks` observations; require at least 2 to compute changes
    weekly = weekly.tail(weeks)
    if weekly.shape[0] < 2:
        return None

    return weekly


def _compute_live_and_intraday(symbols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute:
      - Intraday % Change (today vs prior close)
      - Live Price
      - Live % Change (today vs prior close)  [kept same definition for safety]
    If we fail to fetch, fill NaNs so the UI can still render.
    """
    live_rows = []
    intra_rows = []

    for sym in symbols:
        live_price = np.nan
        intraday_pct = np.nan
        live_pct = np.nan

        try:
            # 5d/1d to get prior close + latest close
            hist = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
            if not hist.empty and "Close" in hist.columns:
                close_vals = hist["Close"].dropna()
                if close_vals.shape[0] >= 2:
                    prev_close = float(close_vals.iloc[-2])
                    last_close = float(close_vals.iloc[-1])
                    live_price = last_close
                    if prev_close > 0:
                        change = last_close - prev_close
                        intraday_pct = (change / prev_close) * 100.0
                        live_pct = intraday_pct
        except Exception:
            pass

        live_rows.append({"Symbol": sym, "Live % Change": live_pct, "Live Price": live_price})
        intra_rows.append({"Symbol": sym, "Intraday % Change": intraday_pct})

    live_df = pd.DataFrame(live_rows)
    intra_df = pd.DataFrame(intra_rows)
    return live_df, intra_df


def build_price_tables(symbols: List[str], weeks: int = 26) -> Dict[str, pd.DataFrame]:
    """
    Build:
      - price_df: rows=symbols, cols=[labels...], plus 'Symbol' column
      - weekly_pct: rows=symbols, cols=[labels...]
      - norm_df: rows=symbols, cols=[labels...], normalized (start=100)
      - live_pct_df: ['Symbol','Live % Change','Live Price']
      - intraday_df: ['Symbol','Intraday % Change']
      - labels: list of week-ending date strings
      - skipped: list of symbols we couldn’t fetch
    """
    symbols = [str(s).strip() for s in symbols if str(s).strip()]
    series_map: Dict[str, pd.Series] = {}
    skipped: List[str] = []

    for sym in symbols:
        s = fetch_friday_closes(sym, weeks=weeks)
        if s is None or s.empty:
            skipped.append(sym)
            continue
        # ensure name for later alignment
        s.name = sym
        series_map[sym] = s

    if not series_map:
        raise ValueError(
            "No weekly price data could be fetched for the selected symbols. "
            "Check symbol formats/exchanges or broaden the date window."
        )

    # Align all series on the union of week-ending dates, then trim to last `weeks`
    all_df = pd.concat(series_map.values(), axis=1).T  # rows=symbols, cols=dates
    # Sort columns (dates) ascending; keep last `weeks`
    all_df = all_df.reindex(sorted(all_df.columns), axis=1)
    all_df = all_df.iloc[:, -weeks:]

    # Labels (week-ending dates as strings)
    labels = [c.strftime("%Y-%m-%d") for c in all_df.columns]

    # price_df in the shape analysis.py expects: include 'Symbol' column
    price_df = all_df.copy()
    price_df.insert(0, "Symbol", price_df.index)

    # Weekly % change per symbol per label
    weekly_pct = all_df.pct_change(axis=1) * 100.0

    # Normalized (start = 100)
    start_vals = all_df.iloc[:, 0].replace(0, np.nan)
    norm_df = all_df.divide(start_vals, axis=0) * 100.0

    # Live & intraday
    live_pct_df, intraday_df = _compute_live_and_intraday(list(all_df.index))

    pack = {
        "labels": labels,
        "price_df": price_df,             # rows = symbols
        "weekly_pct": weekly_pct,         # index = symbols, columns = labels
        "live_pct_df": live_pct_df,       # ['Symbol','Live % Change','Live Price']
        "intraday_df": intraday_df,       # ['Symbol','Intraday % Change']
        "norm_df": norm_df,               # index = symbols, columns = labels
        "skipped": skipped,               # symbols with no data
    }
    return pack
