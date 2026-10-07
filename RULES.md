# Rules

Each rule names the program that enforces it in brackets. A rule with no program is kept by the chief of staff and
checked by the reviewer. Why each rule exists: PRINCIPLES.md.

## 1. Plan first  [factory/planning/validate_matrix.py, factory/consistency.py]

- Plan from outcomes with the slice-matrix skill: outcomes, then requirements mapped to them, then tracer-bullet rows
  (each a thin working path through every layer it needs) and shared-engine columns found by looking across features.
- The row rules R1-R10 come from the slice-matrix checker. Every row takes at most 8 hours and touches at least two
  layers; a one-layer "enabling" row needs a reason, and such rows are at most 20% of the plan. Every row has a
  yes/no check with a command or an observable. Engines are built once and reused, there are no cycles, every
  requirement is covered, and every outcome has an early first proof.
- After every plan change the plan check exits 0; a failing plan is the finding `plan_invalid`.
- The plan must feed every lane: the dashboard shows the ready-queue width; below the number of lanes, builders wait.
- Do not re-cut the whole plan to size work. Size each row when it is reached (section 2).

## 2. Cut: sizing at cut time  [factory/unit_check.py, factory/brief_check.py, factory/cited_sources.py, factory/crew.py]

- Planning is required: `before-cut` refuses a row that is not a slice of a valid `plan/slice-matrix.json`. Only
  `planning = "skip"` in factory.toml lets a row through without one; the skip is logged and named in the daily report.
- Before a row is cut, run `factory crew before-cut <row>`. Sweeper Sid checks the row is not already done; a "done"
  verdict closes the row only after code re-runs its evidence command. The plan coverage auditor then maps every
  deliverable to a unit, and a dropped deliverable blocks the cut. A plan change after the audit blocks it again.
- A unit (`.ai/units/<row>/<n>.json`) holds one observable behaviour, described in a paragraph under 100 words with
  no code or path and one named sabotage. It names 3 to 5 tests, written `file.py::test_name`, and at most 3 code
  files; it may never touch `state.md`, the instructions files, `plan/`, `factory/`, `.claude/` or `var/`. It names its
  seam (the public function or command the tests call), one out-of-scope line and an estimate of at most 120
  minutes. A 1-2 file obvious change is one unit directly.
- Tests import the unit's module inside a helper, so the file collects and each test fails on its own.
- The brief (`.ai/specs/<row>-U<n>.md`) has eight numbered sections, a named test from the unit's own list and a
  named sabotage. Without one, Quill writes it on the clock and code checks it.
- Every file a brief cites exists; never cite a runtime file (`var/...`) by path.
- A unit about an outside tool (`"outside_tool": true`) names its research file; the red check refuses it until that
  file passes the research check and carries `Reviewed-by: <model> PASS` (written by code after the claim verifier).
- Queue units only from the live checkout (`tick.py enqueue` refuses inside a unit work folder).
- A unit's work folder must be a git worktree of this repo under `<repo>-worktrees/` (make it with
  `tick.py worktree`), and never the repo itself: a rebuild runs `git reset --hard` and `git clean -fdq` there, and a
  review runs `git checkout -- .`. Enqueue refuses any other folder, and the runners check again before touching one.

## 3. Red check  [factory/red_check.py]

Each named test fails because the unit's code is missing, not because the test file is broken. A fixture error, a
`NameError` in the test file, or an import of a module that is not one of the unit's files is refused. Every other
test passes. The only exceptions are the exact tests of other units that are moving, held, waiting in an open pull
request, or stopped with an open card. Before the check the unit catches up with main.

## 4. Roles and models  [factory/common.py roles_problem, core/probe.py, factory/runners.py, factory/crew.py]

- Every role is pinned in `factory.toml`: tool, exact model, effort, permissions, a versioned prompt file
  (`.ai/prompts/<role>.v<N>.md`), its output form and the code check that accepts it. Roles: chief-of-staff,
  builder, reviewer, researcher, summarizer.
- Models are found by the install probe (one tiny call per candidate exact ID in core/models.toml) and mapped to the
  role requirements in the preset by a fixed rule. Never a moving alias, never the tool's default model; every role
  command passes `{model}`.
