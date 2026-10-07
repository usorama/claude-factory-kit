"""The factory clock and the orchestrator's queue commands. Run from the repo root.

  tick.py tick                          one clock tick (cron runs this every 5 minutes)
  tick.py worktree <row> <n> [--from REF]   make the unit's work folder on branch unit/<row>/<n>
  tick.py enqueue <unit.json path> <worktree>
  tick.py set <unit.json path> <state> --reason WHY --note TEXT   a logged hand correction
  tick.py status
  tick.py hold <unit.json path> --reason TEXT    stop one unit now: not runnable, its runner ended
  tick.py release <unit.json path> --note TEXT   back to cut, only after the re-cut validates
  tick.py verify-checkout <unit.json path> <folder>   a separate checkout of the landed unit for its sabotage
  tick.py close-row <row>               mark a row done after its crew checks (conformance, claims, surface)
  tick.py prune                         remove work folders and branches of landed and parked units
  tick.py defect <unit.json path> --note TEXT   record an escaped defect found on main
Only one tick runs at a time (tick.lock). A skipped tick is logged, never silent.
"""
import argparse
import json
import os
import re
import socket
import sys
from pathlib import Path

import asks
import drive
from common import (ACTIVE, STOPPED, Lock, config, config_problem, git, label, log, now, paused_until,
                    queue_lock, read_queue, spent_today,
                    unit_row, var, write_queue)
from unit_check import UnitRefused, check_unit

HAND_REASONS = ("cut_defect", "machinery", "split", "rebase", "data_fix", "other")


class Refused(ValueError):
    """The orchestrator's queue command is not allowed."""


def backlog(root):
    """{row id: status} from plan/backlog.md rows '| ID | Status | ...'."""
    path = Path(root) / "plan/backlog.md"
    rows = {}
    for line in path.read_text().splitlines() if path.exists() else []:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", cells[0]) and cells[0] != "ID":
            rows[cells[0]] = cells[1].lower()
    return rows


def backlog_text(root, row):
    path = Path(root) / "plan/backlog.md"
    for line in path.read_text().splitlines() if path.exists() else []:
        if line.strip().strip("|").split("|")[0].strip() == row:
            return line
    raise Refused(f"row {row} is not in plan/backlog.md")


def mark_row(root, row, status):
    """Set a backlog row's status cell (code only: close-row, an evidence-confirmed sweep)."""
    path = Path(root) / "plan/backlog.md"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        cells = line.split("|")
        if len(cells) > 3 and cells[1].strip() == row:
            cells[2] = f" {status} "
            lines[i] = "|".join(cells)
    path.write_text("\n".join(lines) + "\n")


def live_checkout_refusal(root):
    """Enqueue only from the live checkout: a unit work folder has its own copy of the queue files."""
    own = git(root, "rev-parse", "--absolute-git-dir", check=False).stdout.strip()
    common_dir = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False).stdout.strip()
    if own and common_dir and Path(own).resolve() != Path(common_dir).resolve():
        return "this is a unit work folder; run enqueue, hold and release from the live checkout (the main repo folder)"
    return None


def enqueue(root, unit_path, worktree):
    refusal = live_checkout_refusal(root)
    if refusal:
        raise Refused(refusal)
    row, n = unit_row(unit_path)
    try:
        check_unit(Path(worktree) / unit_path)
    except UnitRefused as error:
        raise Refused(str(error)) from error
    data = json.loads((Path(worktree) / unit_path).read_text())
    if (data.get("row"), data.get("n")) != (row, n):
        raise Refused(f"the unit says row {data.get('row')} unit {data.get('n')}, its path says {row} unit {n}")
    status = backlog(root).get(row)
    if status != "building":
        raise Refused(f"row {row} is {status or 'missing'} in plan/backlog.md; mark it building first")
    import crew
    gate = crew.cut_refusal(root, row)
    if gate:
        raise Refused(gate)
    with queue_lock(root):
        queue = read_queue(root)
        if any(e["unit"] == unit_path and e["state"] in ACTIVE for e in queue["units"]):
            raise Refused(f"{unit_path} is already moving in the queue")
        entry = {"unit": unit_path, "worktree": str(Path(worktree).resolve()), "state": "cut",
                 "attempts": 0, "log": [], "enqueued_at": now(), "estimate_minutes": data["estimate_minutes"]}
        queue["units"].append(entry)
        write_queue(root, queue)
    log(root, event="enqueue", unit=unit_path)
    return entry


