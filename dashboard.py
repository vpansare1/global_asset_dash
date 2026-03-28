"""
Momentum Dashboard
==================
Computes momentum metrics across asset categories and outputs:
  - An interactive HTML dashboard
  - A PNG snapshot

Usage:
  python dashboard.py                  # uses today's date
  python dashboard.py --date 2024-01-15
"""

import argparse
import inspect
import logging
from datetime import date
from pathlib import Path

import config
import data_loader
import metrics as m
import renderer
import risk_free

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def build_table(prices, ticker_list, as_of: date, rf=None) -> list[dict]:
    rows = []
    for ticker in ticker_list:
        if ticker not in prices.columns:
            continue
        series = prices[ticker].dropna()
        if series.empty:
            continue
        row = {"Ticker": ticker}
        for metric_cfg in config.METRICS:
            kwargs = dict(metric_cfg.get("kwargs", {}))
            sig = inspect.signature(metric_cfg["fn"])
            if "rf" in sig.parameters and rf is not None:
                kwargs["rf"] = rf
            try:
                value = metric_cfg["fn"](series, as_of=as_of, **kwargs)
            except Exception as exc:
                log.debug("Could not compute %s for %s: %s", metric_cfg["label"], ticker, exc)
                value = None
            row[metric_cfg["label"]] = value
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Run momentum dashboard")
    parser.add_argument("--date", help="As-of date YYYY-MM-DD (default: today)")
    parser.add_argument("--output-dir", default="output", help="Directory for output files")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.date) if args.date else date.today()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []

    # ── Risk-free rate ────────────────────────────────────────────────────────
    log.info("Fetching risk-free rate from FRED …")
    rf, rf_warning = risk_free.get_daily_rf(lookback_days=config.LOOKBACK_DAYS)
    if rf_warning:
        log.warning(rf_warning)
        warnings.append(rf_warning)
    else:
        log.info("  Latest 3M T-bill (annualised): %.2f%%", rf.iloc[-1] * 252 * 100)

    # ── Price data ────────────────────────────────────────────────────────────
    log.info("Fetching price data …")
    all_tickers = [t for cat in config.CATEGORIES for t in cat["tickers"]]
    prices, failed_tickers = data_loader.fetch_prices(
        all_tickers, lookback_days=config.LOOKBACK_DAYS
    )

    if failed_tickers:
        failed_str = ", ".join(failed_tickers)
        msg = f"DA: Price data unavailable for: {failed_str} — these rows are excluded."
        log.warning(msg)
        warnings.append(msg)

    # ── Compute metrics ───────────────────────────────────────────────────────
    log.info("Computing metrics …")
    sections = []
    for cat in config.CATEGORIES:
        rows = build_table(prices, cat["tickers"], as_of, rf=rf if not rf.empty else None)
        sections.append({"name": cat["name"], "icon": cat["icon"], "rows": rows})

    # ── Render ────────────────────────────────────────────────────────────────
    log.info("Rendering HTML …")
    html_path = output_dir / f"dashboard_{as_of}.html"
    renderer.render_html(
        sections, config.METRICS, as_of, html_path,
        rf_rate_ann=rf.iloc[-1] * 252 if not rf.empty else None,
        warnings=warnings,
    )

    log.info("Rendering PNG …")
    png_path = output_dir / f"dashboard_{as_of}.png"
    renderer.render_png(html_path, png_path)

    log.info("Done.  HTML → %s  |  PNG → %s", html_path, png_path)


if __name__ == "__main__":
    main()