- Only code starts a role. A session never picks or overrides a model and never starts a code-only role (the Claude
  Code agent guard refuses it). If a pinned model stops answering, the unit stops with a card. A `DEC-roles` card (a
  decision card for a person) asks the human what to do; nothing falls back. `factory probe` proposes a new roles file; a person approves it with
  `factory roles accept`.
- Every model step leaves a receipt: role, tool, model, effort, prompt file and hash, caps, minutes, cost, and for
  the reviewer the independence used. The dashboard shows them.

## 5. Build  [factory/runners.py, factory/drive.py]

- The builder role, fresh session, permissions from the roles file, no network where the sandbox works, no commit,
  no push. Only the listed files; no new or changed tests; only the checks the tests require.
- Time box: twice the estimate, at least 20 minutes. A rebuild starts from the cut and gets the last finding; each
  fix round is a fresh session.
- Machinery is never the unit's fault: a model error, a tool denial that left no change, a failed fetch or gh call
  is retried (once, or at most `max_retries` in a row); a usage limit pauses every model step.
- Budget: code writes every model run (build, review and every crew run) to the spend ledger the moment it ends.
  It checks `daily_budget_usd` before every model run and after each one. Reaching it raises one `DEC-budget` card,
  and no model run starts until tomorrow or until a person raises the budget. Per-run caps: `max_budget_build_usd`,
  `max_budget_review_usd`, `max_budget_crew_usd`; turns: `max_turns_build`, `max_turns_review`, `crew_max_turns`.
  Each preset ships caps that fit it, and `factory init` shows the expected cost per unit and per row.
- Permissions travel on the command line (`--permission-mode dontAsk --allowedTools ... --disallowedTools ...`): a new
  work folder is untrusted, and Claude Code ignores its project allow list there. A path write rule is
  `Edit(<path>)`; `Write(<path>)` never matches; never deny `Edit` or `Write` outright (it blocks answer files).
- Python caches never count: the build check ignores `__pycache__/` and `*.pyc`, and tracked caches are restored
  after a build and before a catch-up. `factory init` warns when the repo tracks cache files.

## 6. Build check  [factory/build_check.py, factory/guard.py]

The build check refuses the unit when a file outside the list changed, a test file changed, or a named test fails.
It also refuses when a new check survives the mutation guard, which means no named test fails when that check is
removed. Any other failing test refuses it too, with the same tolerance as the red check.

## 7. Review  [factory/review.py, factory/crew.py, factory/common.py]

- Inspector Grumble is the reviewer role: a different model from the builder when one answered the probe; otherwise
  the same model in a fresh session with a different review prompt (`same_tool_review = "fresh-session"`), which the
  dashboard marks weaker. A reused session or the builder's context is refused. The reviewer never sees the builder's
  report.
- Lockjaw joins when the unit's risk class or files match the risk rules; Thomasina when its files are a user-facing
  surface, and she must drive the running system. A `REJECT` verdict from either blocks the landing.
- The JSON form: `verdict`, `high` (each with kind, test_or_paragraph_line, file, line, reproduce_command, optional
  `cut`), `notes`, `suite_result_seen`. Only a complete high finding of a listed kind inside the unit's files blocks;
  every note and downgraded finding becomes a backlog row automatically.
- Stop after the second refusal or twice the estimate: the unit goes to `needs_split`. There is no third round.

## 8. Landing  [factory/land.py]

Landing first catches up with main by replaying the unit's own commits. The change must equal the reviewed change
(same patch id). Code then builds the exact commit that will land, the unit joined with the fetched base by
`merge_method`, and runs the whole suite on it. What happens next depends on `landing`.

- `pr_merge` is the default on a GitHub origin (github.com, or a GitHub Enterprise host gh is signed in to). The
  factory opens a pull request per unit with the review verdict in its body. After its checks it merges that pull
  request itself, by exact head commit.
- `auto` is the default when init finds the GitHub base protected by required reviews or checks. The factory opens
  a pull request per unit, and GitHub merges it when its rules pass. The repo must allow auto-merge.
- `pr_only` opens the pull request and leaves the merge to people.
- `direct` is the default only when the origin is not a GitHub host (GitLab, a bare repo, or no origin yet). Code
  pushes the tested commit to the base with `--force-with-lease=refs/heads/<base>:<fetched>`. A moved base is never
  overwritten.