def set_state(root, unit_path, state, reason, note):
    """A hand correction: logged with its reason, and the unit's stop card closed in the same step."""
    if state not in (*drive.TRANSITIONS, "parked"):
        raise Refused(f"state must be one of {', '.join(drive.TRANSITIONS)} or parked")
    if reason not in HAND_REASONS or not note.strip():
        raise Refused(f"a reason ({', '.join(HAND_REASONS)}) and a note are required")
    with queue_lock(root):
        queue = read_queue(root)
        found = [e for e in queue["units"] if e["unit"] == unit_path and e["state"] != "landed"]
        if not found:
            raise Refused(f"{unit_path} is not in the queue")
        entry = found[-1]
        if entry.get("running"):
            raise Refused(f"{unit_path} is running {entry['running']['step']}; wait for the step to end")
        before = entry["state"]
        entry.update(state=state, attempts=0, cut_finding=False)
        for field in ("last_reject", "retried"):
            entry.pop(field, None)
        entry["log"].append({"step": "orchestrator", "outcome": f"{reason}: {note}", "at": now()})
        write_queue(root, queue)
    log(root, event="hand", unit=unit_path, reason=reason, note=note, state=before, to=state)
    if (asks.folder(root) / f"{label(unit_path)}.md").exists():
        asks.close(root, label(unit_path), f"{reason}: {note}")
    return entry


def make_worktree(root, row, n, start=None):
    name = Path(root).resolve().name
    path = Path(root).resolve().parent / f"{name}-worktrees" / f"{row}-U{n}"
    start = start or f"origin/{config(root)['base']}"
    git(root, "fetch", "-q", "origin", check=False)
    git(root, "worktree", "add", "-q", "-B", f"unit/{row}/{n}", str(path), start)  # -B: a re-cut reuses the name
    return path


def hold_reason(root, cfg):
    """Why model steps (build, review) wait this tick: a usage-limit pause or the daily budget."""
    until = paused_until(root)
    if until:
        return f"usage limit: model steps paused until {until.isoformat()}"
    spent = spent_today(root)
    if spent >= cfg["daily_budget_usd"]:
        card = asks.folder(root) / f"DEC-budget-{now()[:10]}.md"
        if not card.exists() and not (asks.folder(root) / "answered" / card.name).exists():
            asks.decide(root, f"budget-{now()[:10]}", f"Daily model budget reached ({spent} of "
                        f"{cfg['daily_budget_usd']} US dollars). Raise it for today?",
                        "No; builds and reviews continue tomorrow. Checks and landings go on today.")
        return f"daily budget reached: {spent} of {cfg['daily_budget_usd']} US dollars"
    return None


def refusal(root, cfg):
    """A reason this host must not run the clock at all, or None."""
    host = socket.gethostname()
    if cfg["clock_host"] and cfg["clock_host"] != host:
        return f"this host ({host}) is not the clock host ({cfg['clock_host']}); one clock per repo"
    problem = config_problem(cfg, root)
    if problem:
        return problem
    if git(root, "fetch", "-q", "origin", cfg["base"], check=False).returncode != 0:
        return f"cannot fetch origin/{cfg['base']}; nothing moves until it works"
    return None


def tick_line(root, line):
    with (var(root) / "ticks.log").open("a") as stream:
        stream.write(json.dumps({"at": now(), **line}) + "\n")
    return {"at": now(), **line}


def tick_once(root, runners=None):
    root = Path(root)
    cfg = config(root)
    try:
        lock = Lock(var(root) / "tick.lock", wait=0).__enter__()
    except TimeoutError:
        return tick_line(root, {"skipped": "tick already running"})
    try:
        stop = refusal(root, cfg)
        if stop:
            return tick_line(root, {"skipped": stop})
        runners_are_real = runners is None
        if runners is None:
            from runners import make_runners
            runners = make_runners(root)
        hold = hold_reason(root, cfg)
        counts = drive.tick(root, runners, hold_models=hold)
        if not hold and runners_are_real:
            counts["triaged"] = triage_next(root)
        cards = 0
        units = read_queue(root)["units"]
        for entry in units:
            if entry["state"] in STOPPED:
                cards += asks.write_unit_card(root, entry)
        idle = hold if counts["held"] else None
        if not any(e["state"] in ACTIVE + ("pr_open",) for e in units):
            stopped = sum(e["state"] in STOPPED for e in units)
            idle = (f"only stopped units ({stopped}); the orchestrator must handle their cards" if stopped
                    else "queue empty; the orchestrator must cut units")
        return tick_line(root, {**counts, "cards_written": cards, "idle_reason": idle})
    finally:
        lock.__exit__()


