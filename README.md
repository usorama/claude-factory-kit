# Factory kit

A small, working software factory for a team that builds internal tools with AI coding agents. You plan work in
thin rows, cut each row into small units with failing tests, and a clock moves every unit through fixed steps. Programs
check every step. A builder model writes the code; a different model (or a fresh session) reviews it. A crew of
narrow agents starts on fixed triggers. Every step is logged, and a dashboard on your own computer shows it all. On the
normal path it asks you two kinds of thing: decisions (cards), and your approval when its own rules, prompts, scripts
or budget changed.

It is careful with a work repo. Code a model wrote runs its tests fenced: it cannot write outside its work folder,
reach the network or see your home folder, and it gets no tokens. Setup is personal by default: no file your team
tracks changes. Commits carry your own name and pass your team's hooks.

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
 YOU: only money, accounts, production, real people, a model change, product choices  (decision cards, `DEC-<id>`)
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
Python 3.12, git, pytest, and at least one agent tool: Claude Code (2.1 or newer) or Codex CLI. The GitHub CLI
(`gh`, signed in) is needed when units land through pull requests, which is the default on GitHub. On Linux and on the
Windows Subsystem for Linux (WSL), install `bubblewrap` and `socat`: they fence every test run
(`sudo apt install bubblewrap socat`). Without them tests still run, unfenced, and the checks report that. Windows: use Ubuntu under WSL version 2 (WSL2) and
keep repos under `~/`, not `/mnt/c`.

## Install

**Claude Code (default):**
```
claude plugin marketplace add usorama/claude-factory-kit      # or a local clone: claude plugin marketplace add ~/claude-factory-kit
claude plugin install factory@factory-kit
```
Then make a clone of your repo that only the factory uses (`git clone <your origin> ~/factory-<repo>`), open Claude
Code in it, and run `/factory-init`. It asks whether this folder is the factory's own clone and marks it
(`.factory-clone`); the clock never runs anywhere else. It probes which models this machine can use (one tiny call per
candidate model), shows the roles it chose and why, and asks before overwriting anything. Then `/factory-install-clock`.

Setup is personal unless you ask otherwise. Init hides every factory file through `.git/info/exclude`, a file that
never leaves your machine. It writes `.claude/settings.local.json` and `CLAUDE.local.md`, never the team's
`.claude/settings.json` or `CLAUDE.md`, and refuses to change a file the team tracks. `--footprint shared` writes the
team files, for a team that agreed to it. Without `--factory-clone`, init ends with a line starting "next:" that says how to mark
the folder, and the clock installer refuses with the same words.

**Codex:** `git clone <kit>`, `bash adapters/codex/install.sh`, then in a clone of your repo used only by the factory
`python3 <kit>/core/cli.py init --apply --factory-clone --preset codex-only --adapter codex` (or `claude-codex`), then
`factory clock`.

**Any harness or by hand:** put `<kit>/adapters/generic/bin` on your `PATH`, then, in the factory's own clone,
`factory init --apply --factory-clone --preset generic --adapter generic`, fill the commands and models in `factory.toml`, then `factory clock`.

Updating: `/plugin update` (or `git pull` in the kit) does not reach a project's `factory/` copy. Every tick and the
consistency check warn while the project is behind. `factory init --apply --update` refreshes it in one command and
keeps your own files (backlog, state, lessons, roles file).

Landing: on a GitHub origin the factory opens a pull request per unit (review verdict in the body) and merges
it itself (`pr_merge`), or lets GitHub merge it when main is protected (`auto`). It never pushes to main on GitHub
unless `landing = "direct"` is written explicitly. Without a GitHub host it pushes the tested commit (`direct`).
Init prints which mode it chose and why; the dashboard shows the mode in use.

