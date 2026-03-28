"""
renderer.py – turns computed metric rows into HTML and PNG outputs.

HTML: single scrollable table with category group-header rows, sortable
      columns, and green/red cell colouring.

PNG:  Playwright → imgkit → matplotlib fallback.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ── Colour helpers ────────────────────────────────────────────────────────────

def _momentum_color(value: float) -> str:
    if value is None or math.isnan(value):
        return "transparent"
    cap = 0.30
    intensity = min(abs(value) / cap, 1.0)
    if value > 0:
        r = int(255 - intensity * 100)
        g = int(255 - intensity * 30)
        b = int(255 - intensity * 100)
    else:
        r = int(255 - intensity * 30)
        g = int(255 - intensity * 100)
        b = int(255 - intensity * 100)
    return f"rgb({r},{g},{b})"


def _fmt(value: Any, fmt_str: str) -> str:
    if value is None:
        return "—"
    try:
        return fmt_str.format(value)
    except (ValueError, TypeError):
        return "—"


# ── HTML renderer ─────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Momentum Dashboard – {as_of}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:      #0b0d11;
    --surface: #12151c;
    --border:  #1e2330;
    --accent:  #3b82f6;
    --text:    #cbd5e1;
    --muted:   #475569;
    --cat-bg:  #0f1117;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    padding: 12px 16px 20px;
  }}

  /* ── Top bar ── */
  .topbar {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}
  .topbar h1 {{
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
  }}
  .topbar .meta {{
    font-size: 10px;
    color: var(--text);
  }}

  /* ── Warning banners ── */
  .warnings {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 8px;
  }}
  .warn {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.04em;
    border: 1px solid;
  }}
  .warn-rf {{
    background: rgba(234,179,8,0.12);
    border-color: rgba(234,179,8,0.35);
    color: #fde047;
  }}
  .warn-data {{
    background: rgba(239,68,68,0.12);
    border-color: rgba(239,68,68,0.35);
    color: #fca5a5;
  }}
  .warn-icon {{ font-size: 12px; flex-shrink: 0; }}

  /* ── Single scrollable table wrapper ── */
  .tbl-wrap {{
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 6px;
  }}

  table {{
    border-collapse: collapse;
    white-space: nowrap;
    width: max-content;
    min-width: 100%;
  }}

  /* ── Column headers ── */
  thead th {{
    background: var(--surface);
    color: var(--text);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 5px 10px;
    text-align: right;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 2;
  }}
  thead th:first-child {{
    text-align: left;
    position: sticky;
    left: 0;
    z-index: 3;
    min-width: 90px;
  }}
  thead th:hover {{ color: var(--text); }}
  thead th.sorted-asc::after  {{ content: " ▲"; font-size: 8px; }}
  thead th.sorted-desc::after {{ content: " ▼"; font-size: 8px; }}

  /* ── Category separator rows ── */
  tr.cat-row td {{
    background: var(--cat-bg);
    color: var(--text);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    padding: 4px 10px;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
  }}
  tr.cat-row:first-child td {{ border-top: none; }}

  /* ── Data rows ── */
  tbody tr.data-row {{
    border-bottom: 1px solid var(--border);
  }}
  tbody tr.data-row:last-child {{ border-bottom: none; }}
  tbody tr.data-row:hover {{ background: rgba(255,255,255,0.025); }}

  td {{
    padding: 3px 10px;
    text-align: right;
  }}
  td:first-child {{
    text-align: left;
    font-weight: 500;
    color: var(--text);
    position: sticky;
    left: 0;
    background: var(--bg);
    z-index: 1;
    border-right: 1px solid var(--border);
  }}
  tr.data-row:hover td:first-child {{ background: #0f1219; }}

  /* ── Coloured metric cells ── */
  .cv {{
    display: inline-block;
    min-width: 58px;
    text-align: right;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 11px;
  }}
  .cv-pos {{ color: #052e16; }}
  .cv-neg {{ color: #450a0a; }}
  .cv-neu {{ color: var(--text); }}

  /* ── Footer ── */
  .foot {{
    margin-top: 8px;
    font-size: 9px;
    color: var(--text);
    letter-spacing: 0.04em;
  }}
</style>
</head>
<body>

<div class="topbar">
  <h1>⚡ Momentum Dashboard</h1>
  <span class="meta">As of {as_of} · generated {generated} · click headers to sort</span>
</div>

{warnings_html}
<div class="tbl-wrap">
  <table id="main">
    <thead>
      <tr>
        <th data-col="ticker">Ticker</th>
        {header_cells}
      </tr>
    </thead>
    <tbody>
      {body_rows}
    </tbody>
  </table>
</div>

<div class="foot">
  Data: Yahoo Finance via yfinance · Momentum = total return · Sharpe annualised, rf = {rf_label} (FRED DGS3MO) · SerCorr = lag-1 autocorrelation 21-day window
</div>

<script>
(function () {{
  const tbl = document.getElementById('main');
  const headers = Array.from(tbl.querySelectorAll('thead th'));
  let sortCol = -1, sortDir = 1;

  headers.forEach(function (th, colIdx) {{
    th.addEventListener('click', function () {{
      if (sortCol === colIdx) {{ sortDir *= -1; }} else {{ sortCol = colIdx; sortDir = 1; }}
      headers.forEach(function (h) {{ h.classList.remove('sorted-asc', 'sorted-desc'); }});
      th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');

      const tbody = tbl.querySelector('tbody');
      // Collect data rows grouped by their preceding cat row
      const children = Array.from(tbody.children);
      const groups = [];
      let current = null;
      children.forEach(function (row) {{
        if (row.classList.contains('cat-row')) {{
          current = {{ header: row, rows: [] }};
          groups.push(current);
        }} else if (current) {{
          current.rows.push(row);
        }}
      }});

      groups.forEach(function (g) {{
        g.rows.sort(function (a, b) {{
          const aVal = a.cells[colIdx] ? a.cells[colIdx].getAttribute('data-val') : '';
          const bVal = b.cells[colIdx] ? b.cells[colIdx].getAttribute('data-val') : '';
          const aN = parseFloat(aVal), bN = parseFloat(bVal);
          if (!isNaN(aN) && !isNaN(bN)) return sortDir * (aN - bN);
          return sortDir * String(aVal).localeCompare(String(bVal));
        }});
        tbody.appendChild(g.header);
        g.rows.forEach(function (r) {{ tbody.appendChild(r); }});
      }});
    }});
  }});
}})();
</script>
</body>
</html>
"""


