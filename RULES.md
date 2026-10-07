# Rules

Each rule names the program that enforces it in brackets. A rule with no program is kept by the chief of staff and
checked by the reviewer. Why each rule exists: PRINCIPLES.md.

## 1. Plan first  [factory/planning/validate_matrix.py, factory/consistency.py]
- Plan from outcomes with the slice-matrix skill: outcomes, then requirements mapped to them, then tracer-bullet rows
  (each a thin working path through every layer it needs) and shared-engine columns found by looking across features.
- Row rules R1-R10: every row at most 8 hours, at least two layers (one-layer "enabling" rows only with a reason, at
  most 20%), at least one yes/no check with a command or an observable; engines built once and reused; no cycles;
  every requirement covered; every outcome has an early first proof.
- After every plan change the plan check exits 0; a failing plan is the finding `plan_invalid`.
- The plan must feed every lane: the dashboard shows the ready-queue width; below the number of lanes, builders wait.
- Do not re-cut the whole plan to size work. Size each row when it is reached (section 2).

## 2. Cut: sizing at cut time  [factory/unit_check.py, factory/brief_check.py, factory/cited_sources.py, factory/crew.py]
- Planning is required: `before-cut` refuses a row that is not a slice of a valid `plan/slice-matrix.json`. Only
  `planning = "skip"` in factory.toml lets a row through without one; the skip is logged and named in the daily report.
- Before a row is cut, `factory crew before-cut <row>`: Sweeper Sid checks it is not already done (a "done" verdict
  closes the row only after code re-runs its evidence command), and the plan coverage auditor maps every deliverable
  to a unit; a dropped deliverable blocks the cut. A plan change after the audit blocks it again.
- A unit (`.ai/units/<row>/<n>.json`): one observable behaviour in a paragraph under 100 words with no code or path and
  one named sabotage; 3 to 5 tests written `file.py::test_name`; at most 3 code files (never state.md, the instructions
  files, plan/, factory/, .claude/, var/); a named seam (the public function or command the tests call); one
  out-of-scope line; an estimate of at most 120 minutes. A 1-2 file obvious change is one unit directly.
- Tests import the unit's module inside a helper, so the file collects and each test fails on its own.
- The brief (`.ai/specs/<row>-U<n>.md`) has eight numbered sections, a named test from the unit's own list and a
  named sabotage. Without one, Quill writes it on the clock and code checks it.
- Every file a brief cites exists; never cite a runtime file (`var/...`) by path.
- A unit about an outside tool (`"outside_tool": true`) names its research file; the red check refuses it until that
  file passes the research check and carries `Reviewed-by: <model> PASS` (written by code after the claim verifier).
- Queue units only from the live checkout (`tick.py enqueue` refuses inside a unit work folder).

## 3. Red check  [factory/red_check.py]
Each named test fails because the unit's code is missing, not because the test file is broken (a fixture error, a
NameError in the test file, or an import of a module that is not one of the unit's files is refused). Every other test
passes, except the exact tests of other units that are moving, held, waiting in an open pull request, or stopped with
an open card. Before the check the unit catches up with main.

## 4. Roles and models  [factory/common.py roles_problem, core/probe.py, factory/runners.py, factory/crew.py]
- Every role is pinned in `factory.toml`: tool, exact model, effort, permissions, a versioned prompt file
  (`.ai/prompts/<role>.v<N>.md`), its output form and the code check that accepts it. Roles: chief-of-staff,
  builder, reviewer, researcher, summarizer.
- Models are found by the install probe (one tiny call per candidate exact ID in core/models.toml) and mapped to the
  role requirements in the preset by a fixed rule. Never a moving alias, never the tool's default model; every role
  command passes `{model}`.
- Only code starts a role. A session never picks or overrides a model and never starts a code-only role (the Claude
  Code agent guard refuses it). If a pinned model stops answering, the unit stops with a card and a DEC-roles card
  asks the human; nothing falls back. `factory probe` proposes a new roles file; a person approves it with
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
- Budget: every model run (build, review and every crew run) is written to the spend ledger the moment it ends.
  `daily_budget_usd` is checked before every model run and after each one; reaching it raises one DEC-budget card and
  no model run starts until tomorrow or a person raises it. Per-run caps: `max_budget_build_usd`,
  `max_budget_review_usd`, `max_budget_crew_usd`; turns: `max_turns_build`, `max_turns_review`, `crew_max_turns`.
  Each preset ships caps that fit it, and `factory init` shows the expected cost per unit and per row.
- Permissions travel on the command line (`--permission-mode dontAsk --allowedTools ... --disallowedTools ...`): a new
  work folder is untrusted, and Claude Code ignores its project allow list there. A path write rule is
  `Edit(<path>)`; `Write(<path>)` never matches; never deny `Edit` or `Write` outright (it blocks answer files).
- Python caches never count: the build check ignores `__pycache__/` and `*.pyc`, and tracked caches are restored
  after a build and before a catch-up. `factory init` warns when the repo tracks cache files.

