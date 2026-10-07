# Fixes and gaps

Part 1 lists every item of the independent review (REVIEW-fable.md) and what 1.1.0 did. Part 2 lists every gap found
while building 1.2.0 (the plugin, the adapters, roles, the probe, the crew, planning and sizing, the chief of staff,
hold and release), one row each, tagged [Quality] or [Velocity], with what was done or why not.

## Part 1: REVIEW-fable.md items (fixed in 1.1.0, carried into 1.2.0)

Result: 47 kit tests pass. The dry run passes in all three landing modes (direct, auto, pr_only),
with no attempt used and no consistency findings. Every new check was sabotaged once by hand, and a
test failed each time (17 sabotages).

### HIGH
| Item | Done |
|---|---|
| H1 Usage limit or model error counted as the unit's fault | Done. `runners.classify`: non-zero exit, `is_error`, any subtype other than `success` (max turns, budget), and timeouts raise `RetryOnce` (no attempt). Usage or rate limits (429, "usage limit") raise `UsageLimit`: `var/factory/paused-until`, builds and reviews held, idle reason logged. A denial that left no change is `RetryOnce`; the denial count and the first denial are logged. `--max-turns` and `--max-budget-usd` come from `factory.json`. `daily_budget_usd` holds model steps and writes one `DEC-budget-<date>` card for the human. Lanes default to 2. |
| H2 Exact claude pin plus auto-update stops the factory silently | Done. `fingerprint.py --check` blocks only on a major.minor change and warns on a patch change (`toolchain_patch_changed` finding). `DISABLE_AUTOUPDATER=1` is set in `tick.sh`, in the template settings and for every `claude -p`, and the checklist says so. New finding `ticks_skipped` (the last three ticks skipped). |
| H3 Landing assumes an unprotected main and a personal account | Done. `landing: direct / auto / pr_only` and `merge_method: merge / squash / rebase`. `auto` and `pr_only` end in `pr_open`; the `watch` step reads `gh pr view --json state` and lands on MERGED. A closed PR stops the unit. Every `gh` call goes through `gh_call`: a failure is `GhFailed` with gh's stderr, handled as RetryOnce (no attempt), and it shows on the card. RULES and the checklist document protection rules and a bot or service account. |
| H4 Model-written code runs with the secrets | Done, with honest limits. Every factory pytest run (red check, build check, each mutant, merged suite) gets only PATH, locale, TERM and TZ, plus a temporary HOME and TMPDIR. `PYTHONUSERBASE` keeps user-installed pytest. There is no network under bubblewrap `--unshare-net` (Linux, WSL2) or `sandbox-exec` (macOS) when they can start; otherwise `network_isolation: none` is reported. The token moved out of the env file into `~/.config/factory/claude-token`, passed only to `claude`. Limit (RULES 13): files the clock user can read stay readable. |
| H5 Flakes counted as attempts; retries uncapped | Done. One fetch per tick in the main checkout (a failure skips the tick with a reason). Landing fetches again because it runs one at a time; a failure is a `Retry`. The patch id uses `git diff -U0`. `retries` per unit: after `max_retries` (3) in a row the unit stops with a card. Waiting for a PR (`counts=False`) never stops it. |

### Top 10, in order
1. Machinery vs unit failure: done (H1, H5).
2. Pause file, per-run caps, daily cap, lanes default 2: done (H1).
3. Major.minor pin, no auto-update, skipped-tick finding: done (H2).
4. Landing modes, `pr_open`, merge method, gh errors, protection and bot docs: done (H3).
5. Scrubbed, network-less test runs; token out of the env file: done (H4).
6. One fetch per tick, -U0 patch id, retry cap: done (H5).
7. `brief_check.py` (eight sections, named test from the unit, named sabotage; called by the red check), equal-model refusal, builder and reviewer network off (`--settings` with an empty `allowedDomains` list): done. The file-growth finding and the note-to-backlog finding are **not done**; they were left out to stay near the line budget. RULES still says notes become backlog rows by the orchestrator.
8. `clock_host` guard: done (tick refusal plus `install-clock.sh` sets it). The lock ref on origin is not done; `clock_host` covers the common case.
9. Strikes by code (`lessons.py`: two within seven days make a lesson ready; at most two applied a day), escaped defects (`tick.py defect` plus an "Escaped defects" number and a daily line), and a lesson `measure` field: done. The weekly before-and-after report of each `measure` is **not done**.
10. Metrics and gate after every tick (`tick.sh`), unit titles on the Now tab, refusal reasons and minutes from queue to landed in the daily report and on the page, `install-clock.sh`, and a fuller allow list: done. A sender for `notify-text` is **not done**: it messages a person, so it is human-gated.

### MEDIUM not covered above
- M1: RULES 12 is rewritten as "one clock host per repo".
- M5: `tick.py prune` (work folders and local branches of landed and parked units) is done. A re-cut reuses the branch name (`worktree add -B`). The guard copy now skips `.venv`, `node_modules` and caches. `--delete-branch` is not used: inside a worktree gh tries to delete the checked-out local branch. Remote branches stay until GitHub's "delete head branch" setting removes them.
- M6: `install-clock.sh` replaces the hand-written plist and crontab steps and checks the tools. A separate `make doctor` is not done; install-clock covers the same checks.

### LOW
- Catch-up rebase with a factory git identity: done.
- Team pre-commit hooks on the factory's build commit: skipped with `core.hooksPath=/dev/null`.
- `tick.sh` and `install-clock.sh` refuse a repo under `/mnt/`: done.
- Bedrock or Vertex full model ids: not done (set `builder_model` and `reviewer_model` to full ids in `factory.json`).
- Killing an orphaned `claude -p` before a rerun: not done. Recorded in the README ("Kill a running step").
- `cited_sources` ignoring `.sh` and `.html` citations: not done.

