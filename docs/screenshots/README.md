# Screenshots

- **`dashboard_preview.html`** — rendered 4-page dashboard preview (open in a browser) built from committed results by `python scripts/render_dashboard.py`. This is the immediately viewable, PRD-aligned dashboard state.

Power BI Desktop screenshots (manual, after refresh against a populated DB) belong here as:
- `page1_overview.png`
- `page2_drilldown.png`
- `page3_restatements.png`
- `page4_sensitivity.png`

**Status (2026-11-10, final E9 correction):** PBIP is PostgreSQL-only and corrected for mislabeled visuals, but live Power BI execution/screenshots remain a **manual step** — see `dashboard/PortfolioReport/VALIDATION.md`, `dashboard/PortfolioReport/VISUAL_AUDIT.md`, and `docs/DASHBOARD_AUDIT.md`. No images are fabricated.

**Frozen-PNG status:** the committed Power BI Desktop screenshots (`page*_*.png`) are **frozen evidence** captured before the final E9 verification pass; they reflect the E9 sensitivity state recorded at freeze time (pre-final-correction data). The self-contained HTML previews (`dashboard_preview.html`, `page*_drilldown.html`, `page*_restatements.html`, `page*_sensitivity.html`) are regenerated from the final committed results via `scripts/render_dashboard.py` / `scripts/render_dashboard_previews.py` and reflect the final E9 outcome (1,040 / 1,040 solved, 0 excluded). Treat the PNGs as historical evidence and the HTML previews as the current rendered state.