- No mode pushes to the base of a GitHub origin unless factory.toml says `landing = "direct"` explicitly. Otherwise
  code refuses the push and raises a card. `factory init` writes the GitHub choice into factory.toml with its reason
  and prints why. The dashboard's Now tab shows the mode in use. Units land one at a time.

## 9. Stops, holds and cards  [factory/tick.py, factory/asks.py]

- A stopped unit gets a card for the chief of staff, who handles it and closes it in the same step. Never pushed to a person.
- To stop a moving unit: `tick.py hold <unit> --reason` (not runnable at once, its process ended, the running tick
  drained, the killed step's result void); re-cut; `tick.py release <unit> --note` (back to cut only after the re-cut
  validates).
- Decision cards (`DEC-<id>`) are for the human: one question, with a recommendation.
- Every hand change goes through `tick.py set|hold|release` with a reason; it is logged and counted.

## 10. The crew  [factory/crew.toml, factory/crew.py]

Each agent starts only on its trigger in crew.toml, as listed here.

- Sorter Sam starts on a backlog row with no triage record.
- Sweeper Sid starts before a cut.
- The plan coverage auditor starts before a cut and on a plan change.
- Quill starts on a unit with no brief.
- Inspector Grumble starts on every unit after its build check.
- Lockjaw starts on a unit whose risk class or files match the risk rules.
- Thomasina starts on a unit or a landed row with a user-facing surface.
- The spec conformance auditor starts on a row whose units all landed.
- The claim verifier starts on a landed row, and on every done claim, handoff and daily report.
- The Bookie starts on the daily retro.

Each uses the model of a role and is read-only, except for the one file it writes. It answers in a fixed JSON form
that code checks, and keeps its memory in `crew/<name>/memory.md` in the project (code appends it). A refused answer (a machinery
cause or a broken form) stops at once with one `crew-<agent>-<subject>` card for the chief of staff; the agent does not
run again on that subject while the card is open. Review-note rows (`N-...`) are not triaged at model cost.

## 11. Rows close by code  [factory/tick.py close-row]

A row is marked done only by `tick.py close-row`, after all its units landed and the row_landed crew passed
(no `DEVIATION`, `MISSING` or `SPEC_SKIP` finding, no `MISMATCH` claim, no `REJECT` verdict).

## 12. State file and the dashboard  [factory/consistency.py, factory/metrics.py, factory/staleness_gate.py]

- `state.md` Position starts `Updated YYYY-MM-DD HH:MM UTC.`; the commit hook refuses a time ten minutes off the clock.
- Keep at least two units queued while a row is building.
- No typed numbers on the dashboard; static sections declare their sources; the gate refuses anything stale.
- The dashboard shows estimate against actual per unit and row, so sizing improves through the retro.

## 13. One clock host, pinned tools  [factory/tick.py, factory/fingerprint.py]

`clock_host` names the one machine whose clock runs; `factory/toolchain.json` pins the tools by major.minor (a patch
change warns); auto-update is off for the clock user; three skipped ticks are a finding.

## 14. Where the factory may run  [factory/common.py folder_problem]

Two optional settings in factory.toml keep the factory out of the wrong folder; both are off by default.

- `require_clone_marker = true`: nothing runs unless a `.factory-clone` file is in the folder. The factory then never
  runs in the folder a person works in.
- `forbidden_paths = ["data/live.db"]`: nothing runs while any of these files exists in the folder, such as a real
  database or a credentials file.

Either guard stops the clock, the runners, the crew and the chief launcher.

## 15. Model-written code runs scrubbed  [factory/testrun.py]

Every factory test run gets only the `PATH`, locale, `TERM` and `TZ` variables, a temporary `HOME`, no tokens, and no network where
bubblewrap or sandbox-exec works. The Claude token, if used, lives only in `~/.config/factory/claude-token`.

## 16. Lessons  [factory/lessons.py, core/promote_lesson.py]

Two strikes in seven days make a lesson ready; at most two changes a day; rules grow only by replacing. Local
lessons live in the project and work at once. A proven lesson (applied, two strikes) is shared with
`factory promote-lesson`: a local branch on a kit checkout with a version bump and a CHANGELOG entry, and the exact
text printed. Lesson text can name a project, so pushing it is a separate step a person types
(`--push --confirm-remote <the remote URL>`); the slash command never pre-approves it.
Escaped defects (`tick.py defect`) have a target of zero.
