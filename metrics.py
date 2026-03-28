from __future__ import annotations
import math
from datetime import date
from typing import Optional
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta


def _price_on_or_before(series: pd.Series, target: date) -> Optional[float]:
    sub = series[series.index.date <= target]
    return float(sub.iloc[-1]) if not sub.empty else None


def _slice_trailing(series: pd.Series, as_of: date, months: int) -> pd.Series:
    end_dt = pd.Timestamp(as_of)
    start_dt = end_dt - relativedelta(months=months)
    mask = (series.index >= start_dt) & (series.index <= end_dt)
    return series[mask]


def _daily_returns(price_series: pd.Series) -> pd.Series:
    return price_series.pct_change().dropna()


def momentum(series: pd.Series, as_of: date, months: int) -> Optional[float]:
    end_price = _price_on_or_before(series, as_of)
    start_date = (pd.Timestamp(as_of) - relativedelta(months=months)).date()
    start_price = _price_on_or_before(series, start_date)
    if end_price is None or start_price is None or start_price == 0:
        return None
    return (end_price / start_price) - 1.0


def composite_momentum(series: pd.Series, as_of: date, month_list: list[int]) -> Optional[float]:
    values = [momentum(series, as_of, m) for m in month_list]
    if any(v is None for v in values):
        return None
    return float(np.mean(values))


def sharpe(
    series: pd.Series,
    as_of: date,
    months: int,
    rf: Optional[pd.Series] = None,
    trading_days_per_year: int = 252,
) -> Optional[float]:
    sliced = _slice_trailing(series, as_of, months)
    rets = _daily_returns(sliced)
    if len(rets) < 5:
        return None
    if rf is not None and not rf.empty:
        rf_aligned = rf.reindex(rets.index, method="ffill").fillna(0.0)
    else:
        rf_aligned = pd.Series(0.0, index=rets.index)
    excess = rets - rf_aligned
    mean_exc = excess.mean()
    std_ret = rets.std(ddof=1)
    if std_ret == 0 or math.isnan(std_ret):
        return None
    return float(mean_exc / std_ret * math.sqrt(trading_days_per_year))


def serial_correlation(
    series: pd.Series, as_of: date, lag: int = 1, window: int = 21
) -> Optional[float]:
    end_dt = pd.Timestamp(as_of)
    sliced = series[series.index <= end_dt].tail(window + lag + 1)
    rets = _daily_returns(sliced)
    if len(rets) < window + lag:
        return None
    r0 = rets.iloc[lag:].values
    r_lag = rets.iloc[:-lag].values if lag > 0 else rets.values
    if len(r0) < 3:
        return None
    corr = float(np.corrcoef(r0, r_lag)[0, 1])
    return corr if not math.isnan(corr) else None