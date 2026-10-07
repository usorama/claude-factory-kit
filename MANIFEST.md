# Manifest (1.2.1)

`<project>` paths show where `factory init` puts a file in a work repo.

## Repo root
| File | Purpose |
|---|---|
| README.md | What the kit is, the loop, install per harness, dry run, daily use, self-improvement, stop, troubleshooting |
| PRINCIPLES.md, RULES.md | Why and the exact rules with the program that enforces each (copied to `<project>/.ai/factory-principles.md`, `.ai/factory-rules.md`) |
| SETUP-CHECKLIST.md | Setup steps, each with a check |
| CHANGELOG.md, VERSION | Release notes and version (kept equal to `.claude-plugin/plugin.json` by `core/check_kit.py`) |
| MANIFEST.md, FIXES.md, REVIEW-fable.md | This list; what was done for every review item and every gap found; the independent review of 1.0.0 |
| .claude-plugin/marketplace.json, plugin.json | The repo as a Claude Code marketplace holding the plugin `factory` (components in adapters/claude-code) |
| pytest.ini, .gitignore | Run every test from the root; ignore caches |
| tests/test_real_smoke.py | Real-model smoke test (real claude CLI): crew pass, tiny build and review, direct landing; skips unless FACTORY_REAL_SMOKE=1 |
| tests/test_adapters.py | Kit check, plugin validation, fresh install from the local marketplace for every preset, Codex skills, generic CLI, agent guard, broken-adapter sabotages |

## core/ (tool-neutral)
| File | Purpose |
|---|---|
| cli.py | `factory`: init, agents, chief, tick, clock, dashboard, retro, crew, probe, roles, promote-lesson, check |
| factory_init.py | Plan or apply the project setup; probes models when there is no roles file; never overwrites without consent |
| probe.py, models.toml | The model probe (one tiny call per candidate exact ID) and the fixed requirement-to-model rule |
| agents_gen.py | Agent files from the roles file and the crew file: Claude `.claude/agents`, Codex profiles, tool-neutral `crew/<name>/AGENT.md` |
| build_dashboard.py | Metrics, then the staleness gate; prints the page path to publish |
| promote_lesson.py | A proven local lesson becomes a branch (and with --push a pull request) on the kit repo, with a version bump |
| check_kit.py | The kit's own integrity check (manifests, adapter references, CLI calls, prompts, versions) |
| factory/ | Copied to `<project>/factory/` and run from there by the clock (see below) |
| templates/ | Copied into the project: rules for every agent (factory-agents.md), versioned prompts for roles and crew, dashboard, state, backlog, lessons, settings, pre-commit |
| planning/slice-matrix/ | The planning skill: SKILL.md, schema, checker and renderer, tests, 11 examples, 13 eval cases with a config-driven runner |
| sample/ | The dry run: seed repo, two cut units, solutions, deterministic fake claude, codex and gh (`fakes/agent.py`) |
| docs/ | Lessons format, retro procedure, backlog format, example lessons |
| tests/ | 102 tests of the core, including the fixes from the first real run (test_real_run_fixes.py) (fixtures copied from real runs of claude and codex, including unknown-model answers and the 2.1.290 permission probe) |

## core/factory/ (in every project)
| File | Purpose |
|---|---|
| tick.py, tick.sh, install-clock.sh | The clock and the chief of staff's queue commands (enqueue, set, hold, release, verify-checkout, close-row, defect, prune); cron/launchd wrapper; clock installer |
| drive.py | One step per unit per tick, lanes, landings one at a time, unit faults vs machinery, holds, split at twice the estimate |
| runners.py, modelrun.py | The steps; role commands from the roles file, output parsing, failure classification, receipts, tracked processes |
| common.py | Settings, roles validation and reviewer independence, locks with owner start time, queue, log |
| crew.py, crew.toml | The crew: trigger table, runs, form checks, records, memory, scorecard, before-cut, research review, retro |
| unit_check.py, brief_check.py, cited_sources.py, research_check.py | Sizing at cut time; brief sections; cited sources; research and summary forms |
| red_check.py, build_check.py, guard.py, testrun.py, factory_pytest_plugin.py | Red check, build check, mutation guard, scrubbed test runs |
| review.py, land.py | The review form and notes to backlog; landing modes and gh |
| asks.py, consistency.py, metrics.py, daily_report.py, staleness_gate.py | Cards, findings, dashboard data, daily report, the publish gate |
| lessons.py, fingerprint.py, tomlw.py | Lessons by code; toolchain pin; TOML writer |
| chief.sh, stop_hook.sh | Start the chief of staff role and its loop; Stop hook |
| presets/*.toml | claude-only (default), codex-only, claude-codex, generic: role requirements, not model names |

## adapters/
| File | Purpose |
|---|---|
| claude-code/commands/*.md | /factory-init, /factory-install-clock, /factory-dashboard, /factory-retro, /factory-promote-lesson, /factory-chief |
| claude-code/skills/*/SKILL.md | slice-matrix, cut-a-unit, review-a-unit, research-unit, retro, daily-report, staleness-audit |
| claude-code/hooks/ | hooks.json; stop_hook.sh (records must agree); agent_guard.py (no model override, no code-only role from a session) |
| codex/install.sh, codex/AGENTS.md | Codex skills generated from the Claude commands; how Codex drives the core |
| generic/bin/factory, generic/AGENTS.md | The CLI for any harness or a person; how to fill the generic preset |
