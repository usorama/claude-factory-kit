# Gap review: claude-factory-kit 1.0.0

Reviewed 2026-10-07 against `the kit` (read-only) and the reference `the reference repo`.

## What was verified

- Kit tests: 27 passed. Dry run: `DRY RUN PASSED`.
- Three real `claude -p --model haiku` probes (about 0.09 USD): the pattern `Bash(python3 -m pytest *)` is honoured under `--permission-mode dontAsk`; a project Stop hook fires in a never-opened folder with no trust prompt, so worktrees are fine; a denied command gives **exit 0, `is_error: false`, and a filled `permission_denials` list**.
- `gh 2.45` has `pr merge --match-head-commit`. The JSON fields the kit reads are real.
- Present and tested: cited-source and `var/` path refusal, red-check cut-defect refusal, stopped-unit tolerance by exact id, catch-up by replay, merged-result suite, patch-id match, unit cards vs `DEC-` cards, staleness gate. Here the kit is ahead of the reference (lanes on, review retry once, exact-head merge).

The machine is sound. The gaps are around it at a workplace: usage limits, auto-update, branch protection, secrets, and a learning loop still driven by hand.

## HIGH

**H1. A usage limit or model error is treated as the unit's fault.** `kit/factory/runners.py` `build()`: a non-zero exit (rate limit, auth, weekly limit) returns `ok=False`, which costs an attempt; a second tick sends the unit to `needs_split`. With 4 lanes, one limit window wrongly splits four units and writes four cards. `is_error` is only stored as a field. There is no `--max-budget-usd`, no `--max-turns`, no daily cap, and `permission_denials` is not logged (the probe shows a denied builder exits 0 and the kit then reports "the builder changed no unit file" with no cause). The reference lost 23.9 hours to a weekly limit for the same reason.
Fix: in `claude_usage`, classify `is_error`, non-zero exit, `stop_reason in (max_turns, budget_limit)` and non-empty `permission_denials` as *machinery*: raise `RetryOnce`, never an attempt. On a rate/usage-limit subtype write `var/factory/paused-until` and make `drive.tick` skip model steps until then (log the idle reason). Pass `--max-turns` and `--max-budget-usd` from `factory.json` (per build and per review), add a `daily_budget_usd` the tick checks before launching. Log `permission_denials` count and first command. Default `lanes` to 2 on a single seat.

**H2. The exact `claude --version` pin plus auto-update stops the factory silently.** `kit/install.sh` pins `"claude": "2.1.290 (Claude Code)"`; `tick.sh` refuses every tick after the next background update, writing only to `ticks.log` (`consistency.py` has no finding for skipped ticks, so the dashboard shows "clock stale" at best).
Fix: pin `claude` to major.minor and warn, not refuse, on a patch change; set `"env": {"DISABLE_AUTOUPDATER": "1"}` in the template settings and say so in step 2; add a `toolchain_skipped` consistency finding when the last tick lines are skips.

**H3. Landing assumes an unprotected main and a personal account.** `kit/factory/land.py` runs `gh pr merge --merge --match-head-commit`. Under required reviews, required status checks, CODEOWNERS or squash-only (the normal workplace setting) `gh` fails with `CalledProcessError`, which `land_step` does not catch, so the unit goes `errored` with a card the orchestrator cannot fix. Merges appear as the founder's personal commits; many companies forbid unattended self-merge.
Fix: `factory.json` gets `merge_method` and `landing: direct | auto | pr_only`. `auto` uses `gh pr merge --auto`, a new state `pr_open`, and the tick polls `gh pr view --json state` to reach `landed`. Document the protection rules (a required check the factory posts, a bot or GitHub App identity, `--delete-branch`). Catch the error and put `gh`'s stderr in the card.

