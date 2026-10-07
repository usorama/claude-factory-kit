# Changelog

Newest first. 1.2.4 fixes the setup path for the clone marker. 1.2.3 makes the kit safe to run on a work repo.
Model-written code runs fenced, and only a person changes the factory's rules. Setup changes no team file, and
commits carry the person's own name. Each item has a test and a
sabotage, listed item by item in `FIXES.md`.

## 1.2.4 - 2026-10-07

- [Quality] A setup that follows the docs never meets the clone-marker refusal. The init command asks whether the
  folder is the factory's own clone, and marks it. Without the mark, init ends with a "next:" line. The
  refusal in the clock, the chief and the clock installer names the same step. 1.2.3 turned the marker on by default
  but left the documented path and the real smoke test without it.
- The dry run and the real smoke test now follow the documented setup: a team repo on its origin, then a separate
  clone that only the factory uses, set up with `factory init --apply --factory-clone`.
- The real smoke test ran on 2026-10-07 and cost $0.60. Builder: claude-haiku-4-5. Reviewer and plan coverage
  auditor: claude-sonnet-5-5. It landed one unit with the fenced builder path and no tool denials.

## 1.2.3 - 2026-10-07

From a second review. On each question the owner chose the safer option.

- [Quality] Every test run of model-written code is fenced. It cannot write outside the work folder (bubblewrap on
  Linux and the Windows Subsystem for Linux), reach the network, see the home folder or get a token. It also has a
  time limit (`test_timeout_minutes`). Builder, reviewer and
  crew run tests only through `factory/run_tests.py`; `sandbox_allow_paths` names extra writable folders.
- [Quality] Roles and crew get an allow-listed environment and may not read secret files.
- [Quality] A model never hands the factory a command. Sweeper Sid names test ids, which code runs fenced in a
  scratch worktree. Crew agents never work in the live checkout.
- [Quality] Only a person changes the factory: a changed script, `factory.toml`, prompt or rule stops the clock until
  `factory approve --yes`. The chief may not edit those files, approve or restart. Crew memory lines are records only.
- [Quality] Setup is personal by default, so nothing the team tracks changes. A team that agreed uses
  `--footprint shared`. `require_clone_marker` is on by default; init writes the marker with `--factory-clone`.
- [Quality] Commits carry the person's own git identity, with hooks and signing on. A refused push says why.
- [Quality] The dashboard stays on the computer. Publishing it needs the dashboard_publish setting.
- [Quality] The Stop hook runs the plugin's own check, never a project script.
- [Quality] Pruning keeps unsaved work. The clock installer quotes paths and writes a small runner script. It never
  replaces a crontab it could not read.
- [Velocity] The guard copies a unit once, not once per mutant. A failed run about "quotas" no longer pauses the
  factory. gh is needed only for pull request landing.
- Promoted lessons leave the project's name out unless `--name-project` is given; review notes go to
  `var/factory/notes` with one backlog row per unit; sabotage copies live under `var/factory/scratch`.

Also new:

