# Fixes and gaps

Every review item and every gap found so far is fixed and tested, except the items listed under "Still open" below.
Each fixed item names its test and the sabotage: a deliberate break of the check, run on a copy, that turned the
test red. The sections run newest first. Items are tagged [Quality] (a wrong or unsafe result) or [Velocity] (lost
time or money).

## Still open

- **Codex and the daily budget (R16).** Codex reports tokens, not dollars, so the daily dollar budget cannot hold
  Codex runs. The codex presets and init say so.
- **Not run against a real system.** The pull request landing against a real GitHub repo (P1): the gh token here
  lacks the scope to delete a test repo afterwards, so the tests use a fake gh in the shape of a real answer. Also
  never run for real: Codex's usage-limit answer (G6), the builder's no-network sandbox (G8), launchd and Windows
  Task Scheduler (G17), a long Codex chief loop (G25), and pushing a promoted lesson to a real remote (G16, P3).
- **Not built.** A standard way for Thomasina to start the app (G10), richer scorecard rules (G11), running Lockjaw
  and Thomasina side by side (G12), and code that keeps plan rows and backlog rows in step (G19).
- **From the 1.1.0 review, not done.** Full model IDs for Bedrock or Vertex, killing an orphaned `claude -p` before a
  rerun, and checking `.sh` and `.html` citations.

## 1.2.2: landing by pull request on GitHub, and a first adopter's review

**P2 [Quality]: From a first adopter's review: enqueue never checked the work folder; passing the repo itself let a rebuild (`git reset --hard`, `git clean -fdq`) or a review (`git checkout -- .`) wipe uncommitted work.** What was done: Enqueue and the runners accept only a git worktree of this repo under `<repo>-worktrees/`, never the repo itself. Test: `test_the_clock_only_touches_a_worktree_of_this_repo_under_repo_worktrees`. Sabotage that turned it red: repo-itself check removed; runner check removed.

**P3 [Quality]: From a first adopter's review: `promote-lesson --push` could send lesson text, which may name a project, to any remote, and the slash command pre-approved it.** What was done: promote-lesson commits locally and prints the exact text and the remote; pushing needs `--push --confirm-remote <URL>` typed by a person; the command no longer pre-approves promote-lesson (kit check). Test: `test_promote_lesson_shows_the_exact_text_and_pushes_only_with_the_typed_remote_url`, kit check. Sabotage that turned it red: URL check removed; pre-approval added back.

**P4 [Quality]: From a first adopter's review: the factory could run in the folder a person works in, next to real data.** What was done: Optional `require_clone_marker` (a `.factory-clone` file must exist) and `forbidden_paths` (files that must not exist); either stops the clock, runners, crew and chief launcher. Off by default. Test: `test_optional_folder_guards_stop_everything`. Sabotage that turned it red: each guard removed.

**P5 [Quality]: From a first adopter's review (macOS): Codex skills had a mangled path ("code-projectsthe skill factory-kit") because "/factory-" was replaced after the kit path was inserted.** What was done: Only slash commands at a word start are rewritten, and the kit path is inserted last. Test: `test_the_codex_skills_keep_any_install_path_intact` (a path with spaces and "/factory-"). Sabotage that turned it red: old replace order.

**P1 [Quality]: A team on GitHub wanted the factory to merge its own pull requests, never push to main; 1.2.1 defaulted to a direct push everywhere.** What was done: on a GitHub origin init picks pr_merge, or auto when the base is protected. It picks direct only without a GitHub host, and prints why. A direct push to a GitHub base is refused unless factory.toml says landing = "direct". The pull request body carries the review verdict, and the dashboard shows the mode. The real check against a throwaway GitHub repo was not run: the gh token here lacks the delete_repo scope, so the repo could not be removed afterwards. The tests use a fake gh in the shape of a real gh answer (an unprotected branch, captured from a public repo). The protected-branch shape follows the GitHub docs. Test: core/tests/test_github_landing.py. Sabotages that each turned it red: the push guard removed, a protected base not picking auto, and direct as the GitHub default. Also: init not writing pr_merge, the verdict dropped from the body, GitHub Enterprise not detected, and the mode missing on the dashboard.