**H4. Untrusted code runs unsandboxed with the secrets.** The builder is sandboxed, but the code it writes is executed by the cron process in `testrun.run()` (red check, build check, every guard mutant, merged suite) with the full environment: `~/.factory-env.sh` (which step 16 says may hold the OAuth token), `~/.config/gh/hosts.yml`, `~/.claude/.credentials.json`, network. A prompt injection in any repo file can make Sonnet write a test-time exfiltration that the factory runs for it.
Fix: run pytest with a scrubbed env (drop `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `GH_TOKEN`; `HOME` to a temp dir), under `bwrap --unshare-net` or `sandbox-exec` where available. Keep the token out of the env file and say in RULES that the suite runs as the clock user.

**H5. Machinery flakes count as attempts; retries have no cap.** Four lanes call `git fetch` on the same `.git` at once (`catch_up`); lock contention returns "cannot fetch", which is `ok=False` (an attempt). `Retry` in `kit/factory/drive.py` has no counter: after a rebase that changes only context lines, `git patch-id` differs, the unit goes back to review (an Opus call), lands, and if main moved again repeats. On a busy team repo this can burn reviews for hours.
Fix: one `git fetch` per tick in the main checkout before dispatching lanes; a fetch failure raises `Retry`. Compute the patch id on `git diff -U0`. Add `retries` to the entry; after 3 the unit is `errored`.

## MEDIUM

**M1. Rules promised but not enforced.** RULES 2 names `cited_sources.py` as enforcing eight sections, a named test and a named sabotage; it only checks cited paths. RULES 6 says a different model reviews; nothing refuses `builder_model == reviewer_model`. RULES 4 says "no network", but the template sandbox allows github.com and pypi.org. RULES 6 says downgraded notes are "filed as a backlog row"; nobody does it. The defect library and rules file "never grow"; nothing measures them. RULES 12 "a second host joins" is impossible: `var/` is local.
Fix: `brief_check.py` (sections, named test in the unit's list, sabotage line) called by `red_check`; `tick` refuses equal models; builder and reviewer get `--settings '{"sandbox":{"network":{"allowedDomains":[]}}}'`; `consistency.py` findings for file growth and notes without a backlog row; rewrite RULES 12 as "one clock host per repo".

**M2. Two factories on one repo go undetected.** A teammate who clones, runs `install.sh` and starts cron has a second queue and a second orchestrator; branches and PRs collide. CLAUDE.md says "never two orchestrators" but cannot see the other machine.
Fix: `factory.json` `clock_host` (hostname) checked by `tick.sh`; or a lock ref `refs/factory/clock` on origin refreshed each tick and refused when held by another host.

**M3. The self-improvement loop is not closed by code.** `strikes` and `status: ready` are set by hand in the retro; "two strikes in seven days" is computed by nobody. "Zero escaped defects", the one target from day one, has no record and no number in `metrics.py`. A lesson marked `applied` is never measured against the mistake it was meant to remove.
Fix: `lessons.py strike <id>` and `lessons.py ready` (date arithmetic in code); `var/factory/defects.jsonl` with a `tick.py defect` command and an "Escaped defects" number; each lesson carries `measure` (a metric name and baseline) and the weekly report prints it. `consistency.py` refuses more than two `applied` lessons per day.

**M4. A manager cannot see "today" without a human publishing.** Publishing needs the orchestrator session. The Now tab shows `B12-U3 checked` with no title. The daily report has counts but not why a check or review refused, nor cycle time per unit. `asks.py notify-text` has no sender.
Fix: `tick.sh` runs `metrics.py` and the gate after every tick so the local page is always current; add `title` to `now_section`, refusal outcomes and minutes-to-land to `daily_report.py`; a scheduled routine or a webhook for `notify-text`, founder-gated.

**M5. Branch and worktree hygiene.** Landed branches are never deleted; worktrees accumulate; re-cutting unit `n` after a park fails because `unit/<row>/<n>` exists; the guard copies the whole tree per mutant (`.venv`, `node_modules`).
Fix: `--delete-branch` on merge, `tick.py prune`, reuse of an existing branch, `.gitignore` patterns in `guard.survivors`.

**M6. Onboarding a non-expert.** Twenty hand steps: write a launchd plist from prose, edit `/etc/wsl.conf`, build `~/.factory-env.sh`, and step 16 never names `CLAUDE_CODE_OAUTH_TOKEN`. The template allow list lacks `tick.py worktree/enqueue/set`, `asks.py decide/close`, `staleness_gate.py`, `git add/commit`, so `/orchestrate` prompts constantly.
Fix: `factory/install-clock.sh` that writes the crontab line, the plist or the Task Scheduler command and verifies with one tick; name the variable; extend the allow list; a `make doctor` that runs steps 2, 3, 13, 14 together.

## LOW

- `catch_up` rebases without `-c user.name`; a clock user with no global git identity fails every catch-up.
- Team pre-commit hooks (linters) run on the factory's own build commit under cron; use `-c core.hooksPath=/dev/null` or document.
- Enterprise gateways (Bedrock/Vertex) need full model ids; `sonnet`/`opus` lag.
- `clear_interrupted` can start a second builder while an orphaned `claude -p` still runs; record and kill the child pid first.
- `tick.sh` should refuse a repo under `/mnt/` (hard-link locks fail on drvfs). `cited_sources` ignores `.sh` and `.html` citations.

## Top 10 fixes, in order

1. Machinery vs unit failure: model errors, denials and fetch failures become `RetryOnce`/`Retry`, never attempts; log `permission_denials` (H1, H5).
2. Usage-limit pause file and per-call `--max-turns`/`--max-budget-usd` plus a daily cap; lanes default 2 (H1).
3. Pin `claude` to major.minor, set `DISABLE_AUTOUPDATER`, add a `toolchain_skipped` finding (H2).
4. `landing: auto | pr_only` with `pr_open` state, `merge_method`, caught `gh` errors, documented protection and bot identity (H3).
5. Scrubbed, network-less environment for every pytest run the factory makes; token out of the env file (H4).
6. One fetch per tick, `-U0` patch id, retry cap (H5).
7. `brief_check.py`, equal-model refusal, builder/reviewer network off, file-growth and note-to-backlog findings (M1).
8. `clock_host` guard against a second factory (M2).
9. Code-computed strikes, escaped-defects record and number, lesson `measure` field (M3).
10. Metrics and gate on every tick, titles and refusal reasons on the page, `install-clock.sh` and a complete allow list (M4, M6).
