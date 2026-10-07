# Principles

Each principle is here because breaking it cost real time. The exact rules are in `RULES.md`.

1. **Outcome first.** Every report, card and page starts with what happened and what it means. Plain words, short
   sentences, full file paths. The reader may read English as a second language.
2. **Code decides anything computable.** Size limits, test results, file lists, verdicts, merges, model choice, which
   agent runs when, and every number on the dashboard are decided by programs. A model answers only what needs
   judgement, and its answer is a form that code checks.
3. **Plan from outcomes, in thin vertical rows.** Each row is a tracer bullet through every layer it needs, at most a
   day's focused work, with a yes/no check. Shared engines are found by looking across features and built once.
4. **Size at cut time, small.** One behaviour, three to five failing tests, at most three code files, a named seam,
   an estimate of at most two hours. Five-hour work items could never reach tens of pull requests a day; size each
   row when it is reached instead of re-planning everything.
5. **One fix round, then split.** A refused unit gets one rebuild with the exact finding, by a fresh session. A second
   refusal, or twice the estimate, means the unit is too big or unclear: cut it smaller. There is no round three.
6. **Only an acceptance line can block.** A review rejects only on a complete high finding about the unit's own
   promise; everything else becomes a backlog row automatically and never holds the line.
7. **Independent review.** A different model reviews when one is available; otherwise a fresh session with a
   different prompt, marked weaker. The reviewer never sees the builder's report and runs the sabotage itself.
8. **Pinned, probed models; no silent fallback.** Exact model IDs that answered on this machine, never an alias. A
   model that stops answering stops the work and asks a person.
9. **Deterministic gates, one host.** Same inputs, same result: one pinned toolchain, one clock host, scrubbed test runs.
10. **No black box, nothing stale.** Every step logs start and end; every stop, idle tick, hand correction, crew
    verdict and estimate-against-actual shows on the dashboard; a page older than its sources is refused.
11. **Ask the human only for** money, accounts and passwords, production, messages to real people, a model change,
    and real product choices. Decide everything else and report it. Unit stops are the chief of staff's work.
12. **Research before outside tools; fakes from real runs.** An outside tool starts with a reviewed research unit;
    a missing cited source stops the cut. A fake answer in a test is copied from a captured real run.
13. **The plan must feed every lane.** Measure the ready-queue width; idle builders are a planning failure.
14. **Improve slowly, by evidence.** A mistake seen twice in seven days earns one change, at most two a day; a
    mechanical mistake becomes a check, a judgement mistake one replaced rule line. Process tooling only after the
    same failure is measured twice. Proven lessons are promoted to the shared kit by pull request.