## 1.2.1: defects from the first real Claude-only run

Each row names its test and its sabotage (the change that made the test fail, run on a copy). All 13 code sabotages
and the 4 kit-check sabotages turned the suite red.

**R1 [Velocity]: Direct landing needed gh, so a local, GitLab or GitHub Enterprise origin could not land.** What was done: `direct` pushes the exact tested commit with `--force-with-lease=refs/heads/<base>:<fetched>`, no gh; GitHub modes are `pr_merge`, `auto`, `pr_only`; init names the host and the modes that work. Test: `test_direct_landing_*`, `test_init_says_which_landing_modes_work_for_the_origin`. Sabotage that turned it red: lease replaced by `--force`; direct branch removed; local origin offered pr modes.

**R2 [Quality]: The daily budget stopped nothing: crew runs were not counted ($3.39 spent against $3).** What was done: A spend ledger written the moment each run ends (crew included); the cap is checked before and after every run; one card; nothing starts. Reports read the ledger, so a review is never counted twice. Test: `test_crew_runs_count_toward_the_daily_budget...`, `test_a_build_does_not_start_when_the_budget_is_spent`, `test_reported_cost_comes_from_the_spend_ledger...`. Sabotage that turned it red: crew spend removed; gate before build removed; metrics back to the log.

**R3 [Velocity]: The crew command denied `Edit`, blocking every answer file.** What was done: Removed; the kit check refuses a bare Edit or Write deny. Proof: kit check sabotage: `"Edit"` added back.

**R4 [Quality]: `Write(...)` rules never match in 2.1.290.** What was done: All path write rules are `Edit(...)`, verified for real (fixtures/claude-permissions-2.1.290.json); the kit check refuses `Write(`. Proof: kit check sabotage: `Write(.ai/specs/*)`.

**R5 [Quality]: sorter-sam, sweeper-sid and the plan coverage auditor could not write their answer file.** What was done: `Edit(.factory-crew-*)` for every crew agent and a writable Codex sandbox; the kit check requires both. Proof: kit check sabotage: sorter-sam's Edit rule removed.

**R6 [Quality]: A new work folder is untrusted, so the project allow list was ignored.** What was done: Verified for real: command-line permissions apply there. Every claude command must carry `--permission-mode` and `--allowedTools` (kit check); the warning is documented as harmless. Proof: kit check sabotage: `--allowedTools` removed from the preset.

**R7 [Quality]: A tracked `.pyc` cost a build round.** What was done: The build check ignores `__pycache__/` and `*.pyc`; tracked caches are restored after a build and before a catch-up; init warns and ignores `*.pyc`. Test: `test_python_caches_never_count...`. Sabotage that turned it red: filter removed; restore made a no-op.

**R8 [Velocity]: Opus high review costs about 2.4 times a build and no default cap fitted.** What was done: Presets ship caps (claude-only: build $1.0, review $1.5, crew $0.75, daily $15) and the measured cost; init prints the cost per unit and per row and what the budget covers. Test: `test_init_shows_the_expected_cost_and_the_preset_caps`. Sabotage that turned it red: preset settings not copied.

**R9 [Quality]: Crew runs had no stop within one before-cut; turns and budget were hardcoded.** What was done: The first refusal (machinery or a broken form) writes one `crew-<agent>-<subject>` card and the agent does not run again on that subject while it is open; `crew_max_turns` and `max_budget_crew_usd` come from factory.toml. Test: `test_a_crew_refusal_stops_at_once...`. Sabotage that turned it red: open-card check removed; turns hardcoded to 40.

**R10 [Velocity]: The dry run's fakes could not catch permission defects.** What was done: `tests/test_real_smoke.py`: the real claude command-line tool, one crew pass, one tiny build and review, direct landing; skips unless `FACTORY_REAL_SMOKE`=1. Run here: passed, $0.65. Proof: the real run itself.

**R11 [Quality]: before-cut accepted a row with no plan.** What was done: Planning is required (a valid plan/slice-matrix.json naming the row) unless `planning = "skip"`, which is logged and named in the daily report. Test: `test_before_cut_requires_a_plan...`. Sabotage that turned it red: the missing-plan refusal removed.

