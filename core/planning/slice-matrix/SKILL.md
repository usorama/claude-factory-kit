---
name: slice-matrix
description: Start from outcomes, map requirements to them, and cut a plan into small, complete work items with shared engine columns, explicit blockers, and computed completion waves. Validate the JSON and render a Markdown grid.
---

# Slice matrix

Start with the outcomes the plan must achieve. Map requirements to those outcomes,
then cut rows that each deliver or prove one complete behavior. Columns
show capabilities shared by those rows. For example, uploading a profile photo
can create a small storage engine. Adding a cover image can reuse that engine.
The engine first arrives inside the working photo-upload path.

This combines Matt Pocock's tracer-bullet approach in `to-tickets` with a
look-across pass that finds shared engines. A tracer bullet is a thin path through all the layers
needed to make one behavior work. An engine is a capability needed by two or
more features, built once and reused. An engine already built before this plan
may have just one user here. Do not make engine-only construction rows.

## Build the matrix

1. **A1: Read the source and write outcomes first.** Include its referenced
   requirements and decisions. Record a non-empty `source.outcomes` array of
   `{id, text, requirements, first_proof}` objects. Describe the intended result
   in `text` and fill `first_proof` with a slice ID after cutting the rows.
   When outcomes are not named, derive them only from the stated goal and record
   that mapping in `source.description`. If neither outcomes nor a goal is
   supplied, write a `missing_source` stop file with one question asking for
   the outcomes. Do not invent a goal.
2. **A2: Map requirements to outcomes.** Preserve every requirement ID in
   `source.requirements` and link each to at least one outcome. Every outcome
   must have at least one requirement, and every link must name a source ID. If the
   source has no IDs, assign stable IDs and make their mapping clear in the
   source description. If a required source is missing, acceptance is not
   testable, or the source's stated order contains a cycle that cannot be broken
   without changing the plan's meaning, write the stop file below and end here.
   Do not invent missing requirements, acceptance targets, or a new order.
3. **A3: List features.** Put the full feature list in `source.features` before
   cutting rows. Describe what the user can do or what a check can prove.
4. **A4: Look across features.** Find capabilities needed by at least two
   features, such as storage, feature gates, or mounting the same component in
   several places. Give each an engine ID and title. Keep capabilities needed
   by only one feature inside that feature, unless the engine already exists.
   Mark an engine already built before this plan with `"existing": true` and
   record its source evidence in `source.description`. It may serve one row.
   An empty engine list is valid.
5. **A5: Cut tracer-bullet rows.** Each slice delivers or proves one behavior,
   touches every layer it needs, fits one focused agent session, and has binary
   acceptance checks. Name its direct blockers. Split work estimated above
   eight hours, the brief's session limit. S/M/L describes relative size, not
   permission to exceed that limit.
   The walking skeleton, the first thin working path, must advance at least one
   stated outcome through its covered requirements.
   Every slice must have a non-empty `outcomes` array naming the outcomes it
   moves. Its `covers` must share at least one requirement with each named
   outcome. For each outcome, set `first_proof` to a slice whose acceptance
   shows that outcome working for a real user end to end. This is a thin
   working path, not the complete outcome. That slice must name the outcome
   in its own `outcomes` array.
6. **A6: Fill cells.** In each row's `engines` object, use `builds` for the first
   thin version and `uses` for reuse. Omit unused cells. Exactly one row builds
   each new engine. Every user of it lists that builder directly in `blocked_by`.
   The builder must be a vertical slice delivering a real path, even if an
   enabling slice prepares work elsewhere. An existing engine has zero `builds`
   cells and at least one `uses` cell. It adds no builder dependency.
7. **A7: Order for early outcomes.** After the walking skeleton, bring each
   outcome's `first_proof` as early as its real blockers allow. Aim for every
   first proof in the first third of the waves. Round that wave count up:
   with four waves numbered 0 through 3, the target is waves 0 and 1.
   Explain in `source.description` why any first proof falls outside the target.
   Give outcome-finishing slices priority as their blockers allow. Inspect the
   timing report and revise unnecessary dependencies that delay results.
   Preserve mandatory gates. Row order alone does not change computed waves.
8. **A8: Write JSON.** Follow [the schema](schema/slice-matrix.schema.json) and
   [the complete example](examples/toy.json), or the
   [existing-engine example](examples/existing-engine.json). For store or vendor
   selection, use the [fallback example](examples/conditional-store.json).
   Use `covers` to
   connect slices to source requirement IDs. Keep IDs unique across requirements, engines, and
   slices. Layer names must be distinct within a row. Normally omit `wave`.