Presets (`core/factory/presets/`) hold role requirements, not model names. Example: on a machine with only Sonnet 5.5,
Sonnet 5, Sonnet 4.6 and Haiku 5, claude-only maps the chief of staff and builder to `claude-sonnet-5-5`, the reviewer
to `claude-sonnet-5` ("same maker, different version") and the summarizer to `claude-haiku-5`.

## Real smoke test (about $0.65, three minutes)
`FACTORY_REAL_SMOKE=1 python3 -m pytest -q tests/test_real_smoke.py -s` runs the real `claude` CLI: one crew pass
before the cut, one tiny unit built (Haiku 4.5) and reviewed (Sonnet 5.5), landed with plain git onto a local origin.
It skips unless the variable is set and both models answer.

## First run: the dry run (no model calls)
```
python3 core/sample/dry_run.py /tmp/factory-dry-run --preset claude-only     # also codex-only, claude-codex, generic
python3 -m pytest -q                                                          # the kit's own tests
```
The dry run installs with `factory init`, and the model probe runs against fake tools. It runs the before-cut crew
and cuts two units; the second has no brief, so Quill writes it. It ticks until both land, closes the row through
code, runs the retro and builds the dashboard. It ends with `DRY RUN PASSED`.

## Daily use

- **Always: the clock runs by itself.** `factory clock` installed it (cron, launchd or Task Scheduler).
- **Always: the chief of staff runs its loop.** `factory chief` in tmux (Claude Code: role + `/loop`; Codex: role + first instruction).
  Its session asks before each file edit unless you start it with `factory chief --permission-mode acceptEdits`; that
  choice is yours. Either way it cannot edit the factory's rules, prompts, scripts or `factory.toml`.
- **Before planning or re-planning: plan from outcomes.** Skill `slice-matrix`, then `python3 factory/planning/validate_matrix.py plan/slice-matrix.json`.
- **Before cutting a row: crew checks.** `factory crew before-cut <row>`.
- **Cutting: size and queue a unit.** Skill `cut-a-unit`; `python3 factory/tick.py enqueue ...` from the live checkout.
- **Stop one unit: hold, re-cut, release.** `python3 factory/tick.py hold <unit> --reason ...`, then `release <unit> --note ...`.
- **A row's units all landed: close it by code.** `python3 factory/tick.py close-row <row>`.
- **Any time: dashboard.** `factory dashboard` builds a page that stays on your computer. Publishing it as a
  claude.ai artifact (`/factory-dashboard`) happens only after you set `dashboard_publish = "artifact"` in factory.toml.
- **After a rule, prompt, script or budget change: approve it.** The clock stops and says which files changed.
  `factory approve` shows the change; `factory approve --yes` records it. Only you run it.
- **Updating Claude Code: restart the chief safely.** Ask the chief to run job `handoff`, then type
  `factory restart` yourself (`--check` first, if you like). It updates the harness, restarts the chief's tmux session
  with its loop, checks it came back, and never touches the clock. On Windows, run it inside WSL:
  `wsl.exe -d Ubuntu -- python3 ~/<repo>/factory/restart.py`.
- **End of day: retro.** `factory retro` (`/factory-retro`); share a proven lesson with `factory promote-lesson`.

## Self-improvement, two levels
1. **Local:** lessons (`.ai/lessons.jsonl`), rules (`.ai/factory-rules.md`), the defect library and every prompt
   (`.ai/prompts/`) live in your repo. A changed rule or prompt takes effect after you approve it
   (`factory approve --yes`); until then the clock waits. Plugin updates never overwrite them.
2. **Shared:** `factory promote-lesson <id> --plugin-repo <checkout> [--files factory/x.py]` turns a proven lesson
   into a local branch on a kit checkout (shared lessons file, rule line or script change, version bump, CHANGELOG
   entry) and prints the exact text and the remote it would go to. Your project's name stays out of the branch, the
   record and the CHANGELOG unless you add `--name-project`. Lesson text itself can still name your project, so
   pushing is a separate step a person types: `--push --confirm-remote <that exact URL>`; it opens a pull request.
   After it merges, users run `/plugin update` (or `git pull`) and `factory init --apply --update` to take it.