**R12 [Velocity]: Found in the real run: Sorter Sam triaged every review-note row at about $0.14 each.** What was done: Review notes (`N-...`) are not triaged at model cost. Test: `test_review_notes_are_not_triaged_at_model_cost`. Sabotage that turned it red: skip removed.

**R13 [Quality]: Found by the smoke test: a review's cost appeared twice in the step log (crew record and review step).** What was done: Costs are reported only from the spend ledger. Proof: `test_reported_cost_comes_from_the_spend_ledger...`.

**R14 [Quality]: Found in the real run: the model probe's calls were not recorded as spend.** What was done: The probe keeps each call's cost; init writes them to the spend ledger and prints the total. Proof: probe test asserts the cost per model.

**R15 [Quality]: Init said "local" for a repo with no origin yet.** What was done: It says "none (no origin yet)". Proof: `test_init_says_which_landing_modes_work_for_the_origin`.

**R16 [Quality]: Still open: Codex reports tokens, not dollars, so the daily dollar budget cannot hold Codex runs.** What was done: Said in the codex presets and by init; not fixed.

## 1.2.0: gaps found while building the plugin and its adapters

**G1 [Quality]: Plugin commands are namespaced (`/factory:factory-init`); the bare `/factory-init` works only while no other plugin has the same name.** What was done: Documented in `README.md`; names chosen to be unique.

**G2 [Quality]: A plugin cannot ship agent files with the right model: the models differ per machine.** What was done: The plugin ships no role agents; `factory init` generates them per project from the probed roles file.

**G3 [Quality]: A sub-agent call can override an agent file's model, and a session could start a code-only role.** What was done: PreToolUse hook `agent_guard.py` refuses a `model` and any code-only role; tested. Not verified inside a live Claude Code session.

**G4 [Velocity]: `/plugin update` does not update the scripts copied into a project.** What was done: `/factory-init` again shows "differs" and asks; `factory/VERSION` records the copied version. Not automatic.

**G5 [Quality]: Codex has no agent files.** What was done: Per-role profiles in `.codex/profiles/`; the clock passes model and effort on the command line anyway. Linking profiles into `$CODEX_HOME` is left to the person.

**G6 [Quality]: Codex's usage-limit answer was not captured from a real run; the limit words are a pattern.** What was done: The unknown-model answers of both tools and a normal answer of each were captured and are fixtures. Limit handling for Codex is unverified.

**G7 [Quality]: No real build or review ran through the 1.2.0 clock.** What was done: Every preset passes the dry run with fakes shaped from real runs; four tiny real calls were made (normal and unknown model, each tool). A real unit is checklist item 17.

**G8 [Quality]: The builder's and crew's no-network sandbox (`--settings`) is not verified in a real run.** What was done: Flags confirmed with the command-line tool parser only. The test runs that execute model-written code are network-isolated and tested.

**G9 [Velocity]: The model probe costs about thirteen tiny calls per init (ten Claude, three Codex).** What was done: Shown and asked first by `/factory-init`; `--probe-file` for offline or repeated setups.

**G10 [Quality]: Thomasina must drive the running system, but the kit has no standard "start the app" contract.** What was done: Her prompt says the brief names how; a missing way to start is a `REJECT`. A contract field is not built.

**G11 [Quality]: The reference scorecard definitions (cookies and slaps per event kind) were not available on this machine.** What was done: The Bookie gets a code-computed scorecard: accepted answers, refused forms, refuted done claims, `PASS` on a unit with an escaped defect. Richer rules are future work.

**G12 [Velocity]: Lockjaw and Thomasina run one after the other inside the review step.** What was done: Accepted for now; they run only on their triggers.

**G13 [Quality]: `hold` ends tracked model processes; a long test run in a check step finishes before the hold takes effect.** What was done: Its result is voided by the hold; the step is not a model process.

**G14 [Quality]: For the generic tool, a fresh reviewer session can only be declared (`fresh_session = true`), not checked.** What was done: Refused unless declared; the dashboard shows the independence used.

