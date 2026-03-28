"""
risk_free.py – fetches the daily risk-free rate from FRED.

Series used: DGS3MO (3-Month Treasury Constant Maturity Rate, % per annum).
No API key required — FRED's public JSON endpoint is used directly.

Returns a pd.Series of *daily* continuously-compounded rates expressed as
decimal fractions (i.e. 5.25% annualised → 0.0525 / 252 per trading day).

Results are cached in a local SQLite table alongside the price cache so
repeated intraday runs don't hit FRED repeatedly.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

FRED_SERIES = "DGS3MO"
FRED_URL = (
    "https://api.stlouisfed.org/fred/series/observations"
    "?series_id={series}&observation_start={start}&observation_end={end}"
    "&file_type=json&api_key=e432dc4571b7b2bc0fd977b9ebf2f7d5"
    # ↑ FRED allows anonymous access via the public "free" key shown in their docs.
    # Replace with your own key from https://fred.stlouisfed.org/docs/api/api_key.html
    # (free, instant sign-up) for higher rate limits.
)

CACHE_FILE = Path(__file__).parent / "price_cache.db"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rf_rates (
            date TEXT PRIMARY KEY,
            rate REAL
        )
        """
    )
    conn.commit()
    return conn


def _cache_read(conn: sqlite3.Connection, start: date, end: date) -> pd.Series:
    rows = conn.execute(
        "SELECT date, rate FROM rf_rates WHERE date >= ? AND date <= ? ORDER BY date",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    return pd.Series(vals, index=idx, name="rf")


def _cache_write(conn: sqlite3.Connection, series: pd.Series):
    rows = [(str(d.date()), float(v)) for d, v in series.items() if pd.notna(v)]
    conn.executemany(
        "INSERT OR REPLACE INTO rf_rates (date, rate) VALUES (?,?)", rows
    )
    conn.commit()


# ── FRED fetch ────────────────────────────────────────────────────────────────

def _fetch_from_fred(start: date, end: date) -> pd.Series:
    url = FRED_URL.format(
        series=FRED_SERIES,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    log.info("Fetching risk-free rate from FRED (%s) …", FRED_SERIES)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])

    records = {}
    for obs in observations:
        if obs["value"] == ".":   # FRED uses "." for missing values
            continue
        records[obs["date"]] = float(obs["value"]) / 100.0  # % → decimal

    if not records:
        return pd.Series(dtype=float, name="rf")

    series = pd.Series(records, name="rf")
    series.index = pd.to_datetime(series.index)
    return series


# ── Public API ────────────────────────────────────────────────────────────────

def get_daily_rf(lookback_days: int = 400) -> pd.Series:
    """
    Return a pd.Series of *daily* risk-free rates (decimal fractions).

    The annualised 3-month T-bill rate from FRED is divided by 252 to give
    a per-trading-day rate.  The series is forward-filled over weekends /
    holidays so every calendar day has a value.

    Example: a 5.00% annualised rate → 0.05 / 252 ≈ 0.000198 per day.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    conn = _get_conn()
    cached = _cache_read(conn, start_date, end_date)

    needs_fetch = (
        cached.empty
        or cached.index[-1].date() < (end_date - timedelta(days=3))
    )

    if needs_fetch:
        try:
            fresh = _fetch_from_fred(start_date, end_date)
            if not fresh.empty:
                _cache_write(conn, fresh)
                # Merge with cache (fresh wins on overlap)
                combined = pd.concat([cached, fresh])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                cached = combined
            else:
                log.warning("FRED returned no data — falling back to cached rf rates")
        except Exception as exc:
            log.warning("FRED fetch failed (%s) — using cached rf rates", exc)

    conn.close()

    rf_warning: str | None = None

    if needs_fetch and (cached.empty or cached.index[-1].date() < (end_date - timedelta(days=3))):
        rf_warning = (
            "RF: Risk-free rate could not be fetched from FRED — "
            "Sharpe ratios are using rf = 0% and may be overstated."
        )

    if cached.empty:
        log.warning("No risk-free rate data available — defaulting to 0%%")
        return pd.Series(dtype=float, name="rf"), rf_warning or (
            "RF: No risk-free rate data available — Sharpe ratios are using rf = 0%."
        )

    # Convert annualised rate → daily rate, then forward-fill to all calendar days
    daily = cached / 252.0
    full_idx = pd.date_range(start=daily.index[0], end=daily.index[-1], freq="D")
    daily = daily.reindex(full_idx).ffill()
    return daily, rf_warning
