# Factory kit

A small, working software factory for a team that builds internal tools with AI coding agents. You plan work in
thin rows, cut each row into small units with failing tests, and a clock moves every unit through fixed steps. Programs
check every step. A builder model writes the code; a different model (or a fresh session) reviews it. A crew of
narrow agents starts on fixed triggers. Every step is logged, and a dashboard shows it all. Nothing asks you on the
normal path.

It fits every setup: **Claude Code only** (the default; no Codex needed), **Codex only**, **both** (Codex builds,
Claude reviews), or **any other harness**. One tool-neutral core, thin adapters:

```
core/                     the factory (Python 3.12 standard library), formats, prompts, presets, dashboard, planning skill
adapters/claude-code/     Claude Code plugin: commands, skills, hooks (the repo root is its marketplace)
adapters/codex/           Codex skills generated from the same commands, AGENTS.md rules
adapters/generic/         bin/factory: a plain CLI for any harness or a person
```

Version: `VERSION`. Every file: `MANIFEST.md`. Rules: `RULES.md`. Why: `PRINCIPLES.md`.

## The loop

```
 YOU: only money, accounts, production, real people, a model change, product choices  (DEC- cards)
  ^                                                              dashboard (artifact or local page)
 CHIEF OF STAFF (one continuous session: `factory chief`)              ^ metrics + staleness gate
  | plan (slice-matrix) -> before-cut (Sweeper Sid, plan coverage) -> cut a sized unit -> enqueue
  v
 CLOCK every 5 minutes, no AI inside, up to N lanes at once, landings one at a time
  red check -> build (builder role) -> build check (+ mutation guard) -> review (Grumble; Lockjaw on risk,
  Thomasina on a surface) -> landing (catch up, merged suite, PR, merge or wait for GitHub) -> close-row by code
  refused once: rebuild with the finding | twice or over twice the estimate: split | machinery: retry, never the unit's fault
  every step: a start and end line in log.jsonl, a receipt (role, model, prompt version, cost)
```

## What you need
Python 3.12, git, the GitHub CLI (`gh`, signed in), pytest, and at least one agent tool: Claude Code (2.1 or newer) or
Codex CLI. Linux and WSL2: `sudo apt install bubblewrap socat` for no-network test runs. Windows: use WSL2 Ubuntu and
keep repos under `~/`, not `/mnt/c`.

## Install

**Claude Code (default):**
```
claude plugin marketplace add <owner>/claude-factory-kit      # or a local clone: claude plugin marketplace add ~/claude-factory-kit
claude plugin install factory@factory-kit
```
Then, inside your repo, run `/factory-init`. It probes which models this machine can use (one tiny call per
candidate model), shows the roles it chose and why, and asks before overwriting anything. Then `/factory-install-clock`.

**Codex:** `git clone <kit>`, `bash adapters/codex/install.sh`, then in your repo
`python3 <kit>/core/cli.py init --apply --preset codex-only --adapter codex` (or `claude-codex`), then `factory clock`.

**Any harness or by hand:** put `<kit>/adapters/generic/bin` on PATH, then `factory init --apply --preset generic
--adapter generic`, fill the commands and models in `factory.toml`, then `factory clock`.

Presets (`core/factory/presets/`) hold role requirements, not model names. Example: on a machine with only Sonnet 5.5,
Sonnet 5, Sonnet 4.6 and Haiku 5, claude-only maps the chief of staff and builder to `claude-sonnet-5-5`, the reviewer
to `claude-sonnet-5` ("same maker, different version") and the summarizer to `claude-haiku-5`.

## First run: the dry run (no model calls)
```
python3 core/sample/dry_run.py /tmp/factory-dry-run --preset claude-only     # also codex-only, claude-codex, generic
python3 -m pytest -q                                                          # the kit's own tests
```
The dry run installs with `factory init` (the probe runs against fake tools), runs the before-cut crew, cuts two
units (the second without a brief, so Quill writes it), ticks until both land, closes the row through code, runs the
retro and builds the dashboard. It ends with `DRY RUN PASSED`.

## Daily use
| When | What | Command |
|---|---|---|
| Always | The clock runs by itself | `factory clock` installed it (cron, launchd or Task Scheduler) |
| Always | The chief of staff loop | `factory chief` in tmux (Claude Code: role + `/loop`; Codex: role + first instruction) |
| Before planning or re-planning | Plan from outcomes | skill `slice-matrix`, then `python3 factory/planning/validate_matrix.py plan/slice-matrix.json` |
| Before cutting a row | Crew checks | `factory crew before-cut <row>` |
| Cutting | Size and queue a unit | skill `cut-a-unit`; `python3 factory/tick.py enqueue ...` from the live checkout |
| Stop one unit | Hold, re-cut, release | `python3 factory/tick.py hold <unit> --reason ...`, then `release <unit> --note ...` |
| A row's units all landed | Close it by code | `python3 factory/tick.py close-row <row>` |
| Any time | Dashboard | `factory dashboard` (Claude Code: `/factory-dashboard` publishes it as an artifact) |
| End of day | Retro | `factory retro` (`/factory-retro`); share a proven lesson with `factory promote-lesson` |

## Self-improvement, two levels
1. **Local:** lessons (`.ai/lessons.jsonl`), rules (`.ai/factory-rules.md`), the defect library and every prompt
   (`.ai/prompts/`) live in your repo and work at once. Plugin updates never overwrite them.
2. **Shared:** `factory promote-lesson <id> --plugin-repo <checkout> [--files factory/x.py] [--push]` turns a proven lesson
   into a branch on the kit repo (shared lessons file, rule line or script change, version bump, CHANGELOG entry) and a
   pull request. After it merges, users run `/plugin update` (or `git pull`) and `factory init --plan` to take it.

## How to stop it
Pause the clock (`crontab -e`, or unload the launchd job). Stop one unit: `tick.py hold`. Emergency: the `stop` job in
`.ai/prompts/chief-of-staff-jobs.v1.md`.

## Troubleshooting
| Symptom | Cause and fix |
|---|---|
| `factory init` refuses: "role X needs codex ..." | That tool is missing or no wanted model answered. Choose another preset. |
| Ticks skipped: "must be an exact model ID" | The roles file has an alias or a placeholder. `factory probe`, then `factory roles accept`. |
| Unit errored, DEC-roles card | A pinned model stopped answering. Approve a re-probe; nothing switches by itself. |
| Ticks skipped: "builder and reviewer are the same model" | Set a different reviewer model, or with one model `same_tool_review = "fresh-session"`. |
| enqueue refused: "run before-cut first" / "plan changed" | `factory crew before-cut <row>` again. |
| `unit refused: ... too big for one session` | Cut it smaller (at most 3 code files, 5 tests, 120 minutes). |
| Unit `needs_split`: "over twice its estimate" | The unit was too big. Split it; the dashboard shows estimate against actual. |
| Red check `network_isolation: none` | bubblewrap cannot start here; tests can reach the network (RULES 14). |
| `retry once: gh pr merge failed: ... policy` | main is protected: set `landing = "auto"` or `"pr_only"` in factory.toml. |
