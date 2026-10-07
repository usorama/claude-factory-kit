# Slice-matrix evaluations

This suite checks whether a plan becomes useful, complete work items. It contains
13 fixed cases. Reading time: 3 minutes.

Each case has a source, an expected property list, and a reason for inclusion.
The source is the slicer's input. Expected properties are scoring oracles, not an
exact answer. Do not show them to the slicer or revise them to fit its output.
The source paths in retrospective cases are provenance, not instructions to
execute those historical plans. The histories describe only the inspected records.

## Run and score

From the skill directory, use a fresh absolute result directory:

```sh
python3 -m pytest evals/test_run_evals.py -q
python3 evals/run_evals.py run --results /absolute/new/results --config evals/config.example.json
python3 evals/run_evals.py judge --results /absolute/new/results --config evals/config.example.json
python3 evals/run_evals.py score --results /absolute/new/results
```

The scorer uses Python's standard library. Only the tests require pytest.
The slicers and the judge are the commands in the --config file (exact model IDs only).
Each slicer receives only the brief's one-sentence skill/source/output
prompt. The judge runs separately, read-only.
Launches are sequential. Each has a 900-second timeout, overridable by `--timeout`.
No command pushes, deploys, or changes the evaluated skill.

Raw outputs, prompts, process logs, exit codes and input hashes stay in the result
directory. A repeated run refuses to overwrite a launch. Use a fresh directory
for a rerun. Normal Codex user and project instructions still apply to child
sessions, so these are not isolated, blind model benchmarks. The slicer can read
the oracle files because its sandbox does not hide them. The prompt does not ask
it to do so. Review tool traces before making a claim of blind evaluation.

## Read the scores

**S1 Format** passes when the validator accepts a matrix (exit 0), or when a case
requiring a stop receives a valid stop file (exit 3). An unexpected stop fails.
The scorer uses the validator's stop contract:

```json
{"stop":true,"reason":"No acceptance target was supplied.","questions":["Which outcome should improve?"],"rule":"vague_acceptance"}
```

The rule is `vague_acceptance`, `contradictory_order`, or `missing_source`.
All four fields are required, with a nonblank reason and at least one nonblank
question. Extra fields, plain text, and legacy `status` objects are invalid.
A missing output never counts as a stop.

**S2 Accuracy** reports every property separately. Types cover counts, required
and forbidden engines, existing-engine reuse, coverage, first-slice behavior,
layers, order, time bounds, and acceptance text. Required engine and text groups
accept listed synonyms after case and punctuation normalization. Text checks are
proxies: a phrase can be present without a sound plan, or a valid paraphrase can
miss an alias. The judge must examine meaning. Historical probes require their
checks to occur in acceptance for the relevant requirement.

**S3 Usefulness** records five fixed yes/no answers and evidence from the judge. The
fifth question is “Is anything important missing?” The brief asks for the raw yes
count, so the table preserves it. A separate favorable count reverses question
five. Four favorable yes answers and one no produce raw 4/5, favorable 5/5.
Neither score should be presented as implementation proof.

No output means unavailable, never a model failure or a zero score. Missing or
malformed judge answers are unavailable. `scores.json` contains all property
results. `summary.md` contains each case, model totals, and proposed changes.

## Cases that test the skill's limits

- F1: Engines marked `existing: true` need at least one uses cell and zero
  builds cells. New engines still require a builder and a separate user.
- F2: The vague plan and mandatory dependency cycle require stopping. A complete
  looking matrix that invents a decision should fail these cases.
- F3: Tiny tasks and non-code work must avoid fabricated engines and layers.
  Wide migrations may use the existing enabling exception, within its cap.

## Outcome expectations under R9

Keep the case prompts unchanged. They deliberately lack an explicit outcomes
array. The model must write `source.outcomes` from the stated goal or observable
results, map every requirement to an outcome, and retain the supplied acceptance
and order constraints. Each slice must name the outcomes it moves in a non-empty
`outcomes` array and share a covered requirement with each named outcome. Each
source outcome must name a `first_proof` slice whose acceptance demonstrates a
thin working path for a real user end to end. The slice must name that outcome.

S1 checks these links through R9. The validator and renderer report "first
working at wave N, complete at wave M" for each outcome and the median
first-working wave across outcomes. Completion uses the last slice naming the
outcome, even when another slice shares a requirement. Timing is informational.
After the walking skeleton, first proofs should arrive as early as their blockers
allow. Aim for the first third of waves, rounding the wave count up, and explain
later first proofs in `source.description`. Review acceptance for real user paths
and check those explanations. The validator cannot establish that meaning.

The local regression suite covers required slice outcomes, unknown IDs, shared
requirements for every named outcome, required first-proof links, and matching
reports in both scripts. Report tests cover odd and even medians, a single
outcome, reversed row order, and late first proofs that remain valid. The named
sabotage target is `test_slice_outcome_must_share_requirement`: disabling only
the shared-requirement check must make it fail. Restore from a copy of the
current file before rerunning the suite.

These are expected meanings, not exact wording or a required grouping:

| Case | Expected outcome or stop behavior |
|---|---|
| 01-website-builder | Owners can save and publish pages with retained media. |
| 02-existing-engine | Users retain profile and cover photos through MediaStore. |
| 03-tiny | Users see the corrected label and can still save an address. |
| 04-wide-migration | Clients keep working during the field rename and approved removal. |
| 05-hidden-cycle | The launch goal does not resolve the mandatory cycle. Keep the `contradictory_order` stop. |
| 06-vague | The stated goal has no approved, testable meaning. Keep the `vague_acceptance` stop. Do not invent outcomes or thresholds. |
| 07-marketing | Three preview channels produce the supplied delivery and tracking evidence. |
| 08-deadline-approval | Filing totals are reviewed, approved, and filed with a receipt by the supplied deadline. |
| 09-personal-learning | The tutor can understand the introduction and meal order against the supplied checks. |
| 10-research | A reader can reproduce both rates and assess the limited turnover evidence. |
| 11-security | Own-family reports remain available while other-family access is denied. |
| 12-horizontal | Users can add, mark, and delete shopping items with retained state. |
| 13-fake-engine | Users can download the invoice and retain an updated phone number. |

If a source supplies neither outcomes nor a goal, the model must write a
`missing_source` stop file with exactly one question asking what outcomes the
plan must achieve. A missing outcomes heading alone is not grounds to stop when
the source already states the intended result. Deriving outcomes must not remove
the stop conditions in cases 05 and 06.

The website-builder fixture is synthetic, inspired by the brief's scenario. It
does not claim to reproduce video 13. The finance deadline is fictional supplied
data. 
Next: run the configured slicers and the judge, inspect
the failed properties and judge reasons, then decide which skill changes to make.
