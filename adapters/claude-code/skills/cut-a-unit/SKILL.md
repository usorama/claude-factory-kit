---
name: cut-a-unit
description: Size and cut the next unit of a building row - one behaviour, 3-5 red tests, at most 3 code files, a seam, an estimate - and queue it after the crew's before-cut checks. Use whenever fewer than two units are queued while a row is building.
---
Size at cut time, never by re-planning the whole matrix. Code refuses anything larger than the rules below.
1. Pick the row (plan/backlog.md, status building). Every file it names must exist; a missing one stops the row as a DEC- card.
   A row about an outside tool starts with a research unit (the research-unit skill); code units follow its reviewed spec.
2. Ask code for the before-cut checks: `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" crew before-cut <row>`. Sweeper Sid checks it is not already done (a done
   verdict closes the row only after code re-runs the evidence); the plan coverage auditor maps every deliverable to a
   unit. A dropped deliverable blocks the cut: fix the plan first. Run it again whenever the plan changed.
3. Size: one observable behaviour, a paragraph under 100 words with one named sabotage, 3 to 5 tests, at most 3 code
   files, a named seam (the public function or command the tests call), one out-of-scope line, an estimate of at most
   120 minutes. A 1-2 file obvious change is one unit directly. Anything bigger: cut two units.
4. `python3 factory/tick.py worktree <row> <n>` (`--from unit/<row>/<n-1>` only when it needs the earlier unit's code).
5. In the work folder write .ai/units/<row>/<n>.json and the failing tests (import the unit's module inside a helper).
   A fake copies a real run's output and names it. The brief .ai/specs/<row>-U<n>.md is optional: when missing,
   Quill writes it on the clock and brief_check judges it.
6. Self-check: `python3 factory/unit_check.py .ai/units/<row>/<n>.json` then commit on the unit branch.
7. From the main checkout: `python3 factory/tick.py enqueue .ai/units/<row>/<n>.json <work folder>`.
8. Note the unit in the state.md Position block. The dashboard shows its estimate against the actual when it lands.
