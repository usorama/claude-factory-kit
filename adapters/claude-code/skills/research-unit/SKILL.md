---
name: research-unit
description: Research an outside tool or service before any code that evaluates or adopts it. Use whenever a row names an outside tool, library, SaaS or CLI the repo does not use yet.
---

1. Do not cut code units for the row yet. Mark the row building and say so in `state.md`.
2. Start the `researcher` agent (generated from factory.toml; it has its pinned model, do not pass another) on the tool.
   Its output is `docs/research/<date>-<tool>.md` with the sections that `python3 factory/research_check.py <file>` requires.
3. Ask code for the independent review: `python3 factory/crew.py research <file>`. The claim verifier re-measures every
   fact; on MATCH code adds the `Reviewed-by: <model> PASS` line that the red check requires for an outside-tool unit.
4. Fix the research file until the review passes.
5. The reviewed file is the row's work spec. Now cut code units (`cut-a-unit`) with `"outside_tool": true` and
   `"research": "docs/research/<file>.md"`; their briefs cite it.
6. If the research shows the tool cannot do what the row needs, write a `DEC-` card with the facts
   and a recommendation instead of building around it.
