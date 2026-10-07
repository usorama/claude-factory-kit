"""Find records that disagree, and anything stale. Reads files only, so the same files give the same report.

Findings (each names its fix):
  clock_stale            the last tick is older than clock_stale_minutes
  ticks_skipped          the last three ticks were skipped (toolchain, clock host, fetch, settings)
  toolchain_patch_changed a pinned tool changed its patch version (auto-update); a warning
  step_stuck             a step has been running longer than its time limit plus ten minutes
  stopped_without_card   a stopped unit has no open stop card
  stale_card             an open stop card for a unit that is moving again or landed
  row_not_building       a unit moves while its backlog row is not 'building'
  row_all_landed         every unit of a building row landed, and the row is still 'building'
  queue_short            a row is building and fewer than queue_floor units can move
  position_unreadable    state.md has no 'Updated YYYY-MM-DD HH:MM UTC.' line in its Position block
  position_behind        a unit landed or was corrected by hand after the Position block was written
  kit_outdated           the project's factory/ copy is older than the kit installed here (factory init --apply --update)
  plan_invalid           plan/slice-matrix.json fails the plan check (rows over 8 h, one layer, no yes/no check, ...)
Usage: consistency.py [--now ISO]     |     consistency.py --staged   (commit hook: Position time vs clock)
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from asks import collect
from common import ACTIVE, STOPPED, config, label, parse_time, read_jsonl, read_queue, unit_row, var
from tick import backlog

UPDATED = re.compile(r"^Updated (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (UTC|[+-]\d{2}:\d{2})\.$", re.MULTILINE)


def position_time(text):
    block = text.split("## Position", 1)[1].split("\n## ", 1)[0] if "## Position" in text else ""
    match = UPDATED.search(block)
    if not match:
        raise ValueError("state.md Position block needs a line 'Updated YYYY-MM-DD HH:MM UTC.'")
    zone = "+00:00" if match.group(2) == "UTC" else match.group(2)
    return datetime.fromisoformat(f"{match.group(1).replace(' ', 'T')}{zone}")


def version_tuple(text):
    return tuple(int(n) for n in re.findall(r"\d+", str(text))[:3]) or (0,)


def installed_kit_version(root):
    """The newest kit version on this machine: the kit checkout recorded at init (factory/KIT) and any installed
    Claude Code plugin named factory. None when neither can be read."""
    found = []
    kit = Path(root) / "factory/KIT"
    if kit.exists():
        version = Path(kit.read_text().strip()) / "VERSION"
        if version.exists():
            found.append(version.read_text().strip())
    plugins = Path.home() / ".claude/plugins/installed_plugins.json"
    if plugins.exists():
        try:
            for name, installs in json.loads(plugins.read_text()).get("plugins", {}).items():
                if name.split("@")[0] == "factory":
                    found += [i.get("version", "") for i in installs if i.get("version")]
        except ValueError:
            pass
    return max(found, key=version_tuple) if found else None


def kit_outdated(root):
    """(project version, newer kit version) when the project's factory/ copy is behind the installed kit."""
    mine = Path(root) / "factory/VERSION"
    newest = installed_kit_version(root)
    if mine.exists() and newest and version_tuple(newest) > version_tuple(mine.read_text().strip()):
        return mine.read_text().strip(), newest
    return None


def plan_problem(matrix):
    """The first line of the plan checker's complaint, or None when the plan passes (exit 0)."""
    here = Path(__file__).resolve().parent
    validator = here / "planning/validate_matrix.py"
    if not validator.exists():  # running from the kit itself, not a project
        validator = here.parent / "planning/slice-matrix/scripts/validate_matrix.py"
    checked = subprocess.run([sys.executable, str(validator), str(matrix)], capture_output=True, text=True)
    if checked.returncode == 0:
        return None
    return ((checked.stdout + checked.stderr).strip().splitlines() or [f"exit {checked.returncode}"])[0][:300]


