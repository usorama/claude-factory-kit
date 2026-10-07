---
name: review-a-unit
description: Verify a factory claim by hand - re-run a unit's named test and named sabotage, or start a fresh independent review outside the clock. Use before marking a row done, and whenever an agent's claim matters.
---

Never trust a report; re-run its proof.

1. In the unit's work folder, run the named test: `python3 -m pytest -q <named test>`. It must pass.
2. Do the named sabotage on a copy, never in /tmp (on a shared machine others can read it). A landed unit:
   `python3 factory/tick.py verify-checkout <unit>` makes the copy under var/factory/scratch. A unit still in its work
   folder: copy that folder to `<repo>/var/factory/scratch/sabotage-<unit>`. In the copy, break the code exactly as the
   brief says and run the named test: it must fail. Remove the copy.
3. For a second independent review, never start a reviewer yourself and never pick a model: send the unit back to
   review with `python3 factory/tick.py set <unit> checked --reason other --note "second review: <why>"`. The clock
   runs the pinned reviewer (and Lockjaw or Thomasina when their triggers match).
4. Read the new form in var/factory/reviews/ once the clock has run it.
5. Record what you ran and the exit codes in `state.md`. A hand review that changes the queue is a
   hand correction: `tick.py set ... --reason other --note "<what>"`.