def triage_next(root):
    """Sorter Sam on the first todo or building row with no triage record (one per tick)."""
    import crew
    for row, status in backlog(root).items():
        if status in ("todo", "building") and crew.latest(root, "sorter-sam", row) is None:
            try:
                crew.run_agent(root, "sorter-sam", "row_untriaged", row, {"row": row, "text": backlog_text(root, row)})
            except Exception as error:  # a crew failure never stops the clock; it is recorded
                log(root, event="crew", agent="sorter-sam", subject=row, ok=False, note=str(error)[:300])
            return row
    return None


def close_row(root, row):
    """Mark a row done only after its units all landed and the crew's row_landed checks pass."""
    import crew
    units = [e for e in read_queue(root)["units"] if unit_row(e["unit"])[0] == row]
    if not units or any(e["state"] != "landed" for e in units):
        raise Refused(f"{row} has units that have not landed")
    files = sorted({f for e in units for f in crew.load_files(root, e)})
    prs = ", ".join(str(e.get("pr", "")).rsplit("/", 1)[-1] for e in units)
    context = {"row": row, "text": backlog_text(root, row), "units": [e["unit"] for e in units], "files": files,
               "prs": prs, "claim": f"Row {row} is done: {len(units)} unit(s) landed as pull requests {prs}."}
    for name in crew.triggered("row_landed", context):
        data, verdict = crew.run_agent(root, name, "row_landed", row, dict(context, unit_files=files))
        if verdict in ("deviates", "mismatch", "REJECT"):
            raise Refused(f"{name} blocks closing {row}: {verdict}")
    mark_row(root, row, f"done (PRs {prs})")
    log(root, event="row_done", row=row, prs=prs)
    return {"row": row, "done": True, "prs": prs}


def find_entry(queue, unit_path):
    found = [e for e in queue["units"] if e["unit"] == unit_path and e["state"] not in ("landed", "parked")]
    if not found:
        raise Refused(f"{unit_path} is not in the queue (or already landed or parked)")
    return found[-1]


