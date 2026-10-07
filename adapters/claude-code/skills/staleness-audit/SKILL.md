---
name: staleness-audit
description: Make sure nothing the human sees is stale - records agree, the dashboard data is newer than its sources, static page text matches the scripts it describes. Use before publishing the dashboard and after changing any factory script.
---

1. `python3 factory/consistency.py` - fix every finding at its source (each finding names its fix).
   Close stale cards, update the Position block, mark finished rows done.
2. `python3 factory/metrics.py`, then `python3 factory/staleness_gate.py`.
3. A static section is stale: read the scripts it lists in `data-sources`, rewrite the section text
   in place so it is true today, set `data-asof` to today. Never add a second section to cover an
   old one. Never type a number into static text (write rule constants in words).
4. Run the gate again until it says clean, then publish (see `dashboard/PUBLISH.md`).
5. Commit the page change in the same commit as the script change it describes.
