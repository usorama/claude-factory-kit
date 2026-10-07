# Defect library

Every blocking review finding is filed here by type. The top types go into every brief's Traps.
Builders check their work against each type and report "checked: <how>" or "not relevant: <why>".
This file never grows: a new type replaces the least useful one (the retro decides).

Scope: types 1 and 2 matter only for input a normal user or caller gives. A trick that needs
someone who can already write the repo is out of scope and never blocks.

1. **Path spelling and links.** A path with `..`, a symbolic link, a relative path or a nested repo
   slips past a check. Rule: resolve and normalize every caller path, refuse links, compare with one
   trusted root. Test each spelling.
2. **Check one thing, use another.** A file is read once for the check and again for the use.
   Rule: read once; check and use the same bytes. Test with a reader that changes between reads.
3. **Trusting evidence the checked party writes.** A log, record, model answer or exit code that the
   thing under test controls. Rule: anchor evidence in something it cannot write (committed bytes,
   the tool's own record). Test the forged case.
4. **A check with no test.** A refusal that no test fails without (the guard finds these). Rule:
   one test per check, with the bad input it exists for, asserting the message.
5. **Works only on one machine.** A fixed home path, an OS-only behaviour, a folder missing in a
   fresh copy. Rule: skip with the missing path named; behave the same on Linux, macOS and WSL2.
6. **An error handler that throws away good data.** One bad line resets everything that was read.
   Rule: skip or record the bad part, keep the rest. Test one malformed line among good ones.
7. **A file format change that misses another reader.** Rule: before changing a file's shape,
   search the repo for every program that reads it, and update or test each one.
8. **A fake built from a guess.** Tests pass on invented tool answers and fail on real ones. Rule:
   copy every fake answer from a captured real run and name the run (command, date, machine). With
   no real run yet, make one harmless real run first, or stop and report.
9. **A check the tests do not require.** The builder adds extra validation no named test protects,
   and the guard refuses the build. Rule: write only the checks the unit's tests require; report a
   check that seems missing instead of adding it.
10. **A brief that cites a runtime file by its path.** Runtime files (under `var/`) do not exist in a
    unit's work folder, so the cited-source check refuses the brief. Rule: name runtime files in
    words; cite only files committed in the repo.
