# Backlog format

`plan/backlog.md` is the work list. One markdown table, one row per outcome:

| ID | Status | Added | Item | Source |
|---|---|---|---|---|
| B12 | building | 2026-10-07 | The export page shows totals per team. | Team lead request |
| B13 | done (PR 41, 43) | 2026-10-06 | Red check tolerates queued units. | Lesson L1 |

- **ID:** letters and digits, never reused. Units of a row are `.ai/units/<ID>/<n>.json`.
- **Status:** `todo`, `building` or `done ...` (the first word counts). `tick.py enqueue` refuses a
  unit whose row is not `building`; `consistency.py` reports a building row whose units all landed.
- **Item:** one outcome in plain words, not a task list. Units are cut when the row is reached.
- **Source:** who asked, or which lesson or review note created it. Review notes that do not block
  become rows here.
- Only the chief of staff and code (review notes, close-row) edit this file.
