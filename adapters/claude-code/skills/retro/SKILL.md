---
name: retro
description: End-of-day improvement loop. Turn the day's repeated mistakes into at most two changes - a check for a mechanical mistake, one replaced rule line for a judgement mistake. Use once a day after the daily report.
---

1. Read the primary sources, not summaries: today's `var/factory/daily/<date>.md`, the hand
   corrections and stop outcomes in `python3 factory/daily_report.py`, review notes, and
   `.ai/lessons.jsonl`.
2. Look in seven places: files the builder could not find; mistakes a check could catch; rules to
   add or delete; the rules file size; costly calls; instructions nobody uses; missing information.
3. **Two strikes:** for each mistake, `python3 factory/lessons.py strike <id>` (or `lessons.py add`
   first). Code marks a lesson `ready` at two strikes within seven days. Once is noise.
   `python3 factory/lessons.py ready` lists what earned a change.
4. **Shape:** a mechanical mistake becomes a check in a factory script, cut as a unit with red tests
   through the same clock. A judgement mistake becomes one line in `.ai/defect-library.md` or
   `.ai/factory-rules.md`, and one line comes out (the file never grows).
5. **Cap:** at most two changes a day. No new tool, script or agent unless it replaces one.
6. Weekly (pick a day): one hill-climb - the number farthest from its target, one hypothesis, one
   change, measured for a week, kept or reverted.
7. `python3 factory/lessons.py apply <id> --by "<PR or rule line>"` (it refuses a third change a
   day), give each change a `measure` (the number it should move), and report them.
