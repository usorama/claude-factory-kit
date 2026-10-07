# Factory rules for every agent session (Claude Code, Codex, any harness)

This repo is built by the factory in `factory/`. Rules: `.ai/factory-rules.md`. Principles:
`.ai/factory-principles.md`. Read both before building anything.
Commands: `factory init|tick|dashboard|retro|promote-lesson` (or your harness's matching commands).

## Who does what
Every role is pinned in `factory.toml` (tool, model, effort, permissions, a versioned prompt in
`.ai/prompts/`, its output form and the code check that accepts it). Agent files are generated from it.
- **Chief of staff:** one continuous session (`factory chief`; role `.ai/prompts/chief-of-staff.v1.md`, jobs `.ai/prompts/chief-of-staff-jobs.v1.md`).
  It cuts units, handles stop cards, runs the retro and keeps `state.md` true. Never two orchestrators.
- **Clock:** `factory/tick.sh` from cron, launchd or Task Scheduler every 5 minutes. No AI inside.
- **Builder:** the `roles.builder` command, a fresh session per build, started by the clock.
- **Reviewer:** the `roles.reviewer` command: a different model when one is available, else a fresh
  session with a different review prompt (the dashboard marks that weaker). Never the builder's
  session or report.
- **Human (<owner>):** only decisions, through `DEC-` cards.

## Always
- Code decides anything computable. A model's answer is evidence that code checks.
- Work in small units with failing tests first (`cut-a-unit` skill). One fix round, then split.
- Every file a brief cites must exist. Never cite a runtime file (`var/...`) by path.
- Write only the checks the tests require. Fakes in tests come from a captured real run, named in the test.
- Work that adopts an outside tool starts with a research unit (`research-unit` skill).
- Change the queue only with `python3 factory/tick.py set ... --reason ... --note ...`. Never edit `var/factory/`.
- After any change: `python3 factory/consistency.py` must report no findings, or say why.
- Close a unit's stop card in the same step you handle it. Unit stops never go to the human.
- Lessons: `python3 factory/lessons.py strike|apply`; never edit `.ai/lessons.jsonl` by hand. A fault
  found on main: `python3 factory/tick.py defect <unit> --note "<what>"`.
- One clock host per repo (`clock_host` in `factory.toml`). Never start a second clock.
- Never put a token in a file the tests can read; the Claude token lives only in `~/.config/factory/claude-token`.
- Update the `## Position` block in `state.md` after every landing, stop, correction or decision.
  Take the time from `date -u`.
- When a factory script changes, update the dashboard section that describes it in the same commit.
  Publish the dashboard only through `factory/staleness_gate.py --publish`.

## A builder or reviewer never
- Edits `state.md`, `CLAUDE.md`, `plan/`, `factory/`, `.claude/` or anything under `var/`.
- Commits, pushes, or works outside its own work folder.
- Guesses a missing input. It stops and reports.

## Ask the human first (decision card, one question, with a recommendation)
Spending money (including raising `daily_budget_usd`), accounts and passwords, production deploys or production data, messages to real
people, store or external submissions, loosening permissions, and real product choices. Decide
everything else, record it in `state.md`, and report it as "for your information".

## Talking to people
Outcome first. Plain words for a reader whose first language is not English. Full file paths. One
question at a time, with a recommendation. Report failures, stalls, hand corrections and your own
mistakes without being asked.