### Not verified on a real system
- No real `claude -p` build or review has run through the clock. The `--settings` no-network sandbox, `--max-budget-usd` and the usage-limit text matching were checked against the CLI's option parser and a captured real answer, not against a real limit event.
- `gh pr merge --auto` and the `pr view` polling ran against a fake `gh` only.
- launchd and Windows Task Scheduler were not run; on this Linux host install-clock was run with `--print`.
- `sandbox-exec` on macOS was not run; bubblewrap network isolation was tested here.

## Part 2: gaps found while building 1.2.0

| # | Tag | Gap | Done |
|---|---|---|---|
| G1 | [Quality] | Plugin commands are namespaced (`/factory:factory-init`); the bare `/factory-init` works only while no other plugin has the same name. | Documented in README; names chosen to be unique. |
| G2 | [Quality] | A plugin cannot ship agent files with the right model: the models differ per machine. | The plugin ships no role agents; `factory init` generates them per project from the probed roles file. |
| G3 | [Quality] | A sub-agent call can override an agent file's model, and a session could start a code-only role. | PreToolUse hook `agent_guard.py` refuses a `model` and any code-only role; tested. Not verified inside a live Claude Code session. |
| G4 | [Velocity] | `/plugin update` does not update the scripts copied into a project. | `/factory-init` again shows "differs" and asks; `factory/VERSION` records the copied version. Not automatic. |
| G5 | [Quality] | Codex has no agent files. | Per-role profiles in `.codex/profiles/`; the clock passes model and effort on the command line anyway. Linking profiles into `$CODEX_HOME` is left to the person. |
| G6 | [Quality] | Codex's usage-limit answer was not captured from a real run; the limit words are a pattern. | The unknown-model answers of both tools and a normal answer of each were captured and are fixtures. Limit handling for Codex is unverified. |
| G7 | [Quality] | No real build or review ran through the 1.2.0 clock. | Every preset passes the dry run with fakes shaped from real runs; four tiny real calls were made (normal and unknown model, each tool). A real unit is checklist item 17. |
| G8 | [Quality] | The builder's and crew's no-network sandbox (`--settings`) is not verified in a real run. | Flags confirmed with the CLI parser only. The test runs that execute model-written code are network-isolated and tested. |
| G9 | [Velocity] | The model probe costs about thirteen tiny calls per init (ten Claude, three Codex). | Shown and asked first by `/factory-init`; `--probe-file` for offline or repeated setups. |
| G10 | [Quality] | Thomasina must drive the running system, but the kit has no standard "start the app" contract. | Her prompt says the brief names how; a missing way to start is a REJECT. A contract field is not built. |
| G11 | [Quality] | The reference scorecard definitions (cookies and slaps per event kind) were not available on this machine. | The Bookie gets a code-computed scorecard: accepted answers, refused forms, refuted done claims, PASS on a unit with an escaped defect. Richer rules are future work. |
| G12 | [Velocity] | Lockjaw and Thomasina run one after the other inside the review step. | Accepted for now; they run only on their triggers. |
| G13 | [Quality] | `hold` ends tracked model processes; a long test run in a check step finishes before the hold takes effect. | Its result is voided by the hold; the step is not a model process. |
| G14 | [Quality] | For the generic tool, a fresh reviewer session can only be declared (`fresh_session = true`), not checked. | Refused unless declared; the dashboard shows the independence used. |
| G15 | [Quality] | The 1.1.0 kit folder is not updated with the roles file, the crew, sizing and hold/release. | The 1.2.0 repo is the kit (core plus adapters); the fallback zip contains it. The 1.1.0 folder stays as shipped. |
| G16 | [Quality] | `promote-lesson --push` (a pull request on the kit repo) was not exercised: nothing may be pushed until checked. | Tested up to the local branch, version bump and CHANGELOG entry. |
| G17 | [Quality] | launchd and Windows Task Scheduler paths were not run (this host is Linux). | `install-clock.sh --print` writes them; cron path run. |
| G18 | [Quality] | Two slice-matrix eval cases carried another company's private records and Mac paths. | Dropped; 13 cases remain. The eval runner now reads slicer and judge commands from a config with exact model IDs. |
| G19 | [Velocity] | Plan rows in `plan/slice-matrix.json` and backlog rows are kept by hand in step. | The slice-matrix skill says to add a started row to the backlog as building; no sync code. |
| G20 | [Quality] | install-clock still wrote `clock_host` into the old `factory.json` and required `claude` on Codex-only machines. | Fixed: it edits `factory.toml` and checks only the tools the roles use. |
| G21 | [Quality] | Prompts contain JSON examples, so `str.format` on them crashed the first crew run. | `fill()` replaces only known placeholders; covered by every dry run. |
| G22 | [Quality] | A hold set between the tick's read and a step's first save was erased by that save. | `save_entry` keeps a stored hold and the step does not start; test and sabotage. |
| G23 | [Quality] | The vendored plan checker looked for its schema in the wrong folder. | Schema copied to `factory/schema/`; the plan_invalid test covers it. |
| G24 | [Quality] | A crew prompt could be deleted without any check noticing (init copies whatever exists). | `check_kit` verifies every prompt a role or crew agent names; sabotage test. |
| G25 | [Velocity] | `/loop` keeps the Claude chief going; Codex has no loop command. | `factory chief` gives Codex the role and a first instruction to loop; not verified in a long Codex session. |
