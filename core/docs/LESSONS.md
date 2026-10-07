# Lessons ledger

The factory learns from its own mistakes through one file: `.ai/lessons.jsonl` in the work repo,
one JSON object per line. The dashboard's Lessons tab and the daily report read it.

## Format
```json
{"id": "L7", "at": "2026-10-07T09:00:00+00:00", "title": "Parallel units refused each other",
 "what_happened": "Unit 2's red check failed on unit 1's red tests, so only one unit could queue.",
 "lesson": "The red check tolerates the red tests of other units still in the queue.",
 "shape": "check", "strikes": ["2026-10-06", "2026-10-07"], "status": "applied",
 "applied_by": "PR <n>: red_check tolerates queued units", "source": "retro 2026-10-07"}
```
- `shape`: `check` (a program enforces it) or `rule` (one line in the rules or defect library).
- `status`: `open` (one strike), `ready` (two strikes in seven days), `applied`, `retired`.
  `factory/lessons.py` sets it; nobody edits the file by hand.
- `measure`: the dashboard number this lesson should move (for example "Hand corrections").
- A line that cannot be read is skipped by every reader, never fatal.
- Example lines: `lessons.example.jsonl` (generic versions of real lessons).

## From lesson to change
| The mistake | Becomes | Example |
|---|---|---|
| Mechanical: a program could have seen it | A check in a factory script, cut as a unit with red tests, landed through the clock | "the red check refuses a test broken by its own file" |
| Judgement: needs a person or model to see it | One line in `.ai/defect-library.md` or `.ai/factory-rules.md`, replacing one line | "write only the checks the tests require" |
| Seen once | Nothing yet; one strike recorded | |

Prefer the check: a check runs every time, a rule line is read sometimes.

## Limits
- Two strikes in seven days before any change. At most two changes a day.
- Rules grow only by replacing: the rules file and the defect library keep their size.
- No new tool, script or agent unless it replaces one.
- Each change is itself a unit: failing test first, other-model review, landed by the clock. The
  retro writes the unit; it never edits the factory directly.
