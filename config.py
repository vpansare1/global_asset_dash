"""
config.py – single source of truth for tickers, categories, and metrics.

To add a new ticker:     append it to the relevant category's "tickers" list.
To add a new category:   add a new dict to CATEGORIES.
To add a new metric:     implement a function in metrics.py then append an entry to METRICS.
"""

import metrics as m

# ── Categories & tickers ──────────────────────────────────────────────────────

CATEGORIES = [
    {
        "name": "Global Equities",
        "icon": "📈",
        "tickers": ["VOO", "VEA", "VWO", "QVAL", "IVAL", "QMOM", "IMOM"],
    },
    
    {
        "name": "Portable alpha",
        "icon": "$$$",
        "tickers": ["RSST", "RSSY", "RSSB", "MATE", "GDE"],   
    },
    {
        "name": "Bonds",
        "icon": "🏦",
        "tickers": ["SGOV", "VGSH", "VGIT", "GOVZ"],
    },
    {
        "name": "Alternatives",
        "icon": "⚡",
        "tickers": ["GLD", "BTC-USD", "BTAL", "AHLT", "QMHIX"],
    },
    {
        "name": "Low Beta",
        "icon": "🛡️",
        "tickers": ["XLU", "XLV", "XLP"],
    },
]

# ── Global settings ───────────────────────────────────────────────────────────

# How many calendar days of history to pull from yfinance
LOOKBACK_DAYS = 3800  # ~10 years + buffer for drawdown metric

# ── Metrics registry ──────────────────────────────────────────────────────────
# Each entry:
#   label   – column header shown in the dashboard
#   fn      – callable from metrics.py  (signature: fn(series, as_of, **kwargs) -> float|None)
#   fmt     – Python format string applied to the value for display
#   color   – True  → green/red momentum colouring
#             False → no colouring (or custom logic handled in renderer)
#   kwargs  – extra keyword args forwarded to fn

METRICS = [
    # ── Point-in-time momentum ───────────────────────────────────────────────
    {
        "label":  "1M Mom",
        "fn":      m.momentum,
        "fmt":    "{:+.1%}",
        "color":   True,
        "kwargs": {"months": 1},
    },
    {
        "label":  "3M Mom",
        "fn":      m.momentum,
        "fmt":    "{:+.1%}",
        "color":   True,
        "kwargs": {"months": 3},
    },
    {
        "label":  "6M Mom",
        "fn":      m.momentum,
        "fmt":    "{:+.1%}",
        "color":   True,
        "kwargs": {"months": 6},
    },
    {
        "label":  "12M Mom",
        "fn":      m.momentum,
        "fmt":    "{:+.1%}",
        "color":   True,
        "kwargs": {"months": 12},
    },
    # ── Composite momentum ───────────────────────────────────────────────────
    {
        "label":  "1+3+6M Comp",
        "fn":      m.composite_momentum,
        "fmt":    "{:+.1%}",
        "color":   True,
        "kwargs": {"month_list": [1, 3, 6]},
    },
    {
        "label":  "3+12M Comp",
        "fn":      m.composite_momentum,
        "fmt":    "{:+.1%}",
        "color":   True,
        "kwargs": {"month_list": [3, 12]},
    },
    # ── Risk-adjusted ────────────────────────────────────────────────────────
    {
        "label":  "1M Sharpe",
        "fn":      m.sharpe,
        "fmt":    "{:+.2f}",
        "color":   True,
        "kwargs": {"months": 1},
    },
    {
        "label":  "12M Sharpe",
        "fn":      m.sharpe,
        "fmt":    "{:+.2f}",
        "color":   True,
        "kwargs": {"months": 12},
    },
    # ── Drawdown ─────────────────────────────────────────────────────────────
    {
        "label":  "10Y Drawdown",
        "fn":      m.drawdown_from_high,
        "fmt":    "{:.1%}",       # applied to the float component only
        "color":   False,          # renderer handles drawdown colouring separately
        "type":   "drawdown",      # signals renderer to use special two-value cell
        "kwargs": {"years": 10},
    },
    # ── Serial correlation ───────────────────────────────────────────────────
    {
        "label":  "SerCorr 21d",
        "fn":      m.serial_correlation,
        "fmt":    "{:+.2f}",
        "color":   False,   # neutral – not a simple positive/negative call
        "kwargs": {"lag": 1, "window": 21},
    },
]