def check(root, clock=None):
    root, cfg = Path(root), config(root)
    clock = clock or datetime.now(timezone.utc)
    findings = []

    def find(code, subject, text, fix):
        findings.append({"code": code, "subject": subject, "text": text, "fix": fix})

    ticks = read_jsonl(var(root) / "ticks.log")
    if ticks and clock - parse_time(ticks[-1]["at"]) > timedelta(minutes=cfg["clock_stale_minutes"]):
        find("clock_stale", "clock", f"The last tick was at {ticks[-1]['at']}.",
             "Check cron (crontab -l) and the tick output file; run factory/tick.sh by hand once.")
    if len(ticks) >= 3 and all(t.get("skipped") for t in ticks[-3:]):
        find("ticks_skipped", "clock", f"The last three ticks were skipped: {ticks[-1]['skipped']}.",
             "Fix the cause named (toolchain pin, clock host, fetch, settings), then run factory/tick.sh once.")
    seen = var(root) / "toolchain-seen.json"
    if seen.exists():
        warnings = json.loads(seen.read_text()).get("warnings", [])
        if warnings:
            find("toolchain_patch_changed", "toolchain", "; ".join(warnings),
                 "A tool updated itself. Check one unit still works, then update factory/toolchain.json.")
    units = read_queue(root)["units"]
    cards = {c["id"]: c for c in collect(root) if not c["answered"]}
    rows = backlog(root)
    limit = max(cfg["build_timeout_minutes"], cfg["review_timeout_minutes"]) + 10
    by_row = {}
    for entry in units:
        name, state = label(entry["unit"]), entry["state"]
        by_row.setdefault(unit_row(entry["unit"])[0], []).append(state)
        running = entry.get("running")
        if running and clock - parse_time(running["since"]) > timedelta(minutes=limit):
            find("step_stuck", name, f"{name} has been in step {running['step']} since {running['since']}.",
                 "Look at the tick output; if the tick died, the next tick reruns the step.")
        if state in STOPPED and name not in cards:
            find("stopped_without_card", name, f"{name} is {state} with no open card.",
                 "Run one tick (it writes the card), or handle the unit with tick.py set.")
        if (state in ACTIVE or state == "landed") and name in cards and cards[name]["kind"] == "unit-stop":
            find("stale_card", name, f"The stop card for {name} is open, but the unit is {state}.",
                 f"python3 factory/asks.py close {name} --answer '<what was done>'")
    for row, states in sorted(by_row.items()):
        moving = [s for s in states if s in ACTIVE]
        if moving and rows.get(row) != "building":
            find("row_not_building", row, f"{row} has moving units but is {rows.get(row, 'missing')} in the backlog.",
                 "Mark the row building in plan/backlog.md, or stop its units.")
        if rows.get(row) == "building" and states and all(s == "landed" for s in states):
            find("row_all_landed", row, f"All units of {row} landed; the row is still building.",
                 "Cut its next unit, or mark the row done with its pull requests.")
    moving_total = sum(e["state"] in ACTIVE for e in units)
    building = sorted(r for r, s in rows.items() if s == "building")
    if building and moving_total < cfg["queue_floor"]:
        find("queue_short", "queue", f"{moving_total} unit(s) can move while {', '.join(building)} is building.",
             f"Cut units ahead: keep at least {cfg['queue_floor']} in the queue before going idle.")
    behind = kit_outdated(root)
    if behind:
        find("kit_outdated", "factory/", f"This project runs factory {behind[0]}; the kit installed here is {behind[1]}. "
             "Its fixes do not reach the project by themselves.", "Run: factory init --apply --update")
    matrix = root / "plan/slice-matrix.json"
    if matrix.exists():
        problem = plan_problem(matrix)
        if problem:
            find("plan_invalid", "plan/slice-matrix.json", problem,
                 "Fix every rule the plan check names until python3 factory/planning/validate_matrix.py exits 0.")
    state_md = root / "state.md"
    if state_md.exists():
        try:
            written = position_time(state_md.read_text())
            events = [e for e in read_jsonl(var(root) / "log.jsonl")
                      if e.get("to") == "landed" or e.get("event") == "hand"]
            last = parse_time(events[-1]["at"]).replace(second=0, microsecond=0) if events else None
            if last and last > written:  # the Updated line has minutes only
                find("position_behind", "state.md", f"Something changed at {events[-1]['at']}, after the Position block.",
                     "Update the Position block in state.md (run date -u for the time).")
        except ValueError as error:
            find("position_unreadable", "state.md", str(error), "Write the Updated line with the real clock time.")
    return {"findings": findings, "decisions_open": sum(c["for"] == "human" for c in cards.values()),
            "unit_cards_open": sum(c["for"] == "orchestrator" for c in cards.values())}


def staged_position(root, clock=None, window=10):
    """Commit hook: a staged state.md must carry the real clock time, within `window` minutes."""
    names = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=root, capture_output=True, text=True).stdout
    if "state.md" not in names.split():
        return None
    text = subprocess.run(["git", "show", ":state.md"], cwd=root, capture_output=True, text=True).stdout
    written = position_time(text)
    clock = clock or datetime.now(timezone.utc)
    if abs(clock - written) > timedelta(minutes=window):
        return f"Position time {written.isoformat()} is not the clock time {clock.isoformat(timespec='minutes')}"
    return None


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--now")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args(argv)
    root = root or Path.cwd()
    clock = parse_time(args.now) if args.now else None
    if args.staged:
        try:
            problem = staged_position(root, clock)
        except ValueError as error:
            problem = str(error)
        if problem:
            print(f"position time: {problem}; run date -u and write that time", file=sys.stderr)
        return 1 if problem else 0
    report = check(root, clock)
    print(json.dumps(report, indent=1))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
