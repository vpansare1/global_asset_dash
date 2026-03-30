"""
risk_free.py – fetches the daily risk-free rate from FRED.

Series used: DGS3MO (3-Month Treasury Constant Maturity Rate, % per annum).
Requires a free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
Set it as the environment variable FRED_API_KEY (stored as a GitHub secret).

Results are cached in a local SQLite table so repeated intraday runs don't
hit FRED on every execution.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

FRED_SERIES  = "DGS3MO"
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_URL     = (
    "https://api.stlouisfed.org/fred/series/observations"
    "?series_id={{series}}&observation_start={{start}}&observation_end={{end}}"
    "&file_type=json&api_key={api_key}"
).format(api_key=FRED_API_KEY)

CACHE_FILE = Path(__file__).parent / "price_cache.db"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rf_rates (date TEXT PRIMARY KEY, rate REAL)"
    )
    conn.commit()
    return conn


def _cache_read(conn: sqlite3.Connection, start: date, end: date) -> pd.Series:
    rows = conn.execute(
        "SELECT date, rate FROM rf_rates WHERE date >= ? AND date <= ? ORDER BY date",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float, name="rf")
    return pd.Series(
        [r[1] for r in rows],
        index=pd.to_datetime([r[0] for r in rows]),
        name="rf",
    )


def _cache_write(conn: sqlite3.Connection, series: pd.Series) -> None:
    rows = [(str(d.date()), float(v)) for d, v in series.items() if pd.notna(v)]
    conn.executemany(
        "INSERT OR REPLACE INTO rf_rates (date, rate) VALUES (?,?)", rows
    )
    conn.commit()


# ── FRED fetch ────────────────────────────────────────────────────────────────

def _fetch_from_fred(start: date, end: date) -> pd.Series:
    if not FRED_API_KEY:
        raise ValueError(
            "FRED_API_KEY environment variable is not set. "
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html "
            "and add it as a GitHub secret named FRED_API_KEY."
        )
    url = FRED_URL.format(series=FRED_SERIES, start=start.isoformat(), end=end.isoformat())
    log.info("Fetching risk-free rate from FRED (%s) ...", FRED_SERIES)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])

    records = {
        obs["date"]: float(obs["value"]) / 100.0
        for obs in observations
        if obs["value"] != "."
    }
    if not records:
        return pd.Series(dtype=float, name="rf")

    series = pd.Series(records, name="rf")
    series.index = pd.to_datetime(series.index)
    return series


# ── Public API ────────────────────────────────────────────────────────────────

def get_daily_rf(lookback_days: int = 400) -> tuple[pd.Series, str | None]:
    """
    Return (daily_rf_series, warning_or_None).

    daily_rf_series: annualised rate / 252, forward-filled over weekends.
                     Empty Series if data is unavailable.
    warning:         human-readable string if fetch failed, else None.
    """
    end_date   = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    conn   = _get_conn()
    cached = _cache_read(conn, start_date, end_date)

    needs_fetch = (
        cached.empty
        or cached.index[-1].date() < (end_date - timedelta(days=3))
    )

    rf_warning: str | None = None

    if needs_fetch:
        try:
            fresh = _fetch_from_fred(start_date, end_date)
            if not fresh.empty:
                _cache_write(conn, fresh)
                combined = pd.concat([cached, fresh])
                cached = combined[~combined.index.duplicated(keep="last")].sort_index()
                log.info(
                    "RF rate updated. Latest: %.2f%% annualised",
                    cached.iloc[-1] * 100,
                )
            else:
                log.warning("FRED returned no data — falling back to cached rf rates")
                rf_warning = (
                    "RF: FRED returned no data — "
                    "Sharpe ratios are using rf = 0% and may be overstated."
                )
        except Exception as exc:
            log.warning("FRED fetch failed (%s)", exc)
            rf_warning = (
                f"RF: Risk-free rate fetch failed ({exc}) — "
                "Sharpe ratios are using rf = 0% and may be overstated."
            )

    conn.close()

    if cached.empty:
        return (
            pd.Series(dtype=float, name="rf"),
            rf_warning or "RF: No risk-free rate data available — Sharpe ratios are using rf = 0%.",
        )

    # Convert annualised → daily, forward-fill over weekends / holidays
    daily    = cached / 252.0
    full_idx = pd.date_range(start=daily.index[0], end=daily.index[-1], freq="D")
    daily    = daily.reindex(full_idx).ffill()
    return daily, rf_warning
