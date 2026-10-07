# Setup checklist

When every check below passes, the clock runs on this machine and has landed one real unit. Do the items in order.
Each has a **check**; do not go on until the check gives the result shown.
`<repo>` is the full path of your work repo, for example `/home/<you>/code/<your-repo>`.

## A. Machine
1. **Windows only: Ubuntu inside the Windows Subsystem for Linux (WSL), version 2 (WSL2).** In PowerShell: `wsl --install -d Ubuntu`. Work inside Ubuntu
   from here on, and keep the repo under `~/`, not `/mnt/c`.
   Check: `wsl -l -v` shows Ubuntu with version 2 in its `VERSION` column; in Ubuntu, `pwd` of the repo starts with `/home/`.
2. **Tools.** Python 3.12, pytest, git, gh, Claude Code (see `README.md`).
   Check: `python3 --version && python3 -m pytest --version && git --version && gh --version && claude --version` prints five versions.
   Turn off Claude Code auto-update for the clock user (`export DISABLE_AUTOUPDATER=1`, item 13): an
   update would change the pinned version under a running factory.
3. **Sign-ins.** `gh auth login` and `claude` (sign in once, interactively).
   Check: `gh auth status` says logged in; `claude -p "Reply with the word ok" --model haiku` prints ok.
4. **Sandbox support (Linux and WSL2).** `sudo apt install bubblewrap socat`. macOS needs nothing.
   Check: in Claude Code, `/sandbox` shows the sandbox as available, and
   `bwrap --dev-bind / / --unshare-net true; echo $?` prints `0` (test runs then have no network).

## B. The kit
5. **Kit tests pass.** Check: in a clone of the kit, `python3 -m pytest -q` ends with `passed` and no `failed`.
6. **Dry run passes.** Check: `python3 core/sample/dry_run.py /tmp/factory-dry-run --preset <your preset>` ends with `DRY RUN PASSED`.
7. **Plugin (Claude Code).** `claude plugin marketplace add <owner>/claude-factory-kit` (or the clone's path), then
   `claude plugin install factory@factory-kit`.
   Check: `claude plugin list` shows factory; Codex users instead run `bash adapters/codex/install.sh` and check `~/.codex/skills/factory-init/SKILL.md` exists.

## C. The work repo
8. **Green suite and a remote.** Check: `python3 -m pytest -q` passes and `git remote get-url origin` prints your repo.
9. **Init with the model probe.** `/factory-init` (or `factory init --apply --preset <p> --adapter <a>`). It makes one
   tiny call per candidate model of each installed tool, writes `factory.toml`, and shows each role's model and why.
   Check: `python3 factory/tick.py status` runs; `factory.toml` names only exact model IDs; if the reviewer shares the
   builder's model, the line says "fresh session only (weaker)".
10. **Toolchain pin.** Check: `python3 factory/fingerprint.py --check factory/toolchain.json; echo $?` prints `0`.
11. **State file.** Fill the Position block of `state.md` with the real time (`date -u +"%Y-%m-%d %H:%M"`).
    Check: `python3 factory/consistency.py; echo $?` prints `0`.
11b. **Optional guards.** If the factory gets its own clone, add `require_clone_marker = true` to factory.toml and
    create `.factory-clone` in that clone only; list files that must never be there (a real database) in
    `forbidden_paths`. Check: in your own working folder, `python3 factory/tick.py tick` prints a skipped line naming
    the guard.
12. **Commit and push the factory.** Check: `git status` is clean and GitHub shows `factory/` on main.

## D. The clock
13. **Environment for the clock.** Create `~/.factory-env.sh` with
    `export PATH="<folder of claude>:<folder of gh>:/usr/local/bin:/usr/bin:/bin"` and
    `export DISABLE_AUTOUPDATER=1` (find folders with `which claude gh`). No token in this file.
    Check: `env -i HOME=$HOME bash -c '. ~/.factory-env.sh; claude --version && gh --version'` prints both.
14. **Claude sign-in for the clock.** If `claude -p "say ok" --model haiku` works from
    `env -i HOME=$HOME bash -c '. ~/.factory-env.sh; ...'`, you are done. If not, and your company
    allows it, run `claude setup-token` and save the token in `~/.config/factory/claude-token`
    (`chmod 600`). The factory passes it only to `claude`, as `CLAUDE_CODE_OAUTH_TOKEN`.
    It is a credential: follow company policy and never commit it.
    Check: `ls -l ~/.config/factory/claude-token` shows `-rw-------`, or the first command works.
15. **Start the clock.** `/factory-install-clock` or `factory clock` (it runs `factory/install-clock.sh`). It checks the tools and the
    gh sign-in, and writes this machine into `clock_host` in `factory.toml`. It installs the 5-minute schedule: cron
    on Linux and WSL2, launchd on macOS. On WSL2 it also prints the systemd steps and the Windows Task Scheduler
    line. Then it runs one tick. Add `--print` to only see what it would do.
    Commit `factory.toml` so no second machine starts a clock.
    Check: it ends with `READY`; after 10 minutes `python3 factory/consistency.py` has no
    `clock_stale` or `ticks_skipped` finding.
16. **Landing mode.** Run init after the repo has its origin. On a GitHub origin init picks `pr_merge`: the factory
    opens a pull request per unit with the review verdict and merges it itself after its checks, never pushing to
    main directly. When main is protected by required reviews or checks, init picks `auto` instead; then allow
    auto-merge in the repo settings.
    `direct` is the default only without a GitHub host, and init prints why. Set `merge_method` to what the repo
    allows. Use a bot or service account for `gh auth login` on the clock host if people may not self-merge.
    Check: `grep ^landing factory.toml` shows the mode init chose, the dashboard's Now tab shows the same mode, and
    `gh api repos/<owner>/<your-repo>/branches/main/protection` agrees (an HTTP 404 "Branch not protected" means pr_merge).

## E. The chief of staff, first real unit and the dashboard
16b. **Chief of staff.** `tmux new -d -s factory "factory chief"` starts the role and its loop with its pinned model.
    Check: `factory chief --print` shows the model from factory.toml; `tmux ls` lists the session.
17. **One unit end to end.** Plan a small row (skill slice-matrix), add it to `plan/backlog.md` as `building`, run
    `factory crew before-cut <row>`, and let the chief of staff cut one unit.
    Check: `python3 factory/tick.py status` shows the unit; within an hour it is `landed`, and its pull request is merged on GitHub (or its commit is on main for a non-GitHub origin).
18. **Cost is recorded and capped.** Set `daily_budget_usd` and the per-run caps in `factory.toml`
    with whoever owns the budget.
    Check: `grep cost_usd var/factory/log.jsonl | tail -2` shows numbers for the build and the review.
19. **Dashboard.** `/factory-dashboard` (or `factory dashboard` and open the printed file).
    Check: the gate prints `clean`; the artifact link opens and the Now tab shows the clock's last tick.
20. **Daily report and retro.** Each evening, run the `daily-report` and `retro` skills.
    Check: `ls var/factory/daily/` has today's file; `.ai/lessons.jsonl` has today's strikes, if any.
