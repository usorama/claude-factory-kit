## 1.2.0 - 2026-10-07
One tool-neutral core with thin adapters; the Claude Code plugin is one of them.
- Adapters: Claude Code plugin (this repo is its marketplace; commands /factory-init, /factory-install-clock,
  /factory-dashboard, /factory-retro, /factory-promote-lesson, /factory-chief; skills; Stop and agent-guard hooks),
  Codex (skills generated from the same commands, AGENTS.md block, per-role profiles), generic (bin/factory, AGENTS.md).
- Roles file factory.toml: every role (chief-of-staff, builder, reviewer, researcher, summarizer) pinned with tool,
  exact model, effort, permissions, a versioned prompt, its output form and the code check. Presets claude-only
  (default, no Codex), codex-only, claude-codex, generic hold requirements, not model names.
- Model probe at init: one tiny call per candidate exact model ID; a fixed rule maps requirements to the models that
  answered. Aliases and tool defaults refused. A pinned model that stops answering stops the unit and asks a person;
  `factory probe` proposes, `factory roles accept` approves. Receipts record role, model, prompt version, settings.
- Reviewer independence: a different model when available, else a fresh session with a different review prompt,
  marked weaker on the dashboard; session reuse is refused.
- The crew (crew.toml + crew.py): Sorter Sam, Sweeper Sid, the plan coverage auditor, Quill, Inspector Grumble
  (the reviewer), Lockjaw, Thomasina, the spec conformance auditor, the claim verifier and the Bookie, each started
  only by code on its trigger, with a JSON form checked by code, project memory and a scorecard on the dashboard.
- Planning: the slice-matrix skill and its checker ship with the kit; a failing plan is a finding.
- Sizing at cut time in code: named seam, estimate at most 120 minutes, time box twice the estimate, split after the
  second refusal or twice the estimate; research first for outside tools; review notes become backlog rows;
  estimate against actual and ready-queue width on the dashboard.
- Chief of Staff role and jobs (tick, cut, verify, stop, review, close, retro, report) and its launcher
  (`factory chief`: the role and its loop with the pinned model).
- Single-unit stop in code: `tick.py hold` (not runnable at once, its process ended, the killed step voided) and
  `release` (back to cut only after the re-cut validates); enqueue, hold and release refuse inside a unit work
  folder; `verify-checkout` for sabotage in a separate checkout; locks stamped with the owner's start time.
- Rows close only through `tick.py close-row` after the row_landed crew passes.

# Changelog

## 1.1.0 - 2026-10-07
Fixes from the independent review (REVIEW-fable.md; item by item in FIXES.md).
- Machinery is never the unit's fault: model errors, non-success subtypes, timeouts, tool denials
  with no change, fetch and gh failures retry without using an attempt; retries are capped.
- Usage limits pause builds and reviews (`paused-until`); `--max-turns`, `--max-budget-usd` and a
  daily budget with one human decision card; lanes default to 2.
- Toolchain pin by major.minor; patch changes warn; auto-update off; `ticks_skipped` finding.
- Landing modes direct, auto, pr_only with a `pr_open` state; merge method; gh errors with reasons.
- Every test run of model-written code is scrubbed: no tokens, temporary HOME, no network where
  bubblewrap or sandbox-exec works. Builder and reviewer sandboxes have no network.
- One fetch per tick; patch id with -U0; `brief_check.py`; equal-model refusal; `clock_host`.
- `lessons.py` (strikes and daily cap by code), escaped defects (`tick.py defect`), unit titles,
  refusals and cycle time on the page and in the daily report, local dashboard after every tick,
  `tick.py prune`, `install-clock.sh`, the token file, a fuller allow list.

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