def render_html(sections: list[dict], metrics: list[dict], as_of: date, path: Path, rf_rate_ann=None, warnings: list[str] | None = None):
    import datetime

    header_cells = "\n        ".join(f'<th>{m["label"]}</th>' for m in metrics)

    body_parts: list[str] = []
    num_cols = 1 + len(metrics)

    for section in sections:
        body_parts.append(
            f'<tr class="cat-row"><td colspan="{num_cols}">{section["icon"]} {section["name"]}</td></tr>'
        )
        for row in section["rows"]:
            ticker = row["Ticker"]
            cells = [f'<td data-val="{ticker}">{ticker}</td>']
            for metric in metrics:
                val = row.get(metric["label"])
                display = _fmt(val, metric["fmt"])
                data_val = f"{val:.6f}" if isinstance(val, float) else ""
                if metric.get("color") and val is not None:
                    bg = _momentum_color(val)
                    css_class = "cv-pos" if val > 0 else "cv-neg"
                    inner = f'<span class="cv {css_class}" style="background:{bg}">{display}</span>'
                else:
                    inner = f'<span class="cv cv-neu">{display}</span>'
                cells.append(f'<td data-val="{data_val}">{inner}</td>')
            body_parts.append(f'<tr class="data-row">{"".join(cells)}</tr>')

    rf_label = f"{rf_rate_ann*100:.2f}%" if rf_rate_ann is not None else "0% (unavailable)"

    # Build warning banners
    warn_parts: list[str] = []
    for w in (warnings or []):
        css = "warn-rf" if w.startswith("RF:") else "warn-data"
        icon = "⚠️" if css == "warn-rf" else "🔴"
        text = w[3:].strip() if w.startswith(("RF:", "DA:")) else w
        warn_parts.append(f'<div class="warn {css}"><span class="warn-icon">{icon}</span>{text}</div>')
    warnings_html = ('<div class="warnings">\n' + "\n".join(warn_parts) + "\n</div>") if warn_parts else ""

    sep = "\n      "
    html = _HTML_TEMPLATE.format(
        as_of=as_of.isoformat(),
        generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        header_cells=header_cells,
        body_rows=sep.join(body_parts),
        rf_label=rf_label,
        warnings_html=warnings_html,
    )
    path.write_text(html, encoding="utf-8")
    log.info("HTML written to %s", path)


# ── PNG renderer ──────────────────────────────────────────────────────────────

def render_png(html_path: Path, png_path: Path):
    """Try playwright → imgkit → matplotlib fallback."""
    if _try_playwright(html_path, png_path):
        return
    if _try_imgkit(html_path, png_path):
        return
    log.warning("Falling back to matplotlib PNG (limited fidelity)")
    _fallback_matplotlib(html_path, png_path)


def _try_playwright(html_path: Path, png_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        log.debug("playwright not installed")
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(html_path.resolve().as_uri())
            page.wait_for_timeout(500)
            # expand to full page height
            height = page.evaluate("document.body.scrollHeight")
            page.set_viewport_size({"width": 1600, "height": height})
            page.screenshot(path=str(png_path), full_page=True)
            browser.close()
        log.info("PNG written via playwright to %s", png_path)
        return True
    except Exception as exc:
        log.warning("playwright failed: %s", exc)
        return False


def _try_imgkit(html_path: Path, png_path: Path) -> bool:
    try:
        import imgkit  # noqa: F401
    except ImportError:
        log.debug("imgkit not installed")
        return False
    try:
        import imgkit
        options = {
            "width": "1600",
            "quiet": "",
            "format": "png",
        }
        imgkit.from_file(str(html_path), str(png_path), options=options)
        log.info("PNG written via imgkit to %s", png_path)
        return True
    except Exception as exc:
        log.warning("imgkit failed: %s", exc)
        return False


def _fallback_matplotlib(html_path: Path, png_path: Path):
    """Very basic matplotlib table screenshot as last resort."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 4), facecolor="#0d0f14")
        ax.set_facecolor("#0d0f14")
        ax.text(
            0.5, 0.5,
            f"Dashboard saved as HTML:\n{html_path}\n\n"
            "Install playwright or imgkit for a proper PNG.\n"
            "Run: pip install playwright && playwright install chromium",
            ha="center", va="center", color="white", fontsize=12,
            transform=ax.transAxes, wrap=True,
        )
        ax.axis("off")
        plt.tight_layout()
        plt.savefig(str(png_path), dpi=150, bbox_inches="tight", facecolor="#0d0f14")
        plt.close()
        log.info("Fallback PNG written to %s", png_path)
    except Exception as exc:
        log.error("All PNG renderers failed: %s", exc)
