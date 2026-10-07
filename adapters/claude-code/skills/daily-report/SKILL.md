---
name: daily-report
description: Write and send the day's factory report from the records - code writes the numbers, you add only the outcome line. Use at the end of each working day, before the retro.
---

1. `python3 factory/daily_report.py --write` writes `var/factory/daily/<date>.md` from the log,
   the ticks, the cards and the lessons. Do not change any number in it.
2. Read it and write one outcome line on top of your message: what moved, what is stuck, what you
   decided. Plain words, under 300 words in total.
3. Name each hand correction and its reason, each idle reason, and each decision waiting.
4. Rebuild and publish the dashboard (`staleness-audit` skill), so the Daily report tab matches.
5. Send the report to the human in the chat. A phone push, if set up, carries only
   `python3 factory/asks.py notify-text` (decisions only, never unit stops).