## 6. Build check  [factory/build_check.py, factory/guard.py]
Refused when a file outside the list changed, a test file changed, a named test fails, a new check survives the
mutation guard (no named test fails when it is removed), or any other test fails (same tolerance as the red check).

## 7. Review  [factory/review.py, factory/crew.py, factory/common.py]
- Inspector Grumble is the reviewer role: a different model from the builder when one answered the probe; otherwise
  the same model in a fresh session with a different review prompt (`same_tool_review = "fresh-session"`), which the
  dashboard marks weaker. A reused session or the builder's context is refused. The reviewer never sees the builder's
  report.
- Lockjaw joins when the unit's risk class or files match the risk rules; Thomasina when its files are a user-facing
  surface, and she must drive the running system. A REJECT from either blocks the landing.
- The JSON form: `verdict`, `high` (each with kind, test_or_paragraph_line, file, line, reproduce_command, optional
  `cut`), `notes`, `suite_result_seen`. Only a complete high finding of a listed kind inside the unit's files blocks;
  every note and downgraded finding becomes a backlog row automatically.
- Stop after the second refusal or twice the estimate: the unit goes to `needs_split`. There is no third round.

## 8. Landing  [factory/land.py]
Catch up with main by replaying the unit's own commits; the change must equal the reviewed change (patch id); build
the exact commit that will land (the unit joined with the fetched base by `merge_method`) and run the whole suite on
it; then by `landing`:
- `direct` (default, any host: GitHub, GitHub Enterprise, GitLab, a bare repo; no gh): push that tested commit to the
  base with `--force-with-lease=refs/heads/<base>:<fetched>`; if the base moved, nothing is overwritten and landing
  retries next tick.
- `pr_merge` (GitHub): open a pull request with the review form and merge it by exact head commit.
- `auto` (GitHub): GitHub merges when its branch rules pass. `pr_only` (GitHub): people merge.
`factory init` names the origin's host and the modes that work there. One landing at a time.

## 9. Stops, holds and cards  [factory/tick.py, factory/asks.py]
- A stopped unit gets a card for the chief of staff, who handles it and closes it in the same step. Never pushed to a person.
- To stop a moving unit: `tick.py hold <unit> --reason` (not runnable at once, its process ended, the running tick
  drained, the killed step's result void); re-cut; `tick.py release <unit> --note` (back to cut only after the re-cut
  validates).
- Decision cards (`DEC-<id>`) are for the human: one question, with a recommendation.
- Every hand change goes through `tick.py set|hold|release` with a reason; it is logged and counted.

## 10. The crew  [factory/crew.toml, factory/crew.py]
Each agent starts only on its trigger in crew.toml: Sorter Sam (a row with no triage), Sweeper Sid and the plan
coverage auditor (before a cut; the auditor also on a plan change), Quill (a unit with no brief), Inspector Grumble
(every unit after its check), Lockjaw (risk), Thomasina (surface; also when a row lands), the spec conformance auditor
and the claim verifier (a row landed; every done claim, handoff and daily report), the Bookie (the daily retro).
Each uses the model of a role, is read-only unless it writes one named file, answers in a fixed JSON form checked by
code, and keeps its memory in `crew/<name>/memory.md` in the project (code appends it). A refused answer (a machinery
cause or a broken form) stops at once with one `crew-<agent>-<subject>` card for the chief of staff; the agent does not
run again on that subject while the card is open. Review-note rows (`N-...`) are not triaged at model cost.

## 11. Rows close by code  [factory/tick.py close-row]
A row is marked done only by `tick.py close-row`, after all its units landed and the row_landed crew passed
(no DEVIATION, MISSING or SPEC_SKIP; no MISMATCH; no REJECT).

## 12. State file and the dashboard  [factory/consistency.py, factory/metrics.py, factory/staleness_gate.py]
- `state.md` Position starts `Updated YYYY-MM-DD HH:MM UTC.`; the commit hook refuses a time ten minutes off the clock.
- Keep at least two units queued while a row is building.
- No typed numbers on the dashboard; static sections declare their sources; the gate refuses anything stale.
- The dashboard shows estimate against actual per unit and row, so sizing improves through the retro.

## 13. One clock host, pinned tools  [factory/tick.py, factory/fingerprint.py]
`clock_host` names the one machine whose clock runs; `factory/toolchain.json` pins the tools by major.minor (a patch
change warns); auto-update is off for the clock user; three skipped ticks are a finding.

## 14. Model-written code runs scrubbed  [factory/testrun.py]
Every factory test run gets only PATH, locale, TERM and TZ, a temporary HOME, no tokens, and no network where
bubblewrap or sandbox-exec works. The Claude token, if used, lives only in `~/.config/factory/claude-token`.

## 15. Lessons  [factory/lessons.py, core/promote_lesson.py]
Two strikes in seven days make a lesson ready; at most two changes a day; rules grow only by replacing. Local
lessons live in the project and work at once. A proven lesson (applied, two strikes) is shared with
`factory promote-lesson`: a branch and pull request on the kit repo with a version bump and a CHANGELOG entry.
Escaped defects (`tick.py defect`) have a target of zero.