- Updates: every tick warns while a project's `factory/` is behind the installed kit; `factory init --apply
  --update` refreshes it.
- The restart switch: `factory restart [--check] [--force] [--no-update]`, a person's command that updates the harness
  and restarts the chief session safely, never touching the clock. The chief's job `handoff` prepares it.
- Licence: Apache License 2.0 (`LICENSE`, `NOTICE`).
- The landing ran for real against a private GitHub repository, in `pr_merge` and `auto` modes
  (`dry_run.py --github OWNER/REPO`).

## 1.2.2 - 2026-10-07

- [Quality] On a GitHub origin the factory lands by pull request. A GitHub origin is github.com, or a GitHub
  Enterprise host that gh is signed in to. Init picks `pr_merge`: one pull request per unit, with the review verdict
  in its body, which the factory merges itself after its checks. When `gh api` shows the base protected by required
  reviews or checks, init picks `auto` instead. `direct` is the default only without a GitHub host, and init prints
  why. No mode pushes to the base of a GitHub origin unless `factory.toml` says `landing = "direct"` explicitly. Init
  writes the GitHub choice into `factory.toml`, and the dashboard shows the mode in use.

From a first adopter's review of 1.2.1:

- [Quality] Enqueue and the runners accept only a git worktree of the repo under `<repo>-worktrees/`, never the repo
  itself. A rebuild and a review reset and clean the work folder, so the repo itself would lose uncommitted work.
- [Quality] `promote-lesson` commits locally and prints the exact text and the remote. Pushing is a separate step a
  person types with `--confirm-remote <URL>`, and the slash command no longer pre-approves it.
- Two optional settings, `require_clone_marker` and `forbidden_paths`, stop everything when the folder is not the
  factory's own.
- [Quality] The Codex skill generator no longer mangles an install path that contains `/factory-` or spaces.

## 1.2.1 - 2026-10-07

Fixes from the first real Claude-only run (Claude Code 2.1.290). Each has a test and a sabotage (`FIXES.md`, 1.2.1).

- Direct landing is plain git: code pushes the exact tested commit with `--force-with-lease`, with no gh, to any
  host. The GitHub modes are `pr_merge`, `auto` and `pr_only`. Init names the origin's host and the modes that work.
- Budget: every model run, crew included, goes to a spend ledger as soon as it ends. Code checks the daily cap before
  and after every run. Reaching it raises one card and nothing more starts. Reports read costs from the ledger, so no
  run is counted twice.
- Crew permissions: every agent writes its answer file through an `Edit(.factory-crew-*)` rule, because a
  `Write(...)` rule never matches; the bare `Edit` deny is gone. Permissions travel on the command line, since new
  work folders are untrusted. Both facts were verified with real runs.
- A crew refusal stops at once with one card and is not retried while the card is open. Crew turns and budget come
  from `factory.toml`. Review-note rows are no longer triaged at model cost.
- The build check ignores Python caches, and code restores tracked caches before a catch-up. Init warns about
  tracked caches.
- Presets ship caps that fit them, and the measured expected cost. Init shows the cost per unit and per row.
- Planning is required before a cut, or skipped explicitly and recorded.
- A real-model smoke test, skipped unless `FACTORY_REAL_SMOKE=1`, ran here for $0.65.

## 1.2.0 - 2026-10-07

One tool-neutral core with thin adapters; the Claude Code plugin is one of them.

- Adapters. The Claude Code plugin: this repo is its marketplace, with six commands (`/factory-init`,
  `/factory-install-clock`, `/factory-dashboard`, `/factory-retro`, `/factory-promote-lesson`, `/factory-chief`), skills,
  and two hooks (Stop and an agent guard). Codex: skills generated from the same commands, a block in `AGENTS.md`, and
  per-role profiles. Generic: `bin/factory` and `AGENTS.md`.
- The roles file `factory.toml` pins every role (chief-of-staff, builder, reviewer, researcher, summarizer). Each role
  has a tool, an exact model, an effort, permissions, a versioned prompt, its output form and the code check. The
  presets claude-only (the default, no Codex), codex-only, claude-codex and generic hold requirements, not model names.
- A model probe at init makes one tiny call per candidate exact model ID. A fixed rule maps the requirements to the
  models that answered, and aliases and tool defaults are refused. A pinned model that stops answering stops the
  unit and asks a person. `factory probe` proposes a new roles file and `factory roles accept` approves it. Receipts
  record role, model, prompt version and settings.
- Reviewer independence: a different model when one is available, else a fresh session with a different review
  prompt, which the dashboard marks weaker. Session reuse is refused.
- The crew (`crew.toml` and `crew.py`) has ten agents: Sorter Sam, Sweeper Sid, the plan coverage auditor, Quill,
  Inspector Grumble (the reviewer), Lockjaw, Thomasina, the spec conformance auditor, the claim verifier and the
  Bookie. Code starts each one only on its trigger. Each answers in a JSON form that code checks, keeps project memory,
  and has a scorecard on the dashboard.
- Planning: the slice-matrix skill and its checker ship with the kit, and a failing plan is a finding.
- Sizing at cut time, in code: a named seam, an estimate of at most 120 minutes, and a time box of twice the estimate.
  A unit is split after the second refusal or at twice its estimate. Outside tools need research first, review notes
  become backlog rows, and the dashboard shows estimate against actual and the ready-queue width.
- The Chief of Staff role, its jobs (tick, cut, verify, stop, review, close, retro, report) and its launcher
  (`factory chief` starts the role and its loop with the pinned model).
- Single-unit stop in code. `tick.py hold` makes a unit not runnable at once, ends its process and voids the killed
  step. `release` returns it to cut only after the re-cut validates. Enqueue, hold and release refuse inside a unit
  work folder. `verify-checkout` gives a separate checkout for sabotage, and locks carry the owner's start time.
- Rows close only through `tick.py close-row`, after the crew checks for a landed row pass.

## 1.1.0 - 2026-10-07

Fixes from the independent review (`REVIEW-fable.md`; item by item in `FIXES.md`).

- Machinery is never the unit's fault. Model errors, non-success subtypes, timeouts, tool denials with no change,
  fetch failures and gh failures retry without using an attempt, and retries are capped.
- Usage limits pause builds and reviews (`paused-until`). There are per-run limits (`--max-turns`,
  `--max-budget-usd`) and a daily budget with one decision card for a person. Lanes default to 2.
- The toolchain is pinned by major.minor; patch changes warn; auto-update is off; skipped ticks are a finding.
- Landing modes direct, auto and pr_only, with a `pr_open` state, a merge method, and gh errors with reasons.
- Every test run of model-written code is scrubbed: no tokens, a temporary `HOME`, and no network where bubblewrap or
  sandbox-exec works. Builder and reviewer sandboxes have no network.
- One fetch per tick, patch ids with `-U0`, `brief_check.py`, the equal-model refusal and `clock_host`.
- `lessons.py` (strikes and the daily cap by code) and escaped defects (`tick.py defect`). Unit titles, refusals and
  cycle time on the page and in the daily report, and a local dashboard after every tick. Also `tick.py prune`,
  `install-clock.sh`, the token file and a fuller allow list.

## 1.0.0 - 2026-10-07
First release. Claude Code only: Sonnet builds, Opus reviews in a fresh session.

- Clock with up to 4 parallel lanes, per-entry saves under a lock, one landing at a time.
- Red check refuses test-file defects; red, build and landing checks tolerate the exact red tests
  of other queued units and of stopped units with an open card.
- Catch-up by replaying a unit's own commits onto the newest main before every check and landing;
  merged-result suite; patch-id match with the reviewed change; merge by exact head commit.
- Mutation guard over the named tests; cited-source and runtime-path check on briefs.
- Review JSON form decided by code; one retry for a review with no form.
- Stop cards for the orchestrator, decision cards for the human; hand corrections with reasons.
- Step log with start and end, idle reasons, cost and tokens from `claude -p --output-format json`.
- Consistency and staleness checks, daily report, dashboard with a staleness gate.
- Toolchain pin and host fingerprint.
