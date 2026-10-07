# The retro (end-of-day improvement loop)

When: once a day, after the daily report, as its own session. Builders keep working meanwhile.
Who: the chief of staff using the `retro` skill. Input: primary sources only.

1. **Read** today's daily report, every hand correction with its reason, every stop outcome, every
   review note and REJECT, and the open lessons.
2. **Ask seven questions:** Did a builder hunt for a file? Could a check have caught a mistake? Is
   there a rule to add or to delete? Did the rules file grow? Was there an expensive call? Is there
   an instruction nobody uses? Was information missing?
3. **Strike:** add today's date to the matching lesson's `strikes`, or open a new lesson.
4. **Two strikes in seven days** earns one change; at most two changes a day.
5. **Shape it:** mechanical -> a check (a unit with red tests); judgement -> one replaced rule line.
6. **Ship it through the clock** like any unit. Mark the lesson `applied` with what applied it.
7. **Weekly hill-climb:** one number, one hypothesis, one change, one week, keep or revert.
8. **Report** in the daily report: what changed, why, and what is measured tomorrow.

Week one sets a baseline and has no targets; week two's targets come from week one's numbers.
One target holds from day one: zero escaped defects (a defect found on main after landing).
