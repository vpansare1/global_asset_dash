"""
data_loader.py – fetches and caches adjusted closing prices via yfinance.

Price data is cached in a local SQLite database (price_cache.db) so repeated
runs on the same day are fast and don't hammer the Yahoo Finance API.
"""

import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "price_cache.db"


# ── SQLite cache helpers ───────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT,
            date   TEXT,
            close  REAL,
            PRIMARY KEY (ticker, date)
        )
        """
    )
    conn.commit()
    return conn


def _cache_read(conn: sqlite3.Connection, ticker: str, start: date, end: date) -> pd.Series:
    rows = conn.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date>=? AND date<=? ORDER BY date",
        (ticker, start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    return pd.Series(vals, index=idx, name=ticker)


def _cache_write(conn: sqlite3.Connection, ticker: str, series: pd.Series):
    rows = [(ticker, str(d.date()), float(v)) for d, v in series.items() if pd.notna(v)]
    conn.executemany(
        "INSERT OR REPLACE INTO prices (ticker, date, close) VALUES (?,?,?)", rows
    )
    conn.commit()


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_prices(tickers: list[str], lookback_days: int = 400) -> tuple[pd.DataFrame, list[str]]:
    """
    Return (prices_df, failed_tickers).
    prices_df: DataFrame of adjusted closing prices (columns = tickers).
    failed_tickers: list of tickers for which no data could be retrieved.
    Uses a local SQLite cache; fetches missing / stale data from yfinance.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    conn = _get_conn()
    all_series: dict[str, pd.Series] = {}

    for ticker in tickers:
        cached = _cache_read(conn, ticker, start_date, end_date)

        # Determine whether we need a fresh fetch
        needs_fetch = (
            cached.empty
            or cached.index[-1].date() < (end_date - timedelta(days=1))
        )

        if needs_fetch:
            log.info("Fetching %s from yfinance …", ticker)
            try:
                raw = yf.download(
                    ticker,
                    start=start_date.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    auto_adjust=True,
                    progress=False,
                )
                if raw.empty:
                    log.warning("No data returned for %s", ticker)
                    all_series[ticker] = cached if not cached.empty else pd.Series(dtype=float, name=ticker)
                    if cached.empty:
                        continue  # will be detected as failed
                    continue

                # Handle MultiIndex columns (yfinance ≥ 0.2.x)
                if isinstance(raw.columns, pd.MultiIndex):
                    series = raw["Close"][ticker] if ticker in raw["Close"].columns else raw["Close"].iloc[:, 0]
                else:
                    series = raw["Close"]

                series.name = ticker
                _cache_write(conn, ticker, series)
                all_series[ticker] = series
            except Exception as exc:
                log.error("Failed to fetch %s: %s", ticker, exc)
                all_series[ticker] = cached if not cached.empty else pd.Series(dtype=float, name=ticker)
        else:
            log.debug("Cache hit for %s", ticker)
            all_series[ticker] = cached

    conn.close()

    df = pd.DataFrame(all_series)
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)

    failed = [t for t in tickers if t not in df.columns or df[t].dropna().empty]
    return df, failed