def hold(root, unit_path, reason, wait=3600.0):
    """Stop one unit: mark it not runnable at once, end its running model process, then wait for the
    running tick to finish (the whole-tick lock). The killed step's own save cannot clear the hold."""
    import signal
    refusal = live_checkout_refusal(root)
    if refusal or not reason.strip():
        raise Refused(refusal or "a reason is required")
    with queue_lock(root):
        queue = read_queue(root)
        entry = find_entry(queue, unit_path)
        entry["hold"] = {"reason": reason, "at": now()}
        write_queue(root, queue)
    pidfile = var(root) / "pids" / f"{label(unit_path)}.pid"
    killed = None
    if pidfile.exists():
        try:
            killed = int(pidfile.read_text())
            os.killpg(killed, signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            killed = None
    with Lock(var(root) / "tick.lock", wait=wait):
        with queue_lock(root):
            entry = find_entry(read_queue(root), unit_path)
    if not entry.get("hold"):
        raise Refused(f"the hold on {unit_path} did not survive; report this as a bug")
    log(root, event="hand", unit=unit_path, reason="hold", note=reason, state=entry["state"], to="held")
    return {"unit": unit_path, "held": True, "state": entry["state"], "runner_ended": killed}


def release(root, unit_path, note, wait=3600.0):
    """Return a held unit to cut only after its re-cut validates (shape, brief, red tests)."""
    from red_check import red_check, tolerated_tests
    refusal = live_checkout_refusal(root)
    if refusal or not note.strip():
        raise Refused(refusal or "a note is required")
    with Lock(var(root) / "tick.lock", wait=wait):
        with queue_lock(root):
            entry = find_entry(read_queue(root), unit_path)
        if not entry.get("hold"):
            raise Refused(f"{unit_path} is not held")
        try:
            check_unit(Path(entry["worktree"]) / unit_path)
            red_check(unit_path, entry["worktree"], tolerated_tests(root, entry))
        except ValueError as error:
            raise Refused(f"the re-cut does not validate, the unit stays held: {error}") from error
        head = git(entry["worktree"], "rev-parse", "HEAD").stdout.strip()
        with queue_lock(root):
            queue = read_queue(root)
            entry = find_entry(queue, unit_path)
            for field in ("hold", "last_reject", "retried", "reviewed_patch", "cut_finding", "built_from", "model_minutes"):
                entry.pop(field, None)
            entry.update(state="cut", attempts=0, retries=0, cut_commit=head)
            entry["log"].append({"step": "orchestrator", "outcome": f"released after a validated re-cut: {note}", "at": now()})
            write_queue(root, queue)
    log(root, event="hand", unit=unit_path, reason="hold", note=f"released: {note}", state="held", to="cut")
    if (asks.folder(root) / f"{label(unit_path)}.md").exists():
        asks.close(root, label(unit_path), f"released: {note}")
    return {"unit": unit_path, "released": True, "cut_commit": head}


def verify_checkout(root, unit_path, folder):
    """A separate detached checkout of main containing the landed unit, with its named tests run there.
    Sabotage only in this copy, never in the live checkout the clock uses."""
    entry = next((e for e in read_queue(root)["units"] if e["unit"] == unit_path and e["state"] == "landed"), None)
    if entry is None:
        raise Refused(f"{unit_path} has not landed")
    git(root, "fetch", "-q", "origin", config(root)["base"], check=False)
    git(root, "worktree", "add", "-q", "--detach", str(folder), f"origin/{config(root)['base']}")
    unit = json.loads((Path(folder) / unit_path).read_text())
    from testrun import run
    _, records, _, _ = run(folder, unit["tests"])
    return {"checkout": str(folder), "named_tests": {t: records.get(t, {}).get("outcome") for t in unit["tests"]},
            "next": "apply the named sabotage in this checkout only, see the test go red, then remove it: "
                    f"git worktree remove --force {folder}"}


def prune(root):
    """Remove the work folders and local branches of landed and parked units."""
    removed = []
    for entry in read_queue(root)["units"]:
        if entry["state"] in ("landed", "parked") and Path(entry["worktree"]).exists():
            branch = git(entry["worktree"], "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            git(root, "worktree", "remove", "--force", entry["worktree"], check=False)
            git(root, "branch", "-D", branch, check=False)
            removed.append(entry["worktree"])
    git(root, "worktree", "prune", check=False)
    return removed


def defect(root, unit_path, note):
    """Record an escaped defect: a fault found on main in a unit that had landed."""
    if not any(e["unit"] == unit_path and e["state"] == "landed" for e in read_queue(root)["units"]):
        raise Refused(f"{unit_path} has not landed; an escaped defect belongs to a landed unit")
    log(root, event="defect", unit=unit_path, note=note)
    return {"unit": unit_path, "note": note}


def main(argv=None, root=None):
    root = Path(root or Path.cwd())
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tick")
    sub.add_parser("status")
    sub.add_parser("prune")
    closing = sub.add_parser("close-row")
    closing.add_argument("row")
    for name in ("hold", "release"):
        stop = sub.add_parser(name)
        stop.add_argument("unit")
        stop.add_argument("--reason" if name == "hold" else "--note", required=True, dest="text")
    checkout = sub.add_parser("verify-checkout")
    checkout.add_argument("unit")
    checkout.add_argument("folder")
    escaped = sub.add_parser("defect")
    escaped.add_argument("unit")
    escaped.add_argument("--note", required=True)
    tree = sub.add_parser("worktree")
    tree.add_argument("row")
    tree.add_argument("n", type=int)
    tree.add_argument("--from", dest="start")
    add = sub.add_parser("enqueue")
    add.add_argument("unit")
    add.add_argument("worktree")
    change = sub.add_parser("set")
    change.add_argument("unit")
    change.add_argument("state")
    change.add_argument("--reason", required=True)
    change.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "tick":
            result = tick_once(root)
        elif args.command == "worktree":
            result = str(make_worktree(root, args.row, args.n, args.start))
        elif args.command == "enqueue":
            result = enqueue(root, args.unit, args.worktree)
        elif args.command == "prune":
            result = prune(root)
        elif args.command == "hold":
            result = hold(root, args.unit, args.text)
        elif args.command == "release":
            result = release(root, args.unit, args.text)
        elif args.command == "verify-checkout":
            result = verify_checkout(root, args.unit, args.folder)
        elif args.command == "close-row":
            result = close_row(root, args.row)
        elif args.command == "defect":
            result = defect(root, args.unit, args.note)
        elif args.command == "set":
            result = set_state(root, args.unit, args.state, args.reason, args.note)
        else:
            result = [{"unit": e["unit"], "state": e["state"], "running": e.get("running"),
                       "attempts": e["attempts"]} for e in read_queue(root)["units"]]
    except (Refused, ValueError) as error:
        print(f"{args.command} refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1) if not isinstance(result, str) else result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
