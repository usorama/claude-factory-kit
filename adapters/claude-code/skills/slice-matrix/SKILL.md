---
name: slice-matrix
description: Plan from outcomes - map requirements to outcomes, cut tracer-bullet rows (each at most 8 hours, at least two layers, a yes/no check) with shared-engine columns, and check the plan until the checker exits 0. Use before any build and for every re-plan.
---
Read the full skill first: ${CLAUDE_PLUGIN_ROOT}/core/planning/slice-matrix/SKILL.md, with its schema and examples in
the same folder. Follow its steps A1 to A10 exactly.
- Write the plan to plan/slice-matrix.json in this repo.
- After every change run `python3 factory/planning/validate_matrix.py plan/slice-matrix.json` and keep it at exit 0
  (rules R1-R10; rows over 8 hours, one-layer rows and rows without a yes/no check are refused).
  `python3 factory/consistency.py` reports a failing plan as plan_invalid.
- Render with `python3 factory/planning/render_matrix.py plan/slice-matrix.json > plan/slice-matrix.md`.
- Do not re-cut the whole plan to size work: size each row when it is reached (the cut-a-unit skill).
- Put each row you start into plan/backlog.md as building; the clock takes units only for building rows.