9. **A9: Check and review.** Run the checker and fix every reported rule until
   exit 0. Have a second model review whether rows are genuinely complete,
   thin paths, whether acceptance is binary, and whether shared capabilities
   were found across features. Review whether the skeleton advances an outcome
   and each first proof demonstrates a real user path. Check that first proofs
   and outcome-finishing slices arrive as early as their blockers allow, with
   reasons for first proofs outside the first-third target.
   A small model may answer the narrow question "does this
   slice touch more than one layer?" as a hint only. The checker decides
   whether the recorded format and graph pass. Recheck after review edits.
10. **A10: Render.** Render the validated grid. Rows are slices, columns are
   engines, and the wave list shows what can start after its blockers finish.
   Both scripts report a success path and a worst path for each outcome.
   The success path skips every conditional slice. The worst path triggers every
   condition and treats the referenced candidates as failed. Each path reports
   "first working at wave N, complete at wave M". N is its `first_proof` slice's
   wave if that slice passes. M is the last passing slice explicitly naming
   that outcome. Sharing a requirement alone does not count.
   A failed or skipped first proof is unavailable. Completion is unavailable
   when no slice passes or a required slice is blocked. Use a shared verification
   slice after the alternatives as `first_proof` to prove either selected path.
   Both reports include the median first-working wave across outcomes. Waves
   start at 0. Late timing is information, never a validation failure. This
   report describes the plan, not delivered results.

## Fallbacks and alternative choices

Try store A first. If A fails or is explicitly not selected, try store B.
Then verify whichever store passed. The dependency fields for those rows are:

```json
[
  {"id": "S1", "blocked_by": []},
  {"id": "S2", "blocked_by": [], "runs_if": {"failed": ["S1"]}},
  {"id": "S3", "blocked_by": [], "blocked_by_any": [["S1"], ["S2"]]}
]
```

These are field excerpts. [The complete example](examples/conditional-store.json)
includes acceptance checks and outcome links. Its success path finishes at wave 1.
Its worst path finishes at wave 2.

`blocked_by` requires every listed slice to pass. `runs_if.failed` requires every
listed slice to finish failed or explicitly not selected before this slice can
run. A pending or unattempted candidate is not a failure or a pass. Never put the
same ID in both fields. Failure conditions impose order without promising success.

`blocked_by_any` is a list of alternative groups. Every member of one group must
pass. For example, `[["S1", "S4"], ["S2"]]` means S1 and S4 both passed, or S2
passed. Mandatory `blocked_by` entries still apply. Move a conditional blocker
out of `blocked_by` and into these groups alongside its alternative. Adding an
alternative field while leaving the conditional slice mandatory remains invalid.
There must be a passing group on the success path for an unconditional consumer.

All dependency edges participate in cycle detection, including condition edges
and every alternative group. Within each group the latest member sets its wave.
The success path uses the earliest satisfiable group. The worst path uses the
latest satisfiable group, after excluding failed candidates. Both paths also wait
for mandatory blockers and failure conditions. An optional stored `wave` means
the worst-path wave. Skipped slices have no success-path wave.

These are planning scenarios. The tool does not run slices or record live status.
If triggering every condition leaves required work blocked, the report says the
outcome is unavailable rather than counting a failed choice as passed. Review
that result and revise the alternatives before using the plan.

## Stop file

Write this JSON object to the requested output path instead of a matrix. Use
`vague_acceptance` for missing testable acceptance, `contradictory_order` for
an unresolvable source-order cycle, or `missing_source` for an unavailable
required source or a plan with no stated outcomes and no goal from which to
derive them. State the specific obstacle and ask what is needed to proceed.
For missing outcomes, ask exactly one question:

```json
{"stop":true,"reason":"The plan states neither outcomes nor a goal.","questions":["What outcomes must this plan achieve?"],"rule":"missing_source"}
```

```json
{"stop":true,"reason":"The source gives no testable acceptance target.","questions":["Which observable result would count as success?"],"rule":"vague_acceptance"}
```

All four fields are required. `reason` and every question must contain nonblank
text, and `questions` must have at least one entry. No extra fields, slices, or
engines belong in a stop file. Run the validator: exit 3 with `STOP` and the
reason confirms a valid stop. Exit 1 means fix the stop file's format. End
without rendering or inventing slices once the stop file validates.

