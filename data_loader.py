# data_loader.py
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


# ------------ Excel helpers ------------

def read_excel_to_df(uploaded_file, sheet_name: str | None = None) -> pd.DataFrame:
    """Read an Excel file (Streamlit UploadedFile or path) and return a DataFrame."""
    xls = pd.ExcelFile(uploaded_file)
    if sheet_name is None:
        sheet_name = xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def get_available_filters(df: pd.DataFrame) -> List[str]:
    """Suggest filterable metadata columns if present."""
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


# ------------ Risk helpers ------------

def calculate_max_drawdown(prices: pd.Series) -> float:
    """
    Max drawdown in percent (negative number).
    `prices` should be a price-like series (no NaNs ideally).
    """
    if prices is None or prices.empty:
        return np.nan
    s = prices.astype(float).dropna()
    if s.empty:
        return np.nan
    cum_max = s.cummax()
    drawdown = (s / cum_max) - 1.0
    return float(drawdown.min() * 100.0)


# ------------ Price fetching & table builders ------------

def _safe_download(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    yfinance sometimes returns empty data; wrap and normalize.
    """
    try:
        df = yf.download(
            symbol,
            start=start,
            end=end + timedelta(days=1),  # include last day
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
                df.index = df.index.tz_convert("UTC").tz_localize(None)
            return df
    except Exception:
        pass
    return pd.DataFrame()


def fetch_friday_closes(symbol: str, weeks: int = 26) -> pd.Series | None:
    """Return a Series of Friday closes (index: week-ending date). None if not enough data."""
    today = datetime.now(timezone.utc).date()
    lookback_days = weeks * 7 + 42  # generous buffer for holidays/gaps
    start_date = datetime.combine(today - timedelta(days=lookback_days), datetime.min.time())
    end_date = datetime.combine(today, datetime.min.time())

    daily = _safe_download(symbol, start_date, end_date)
    if daily.empty or "Close" not in daily.columns:
        return None

    weekly = daily["Close"].resample("W-FRI").last().dropna()

    # Backstop for thin markets: reindex on W-FRI and forward-fill
    if weekly.empty and not daily.empty:
        idx = pd.date_range(daily.index.min(), daily.index.max(), freq="W-FRI")
        tmp = daily["Close"].reindex(idx, method="pad")
        weekly = tmp.dropna()

    if weekly.empty:
        return None

    weekly = weekly.tail(weeks)
    if weekly.shape[0] < 2:
        return None

    return weekly


def _compute_live_and_intraday(symbols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compute Live Price and Intraday % Change from last close vs prior close."""
    live_rows, intra_rows = [], []

    for sym in symbols:
        live_price = np.nan
        intraday_pct = np.nan
        live_pct = np.nan
        try:
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

    return pd.DataFrame(live_rows), pd.DataFrame(intra_rows)


def build_price_tables(symbols: List[str], weeks: int = 26) -> Dict[str, pd.DataFrame | list]:
    """
    Build & return:
      - labels: list[str] week-ending YYYY-MM-DD
      - price_df: rows=symbols, cols=['Symbol', *labels]
      - weekly_pct: DataFrame (index=symbols, columns=labels)
      - norm_df: DataFrame (index=symbols, columns=labels, start=100)
      - live_pct_df: ['Symbol','Live % Change','Live Price']
      - intraday_df: ['Symbol','Intraday % Change']
      - skipped: list[str] of symbols with no data
    """
    symbols = [str(s).strip() for s in symbols if str(s).strip()]
    series_map: Dict[str, pd.Series] = {}
    skipped: List[str] = []

    for sym in symbols:
        s = fetch_friday_closes(sym, weeks=weeks)
        if s is None or s.empty:
            skipped.append(sym)
            continue
        s.name = sym
        series_map[sym] = s

    if not series_map:
        raise ValueError(
            "No weekly price data could be fetched for the selected symbols. "
            "Check symbol formats/exchanges or broaden the date window."
        )

    # Align all series on union of week-ending dates, then keep last `weeks`
    all_df = pd.concat(series_map.values(), axis=1).T  # rows=symbols, cols=dates
    all_df = all_df.reindex(sorted(all_df.columns), axis=1)
    all_df = all_df.iloc[:, -weeks:]

    labels = [c.strftime("%Y-%m-%d") for c in all_df.columns]

    price_df = all_df.copy()
    price_df.insert(0, "Symbol", price_df.index)

    weekly_pct = all_df.pct_change(axis=1) * 100.0

    start_vals = all_df.iloc[:, 0].replace(0, np.nan)
    norm_df = all_df.divide(start_vals, axis=0) * 100.0

    live_pct_df, intraday_df = _compute_live_and_intraday(list(all_df.index))

    return {
        "labels": labels,
        "price_df": price_df,
        "weekly_pct": weekly_pct,
        "norm_df": norm_df,
        "live_pct_df": live_pct_df,
        "intraday_df": intraday_df,
        "skipped": skipped,
    }
