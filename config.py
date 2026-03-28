import metrics as m

CATEGORIES = [
    {
        "name": "Global Equities",
        "icon": "📈",
        "tickers": ["VOO", "VEA", "VWO", "QVAL", "IVAL", "QMOM", "IMOM"],
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

LOOKBACK_DAYS = 400

METRICS = [
    {"label": "1M Mom",      "fn": m.momentum,           "fmt": "{:+.1%}", "color": True,  "kwargs": {"months": 1}},
    {"label": "3M Mom",      "fn": m.momentum,           "fmt": "{:+.1%}", "color": True,  "kwargs": {"months": 3}},
    {"label": "6M Mom",      "fn": m.momentum,           "fmt": "{:+.1%}", "color": True,  "kwargs": {"months": 6}},
    {"label": "12M Mom",     "fn": m.momentum,           "fmt": "{:+.1%}", "color": True,  "kwargs": {"months": 12}},
    {"label": "1+3+6M Comp", "fn": m.composite_momentum, "fmt": "{:+.1%}", "color": True,  "kwargs": {"month_list": [1, 3, 6]}},
    {"label": "3+12M Comp",  "fn": m.composite_momentum, "fmt": "{:+.1%}", "color": True,  "kwargs": {"month_list": [3, 12]}},
    {"label": "1M Sharpe",   "fn": m.sharpe,             "fmt": "{:+.2f}", "color": True,  "kwargs": {"months": 1}},
    {"label": "12M Sharpe",  "fn": m.sharpe,             "fmt": "{:+.2f}", "color": True,  "kwargs": {"months": 12}},
    {"label": "SerCorr 21d", "fn": m.serial_correlation, "fmt": "{:+.2f}", "color": False, "kwargs": {"lag": 1, "window": 21}},
]