## Fixed fields and rules

The root has `source`, `engines`, and `slices`. `source` has `description`,
`requirements` (ID strings), `outcomes`, and `features` (feature descriptions). An engine
has `id`, `title`, and optional boolean `existing` (false by default). True
means it was built before this plan. A slice has the fields in R1 plus `covers`,
`outcomes`, and `engines`.
Unknown fields and unknown engine, requirement, outcome, or first-proof slice
references are rejected.

Two optional slice fields carry facts from outside the plan:
- `blocked_by_decisions`: IDs of decisions a person must make before the slice
  may start (for example `D3`). They do not affect waves; they mark which rows
  wait on a person.
- `scope`: `base` (default) or `product-setting`, for a row that only
  configures one product or company on top of a general system.

An acceptance item has `check`, `type: "yes_no"`, and at least one of `command`
or `observable`. State a concrete pass condition in the check. A command must
include its expected result there. The checker never executes commands.

| Rule | Required result |
| --- | --- |
| R1 | Each row has id, title, behavior, layers_touched, acceptance, blocked_by, size (S/M/L), and positive est_hours at most 8. At least two distinct layers and one yes/no check with a command or observable are required, subject to R7's layer exception. |
| R2 | Each new engine appears in at least two distinct rows. Both builds and uses count as participation. An existing engine needs at least one uses row. |
| R3 | Each new engine has exactly one builds cell in a vertical row. That builder directly blocks every uses row. An existing engine has zero builds cells and at least one uses cell, with no builder dependency. |
| R4 | All blocker IDs exist. The graph across mandatory blockers, alternative groups, and failure conditions has no cycles, including self-blocking. |
| R5 | Every source requirement ID is covered by at least one row. Covers cannot name unknown requirements. |
| R6 | Roots are wave 0. Mandatory blockers and failure conditions add one wave after their latest prerequisite. Alternative groups use the earliest satisfiable group on the success path and the latest on the worst path. An optional stored wave must match the worst path. |
| R7 | A one-layer row requires kind: enabling and a nonempty reason. Enabling rows are at most 20% of all rows. Every enabling row requires a reason. Zero-layer rows are invalid. |
| R8 | IDs are unique and the file conforms to the supplied draft 2020-12 schema. |
| R9 | Source outcomes are required and their IDs are unique. Every outcome links to at least one known requirement. Every source requirement leads to at least one outcome. Each slice names one or more known outcomes and shares a covered requirement with each. Every outcome has a first_proof slice that exists and names that outcome. |
| R10 | Optional runs_if.failed and blocked_by_any contain nonempty, unique ID lists with known slice references. A slice cannot require the same candidate to fail and pass. A conditional slice cannot be a mandatory blocker. Alternative groups must provide an unconditional consumer a passing success path. |

The R7 exception overrides R1's two-layer minimum. `kind` defaults to `vertical`.
Use enabling only for necessary preparation that cannot itself deliver a full
path. The 20% cap comes from the brief and includes all rows marked enabling.

The checker makes format and dependencies deterministic. It can count declared
layers and require a declared yes/no check, but cannot prove those declarations
are truthful, that an estimate is realistic, or that a path is complete. Those
judgments remain with the author and second model. A green matrix is a checked
plan, not evidence that the software works.
In particular, the checker verifies the `first_proof` link, while the author
and reviewer judge whether its acceptance proves a real user path end to end.

## Run locally

Replace `<skill-dir>` and `<matrix.json>` with their actual paths. Both scripts
use Python 3's standard library and work from any current directory.

```sh
python3 <skill-dir>/scripts/validate_matrix.py <matrix.json>
python3 <skill-dir>/scripts/render_matrix.py <matrix.json> > <matrix.md>
python3 -B -m unittest discover -s <skill-dir>/tests -v
```

The checker prints all detected failures with R1–R10 IDs. Exit 0 means a valid
matrix, exit 1 means invalid input, and exit 3 means a valid stop file. The
renderer emits no grid for invalid input or a stop file. It returns the same
exit codes and computes matrix waves itself. Cyclic rows have no computable
wave, so R4 reports the cycle rather than
inventing a value for R6. The validator supports the schema keywords used by
this bundled schema, not arbitrary JSON Schema documents. It fails closed if
the schema gains an unsupported keyword.