**G15 [Quality]: The 1.1.0 kit folder is not updated with the roles file, the crew, sizing and hold/release.** What was done: The 1.2.0 repo is the kit (core plus adapters); the fallback zip contains it. The 1.1.0 folder stays as shipped.

**G16 [Quality]: `promote-lesson --push` (a pull request on the kit repo) was not exercised: nothing may be pushed until checked.** What was done: Tested up to the local branch, version bump and `CHANGELOG.md` entry.

**G17 [Quality]: launchd and Windows Task Scheduler paths were not run (this host is Linux).** What was done: `install-clock.sh --print` writes them; cron path run.

**G18 [Quality]: Two slice-matrix eval cases carried another company's private records and Mac paths.** What was done: Dropped; 13 cases remain. The eval runner now reads slicer and judge commands from a config with exact model IDs.

**G19 [Velocity]: Plan rows in `plan/slice-matrix.json` and backlog rows are kept by hand in step.** What was done: The slice-matrix skill says to add a started row to the backlog as building; no sync code.

**G20 [Quality]: install-clock still wrote `clock_host` into the old `factory.json` and required `claude` on Codex-only machines.** What was done: Fixed: it edits `factory.toml` and checks only the tools the roles use.

**G21 [Quality]: Prompts contain JSON examples, so `str.format` on them crashed the first crew run.** What was done: `fill()` replaces only known placeholders; covered by every dry run.

**G22 [Quality]: A hold set between the tick's read and a step's first save was erased by that save.** What was done: `save_entry` keeps a stored hold and the step does not start; test and sabotage.

**G23 [Quality]: The vendored plan checker looked for its schema in the wrong folder.** What was done: Schema copied to `factory/schema/`; the plan_invalid test covers it.

**G24 [Quality]: A crew prompt could be deleted without any check noticing (init copies whatever exists).** What was done: `check_kit` verifies every prompt a role or crew agent names; sabotage test.

**G25 [Velocity]: `/loop` keeps the Claude chief going; Codex has no loop command.** What was done: `factory chief` gives Codex the role and a first instruction to loop; not verified in a long Codex session.

## 1.1.0: the independent review (`REVIEW-fable.md`)

Result: 47 kit tests pass. The dry run passes in all three landing modes (direct, auto, pr_only),
with no attempt used and no consistency findings. Every new check was sabotaged once by hand, and a
test failed each time (17 sabotages).

### High findings
**H1: Usage limit or model error counted as the unit's fault.** Done. `runners.classify`: non-zero exit, `is_error`, any subtype other than `success` (max turns, budget), and timeouts raise `RetryOnce` (no attempt). Usage or rate limits (429, "usage limit") raise `UsageLimit`: `var/factory/paused-until`, builds and reviews held, idle reason logged. A denial that left no change is `RetryOnce`; the denial count and the first denial are logged. `--max-turns` and `--max-budget-usd` come from `factory.json`. `daily_budget_usd` holds model steps and writes one `DEC-budget-<date>` card for the human. Lanes default to 2.

**H2: Exact claude pin plus auto-update stops the factory silently.** Done. `fingerprint.py --check` blocks only on a major.minor change and warns on a patch change (`toolchain_patch_changed` finding). `DISABLE_AUTOUPDATER=1` is set in `tick.sh`, in the template settings and for every `claude -p`, and the checklist says so. New finding `ticks_skipped` (the last three ticks skipped).

**H3: Landing assumes an unprotected main and a personal account.** Done. `landing: direct / auto / pr_only` and `merge_method: merge / squash / rebase`. `auto` and `pr_only` end in `pr_open`; the `watch` step reads `gh pr view --json state` and lands on `MERGED`. A closed pull request stops the unit. Every `gh` call goes through `gh_call`: a failure is `GhFailed` with gh's stderr, handled as RetryOnce (no attempt), and it shows on the card. `RULES.md` and the checklist document protection rules and a bot or service account.

