# Chief of Staff jobs: tick, cut, verify, stop, review, close, retro, report, handoff

`factory` below is the kit CLI (`python3 <kit>/core/cli.py`, or the harness command that wraps it). Run every step
from the live checkout (the main repo folder) unless a step names another folder.

## tick (every loop iteration)
0. **First tick after a restart** (the newest line of var/factory/restart.log is newer than your session): read the
   newest note in var/factory/handoff/ and the end of var/factory/restart.log. Restart the agents the note lists as
   running, with the commands it gives. Report the harness version the log names and anything the note left open.
1. Read the state.md Position block, `python3 factory/tick.py status` and `tail -50 var/factory/tick.err`.
2. **Landed units:** for each unit landed since the last tick, job `verify <unit>`.
3. **Stopped units:** read the reason, then re-cut, split or reset with
   `python3 factory/tick.py set <unit> <state> --reason <cut_defect|machinery|split|rebase|data_fix|other> --note "<why>"`
   (it closes the unit's card). A decision card (DEC) named DEC-roles means a pinned model stopped answering. It is the human's: never switch models.
4. **Fill the lanes:** while fewer units move than `lanes` and a ready row exists, job `cut`.
5. **Rows:** when every unit of a row has landed, job `close <row>`.
6. **Cards:** `factory dashboard` (it recomputes the numbers; publish the page only when its last line says
   "publish: allowed"), then `python3 factory/asks.py notify-text`. If it prints
   decision cards, send that text with your notification tool; only decisions are ever pushed, never unit stops.
7. **Retro:** if it is past `retro_time` and `var/factory/daily/<today>.md` does not exist, job `retro`.
8. Fix every `python3 factory/consistency.py` finding, update the Position block if anything changed, commit, push.

## cut <row>
1. **Research gate:** a row about an outside tool starts with a reviewed research unit; a missing cited source stops
   the row as a DEC- card.
2. **Before cut:** `factory crew before-cut <row>` (Sweeper Sid, then the plan coverage auditor). A dropped deliverable
   blocks the cut; an already-done row is closed by code after it re-runs the evidence.
3. **Size:** a 1-2 file obvious change is one unit. Otherwise each unit is one observable behaviour in a paragraph under
   100 words with one named sabotage, 3-5 red tests, at most 3 code files, a named seam, one out-of-scope line, an
   estimate of at most 120 minutes. A unit that fails twice is split, never patched a third time.
4. **Folder:** `python3 factory/tick.py worktree <row> <n>`; write the unit file, the red tests and (optionally) the brief
   `.ai/specs/<row>-U<n>.md` there. Without a brief, Quill writes it on the clock.
5. **Check before the clock sees it:** in the unit folder, `python3 factory/unit_check.py .ai/units/<row>/<n>.json`
   and `python3 factory/red_check.py .ai/units/<row>/<n>.json`. The mutation guard runs after the build, on the clock.
6. Commit on the unit branch. **Go back to the live checkout** and enqueue there with
   `python3 factory/tick.py enqueue .ai/units/<row>/<n>.json <unit folder>`. Enqueue refuses inside a unit folder.

## verify <unit>
Never sabotage the live checkout: the clock may be running in it.
1. `python3 factory/tick.py verify-checkout <unit>`: a separate checkout (under var/factory/scratch) of main with the unit landed;
   it runs the named tests there.
2. In that folder only: apply the brief's named sabotage, see the named test go red, restore, see it green.
3. Remove the folder (`git worktree remove --force <folder>`) and record the result in state.md. A failed re-run is a
   stop: `python3 factory/tick.py defect <unit> --note "<what>"`, a backlog row, and tell the human.

## stop <unit>
1. `python3 factory/tick.py hold <unit> --reason "<why>"` from the live checkout. It marks the unit not runnable at
   once, ends its running model process, and returns after the running tick finished. The killed step's result is void.
2. Re-cut in the unit's own folder (reset it to the cut commit if the builder left changes), commit.
3. `python3 factory/tick.py release <unit> --note "<what changed>"`. It returns the unit to cut only after the re-cut
   validates (shape, brief, red tests); otherwise it stays held.
**Emergency only** (a process doing harm), in this order: comment out the clock line (`crontab -e`, or unload the
launchd job), `factory/tick.py hold` every moving unit (it ends their processes at once), confirm
`pgrep -af "[t]ick.py tick"` prints nothing, keep the clock paused, tell the human, record it in state.md.

## review <pr>
For a change that did not go through the clock's review step (a hand fix, a row-level pull request):
1. Fix the exact commit: `gh pr view <pr> --json headRefOid`.
2. Put it through code: check out that commit in a unit folder, enqueue it as a unit in state `checked` with
   `python3 factory/tick.py set <unit> checked --reason other --note "review of <pr> at <sha>"`. The clock runs the pinned
   reviewer (a different model, or a fresh session with a different prompt), plus Lockjaw or Thomasina on their triggers.
   The reviewer gets the brief and the diff, never the builder's report.
3. Only a complete high finding naming an acceptance line blocks; every note becomes a backlog row (code files them).

## close <row>
`python3 factory/tick.py close-row <row>`: code runs the spec conformance auditor, Thomasina on a user-facing surface
and the claim verifier, and marks the row done with its pull requests. Then update Position, commit and push the
backlog with state.md together, before the tick's card step.

## retro (daily, at retro_time)
`factory retro` (daily report, the claim verifier on it, the Bookie's scorecard, lessons that earned a change).
Then: strike lessons (`python3 factory/lessons.py strike <id>`), shape each ready one into a check (a unit with red
tests) or one replaced rule line, apply at most two (`lessons.py apply`), file every gap as its own [Quality] or
[Velocity] backlog row. The daily report file marks the retro done for the day.

## report
The daily report plus your outcome line: what landed (verified), what stopped and why, hand corrections, cost, open
decisions. Plain words, outcome first. `factory dashboard` passes the staleness gate before any publish.

## handoff (before a restart, or when the person asks)
Write var/factory/handoff/<universal time, for example 2026-10-07T10-30>.md: the Position block, the units in flight, every agent or
session you started that is still running and the exact command that restarts it, open decisions, and what you were
about to do. Commit and push any tracked change. Then tell the person: "Ready to restart: run `factory restart`
yourself." Never run `factory restart` or `factory approve` yourself; only a person does.
