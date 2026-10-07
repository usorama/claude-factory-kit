---
description: End-of-day retro - daily report, claim check on it, the Bookie's crew scorecard, and lessons that earned a change (two strikes, at most two changes a day).
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" retro *), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" retro), Bash(python3 factory/lessons.py *), Bash(python3 factory/daily_report.py *)
---
1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" retro`. It writes today's report, runs the claim verifier on it and the Bookie's scorecard, and lists
   lessons that are ready.
2. Follow the retro skill: strike lessons with `python3 factory/lessons.py strike <id>`, shape each ready one into a
   check (a unit with red tests) or one replaced rule line, apply at most two with `lessons.py apply`.
   Lessons live in this repo (.ai/lessons.jsonl, .ai/factory-rules.md, .ai/defect-library.md, .ai/prompts/) and work at once.
3. A lesson that is applied and proven (two strikes, its measure moved) can be shared with every user of the kit:
   suggest /factory-promote-lesson <id>.
4. Report the outcome first, then the scorecard's most expensive mistake, then any decision waiting.