**H4: Model-written code runs with the secrets.** Done, with honest limits. Every factory pytest run (red check, build check, each mutant, merged suite) gets only `PATH`, locale, `TERM` and `TZ`, plus a temporary `HOME` and `TMPDIR`. `PYTHONUSERBASE` keeps user-installed pytest. There is no network under bubblewrap `--unshare-net` (Linux, the Windows Subsystem for Linux (WSL), version 2,) or `sandbox-exec` (macOS) when they can start; otherwise `network_isolation: none` is reported. The token moved out of the env file into `~/.config/factory/claude-token`, passed only to `claude`. Limit (`RULES.md` section 13): files the clock user can read stay readable.

**H5: Flakes counted as attempts; retries uncapped.** Done. One fetch per tick in the main checkout (a failure skips the tick with a reason). Landing fetches again because it runs one at a time; a failure is a `Retry`. The patch id uses `git diff -U0`. `retries` per unit: after `max_retries` (3) in a row the unit stops with a card. Waiting for a pull request (`counts=False`) never stops it.


### Top 10, in order
1. Machinery vs unit failure: done (H1, H5).
2. Pause file, per-run caps, daily cap, lanes default 2: done (H1).
3. Major.minor pin, no auto-update, skipped-tick finding: done (H2).
4. Landing modes, `pr_open`, merge method, gh errors, protection and bot docs: done (H3).
5. Scrubbed, network-less test runs; token out of the env file: done (H4).
6. One fetch per tick, `-U0` patch id, retry cap: done (H5).
7. `brief_check.py` (eight sections, named test from the unit, named sabotage; called by the red check), equal-model refusal, builder and reviewer network off (`--settings` with an empty `allowedDomains` list): done. The file-growth finding and the note-to-backlog finding are **not done**; they were left out to stay near the line budget. `RULES.md` still says notes become backlog rows by the orchestrator.
8. `clock_host` guard: done (tick refusal plus `install-clock.sh` sets it). The lock ref on origin is not done; `clock_host` covers the common case.
9. Strikes by code (`lessons.py`: two within seven days make a lesson ready; at most two applied a day), escaped defects (`tick.py defect` plus an "Escaped defects" number and a daily line), and a lesson `measure` field: done. The weekly before-and-after report of each `measure` is **not done**.
10. Metrics and gate after every tick (`tick.sh`), unit titles on the Now tab, refusal reasons and minutes from queue to landed in the daily report and on the page, `install-clock.sh`, and a fuller allow list: done. A sender for `notify-text` is **not done**: it messages a person, so it is human-gated.

### Medium findings not covered above
- M1: `RULES.md` section 12 is rewritten as "one clock host per repo".
- M5: `tick.py prune` (work folders and local branches of landed and parked units) is done. A re-cut reuses the branch name (`worktree add -B`). The guard copy now skips `.venv`, `node_modules` and caches. `--delete-branch` is not used: inside a worktree gh tries to delete the checked-out local branch. Remote branches stay until GitHub's "delete head branch" setting removes them.
- M6: `install-clock.sh` replaces the hand-written plist and crontab steps and checks the tools. A separate `make doctor` is not done; install-clock covers the same checks.

### Low findings
- Catch-up rebase with a factory git identity: done.
- Team pre-commit hooks on the factory's build commit: skipped with `core.hooksPath=/dev/null`.
- `tick.sh` and `install-clock.sh` refuse a repo under `/mnt/`: done.
- Bedrock or Vertex full model ids: not done (set `builder_model` and `reviewer_model` to full ids in `factory.json`).
- Killing an orphaned `claude -p` before a rerun: not done. Recorded in the `README.md` ("Kill a running step").
- `cited_sources` ignoring `.sh` and `.html` citations: not done.

### Not verified on a real system
- No real `claude -p` build or review had run through the clock at 1.1.0 (the 1.2.1 real run later did). The `--settings` no-network sandbox, `--max-budget-usd` and the usage-limit text matching were checked against the command-line tool's option parser and a captured real answer. None was checked against a real limit event.
- The `gh pr merge --auto` call and the `pr view` polling ran against a fake `gh` only.
- launchd and Windows Task Scheduler were not run; on this Linux host install-clock was run with `--print`.
- `sandbox-exec` on macOS was not run; bubblewrap network isolation was tested here.