## How to stop it
Pause the clock (`crontab -e` and delete the line naming `factory/clock-run.sh`, or unload the launchd job). Stop one unit: `tick.py hold`. Emergency: the `stop` job in
`.ai/prompts/chief-of-staff-jobs.v1.md`.

## Troubleshooting

Each item is a symptom, then its cause and fix.

- **`factory init` refuses: "role X needs codex ...".** That tool is missing or no wanted model answered. Choose another preset.
- **Ticks skipped: "must be an exact model ID".** The roles file has an alias or a placeholder. `factory probe`, then `factory roles accept`.
- **Unit errored, `DEC-roles` card.** A pinned model stopped answering. Approve a re-probe; nothing switches by itself.
- **Ticks skipped: "builder and reviewer are the same model".** Set a different reviewer model, or with one model `same_tool_review = "fresh-session"`.
- **enqueue refused: "run before-cut first" / "plan changed".** `factory crew before-cut <row>` again.
- **`unit refused: ... too big for one session`.** Cut it smaller (at most 3 code files, 5 tests, 120 minutes).
- **Unit `needs_split`: "over twice its estimate".** The unit was too big. Split it; the dashboard shows estimate against actual.
- **Red check `network_isolation: none`.** Bubblewrap cannot start here; tests can reach the network (`RULES.md` section 15).
- **`retry once: gh pr merge failed: ... policy`.** Main is protected: set `landing = "auto"` or `"pr_only"` in factory.toml.
- **`gh pr create failed: none of the git remotes ... known GitHub host`.** The origin is not a GitHub host gh can reach. Leave `landing` unset (direct follows the origin) or sign gh in to your GitHub Enterprise host.
- **`the origin is GitHub: the factory never pushes to main unless factory.toml says landing = "direct"`.** On GitHub the factory lands through pull requests (`pr_merge` or `auto`). Write `landing = "direct"` only if your team really wants direct pushes.
- **`claude -p` warns "Ignoring ... permissions.allow entries ... not trusted".** Expected in a new work folder: the factory passes every permission on the command line, so the warning changes nothing.
- **`DEC-budget` card.** The daily budget is spent (builds, reviews and crew all count). Raise `daily_budget_usd` or wait for tomorrow.
- **`crew-<agent>-<row>` card.** A crew agent was refused once (for example it could not write its answer file). Fix the cause, close the card, run the command again.
- **Ticks skipped: "protected files changed without a person's approval".** A rule, prompt, script or `factory.toml` changed. Read it with `factory approve`; record it with `factory approve --yes`.
- **Ticks skipped: "git has no identity".** The factory commits as you: set `git config user.name` and `user.email`.
- **Ticks skipped: "this is not the factory's clone".** Run the clock in a separate clone set up with `factory init --apply --factory-clone`, or set `require_clone_marker = false`.
- **`WARNING: factory 1.2.2 is behind the installed kit 1.2.3`.** Run `factory init --apply --update`.
- **`unit refused: git refused the commit (a hook, or signing)`.** Your team's pre-commit hook refused the builder's work; its message follows. Fix the cause in the unit.
- **`the test run passed its limit`.** A test hung. The run was stopped and counts as a refusal; raise `test_timeout_minutes` only if the suite really needs longer.
- **A test needs to write outside its folder (a cache, a fixture folder).** Add the path to `sandbox_allow_paths` in factory.toml.
- **`restart refused, nothing changed`.** The reason follows: write a fresh handoff note (job `handoff`), commit, or push; or use `--force`.
- **`before-cut` refused: "no planning matrix".** Plan the row with the slice-matrix skill, or set `planning = "skip"` in factory.toml (recorded in the daily report).

## Licence
Apache License 2.0: the full text is in the file `LICENSE`. Credits for the ideas the kit builds on are in the file `NOTICE`.
