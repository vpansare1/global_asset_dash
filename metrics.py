"""
metrics.py – all metric calculations live here.

Every public function must accept:
    series  : pd.Series of daily adjusted closing prices, DatetimeIndex
    as_of   : datetime.date  – the reference date for the calculation
    **kwargs: metric-specific parameters

Return: float | None  (None means not enough data)
"""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta


# ── Internal helpers ───────────────────────────────────────────────────────────

def _price_on_or_before(series: pd.Series, target: date) -> Optional[float]:
    """Closest available price on or before `target`."""
    sub = series[series.index.date <= target]
    return float(sub.iloc[-1]) if not sub.empty else None


def _slice_trailing(series: pd.Series, as_of: date, months: int) -> pd.Series:
    """Return daily prices for the trailing `months` months ending on as_of."""
    end_dt = pd.Timestamp(as_of)
    start_dt = end_dt - relativedelta(months=months)
    mask = (series.index >= start_dt) & (series.index <= end_dt)
    return series[mask]


def _daily_returns(price_series: pd.Series) -> pd.Series:
    return price_series.pct_change().dropna()


# ── Public metric functions ────────────────────────────────────────────────────

def momentum(series: pd.Series, as_of: date, months: int) -> Optional[float]:
    """
    Total return over the trailing `months` calendar months.
    End price: last available price on or before as_of.
    Start price: last available price on or before (as_of - months months).
    """
    end_price = _price_on_or_before(series, as_of)
    start_date = (pd.Timestamp(as_of) - relativedelta(months=months)).date()
    start_price = _price_on_or_before(series, start_date)

    if end_price is None or start_price is None or start_price == 0:
        return None
    return (end_price / start_price) - 1.0


def composite_momentum(
    series: pd.Series, as_of: date, month_list: list[int]
) -> Optional[float]:
    """
    Equal-weighted average of momentum across multiple lookback windows.
    Returns None if any individual momentum is unavailable.
    """
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
    """
    Annualised Sharpe ratio over trailing `months` months.

    rf : optional pd.Series of *daily* risk-free rates (decimal, e.g. 0.000198).
         Index must be DatetimeIndex.  If None or empty, rf defaults to 0.
         Sourced from FRED DGS3MO (3-month T-bill) via risk_free.get_daily_rf().
    """
    sliced = _slice_trailing(series, as_of, months)
    rets = _daily_returns(sliced)
    if len(rets) < 5:
        return None

    # Align rf to the same dates as rets; fill missing with 0
    if rf is not None and not rf.empty:
        rf_aligned = rf.reindex(rets.index, method="ffill").fillna(0.0)
    else:
        rf_aligned = pd.Series(0.0, index=rets.index)

    excess = rets - rf_aligned
    mean_exc = excess.mean()
    std_ret = rets.std(ddof=1)   # vol of total returns (standard convention)
    if std_ret == 0 or math.isnan(std_ret):
        return None
    return float(mean_exc / std_ret * math.sqrt(trading_days_per_year))


def serial_correlation(
    series: pd.Series, as_of: date, lag: int = 1, window: int = 21
) -> Optional[float]:
    """
    Pearson autocorrelation of daily returns over the trailing `window` trading days,
    with `lag` day shift.  Positive -> trending; Negative -> mean-reverting.
    """
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


def drawdown_from_high(
    series: pd.Series,
    as_of: date,
    years: int = 10,
) -> Optional[tuple[float, date]]:
    """
    Drawdown from the rolling high over the trailing `years` years.

    Returns (drawdown_pct, high_date) where drawdown_pct is negative (e.g. -0.15
    means 15% below the peak), and high_date is the date of that peak.
    Returns None if there is insufficient data.
    """
    end_dt = pd.Timestamp(as_of)
    start_dt = end_dt - relativedelta(years=years)
    mask = (series.index >= start_dt) & (series.index <= end_dt)
    sliced = series[mask].dropna()

    if sliced.empty:
        return None

    high_val = sliced.max()
    high_date = sliced.idxmax().date()
    current_price = _price_on_or_before(series, as_of)

    if current_price is None or high_val == 0:
        return None

    dd = (current_price / high_val) - 1.0
    return (dd, high_date)
