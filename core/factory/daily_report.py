"""One plain report per day, written by code from the factory's own records. No AI touches a number.

Sources: var/factory/log.jsonl, var/factory/ticks.log, var/factory/asks/, .ai/lessons.jsonl.
Usage: daily_report.py [--day YYYY-MM-DD] [--write]   (--write saves var/factory/daily/<day>.md)
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from asks import collect
from common import now, parse_time, read_jsonl, var


def _first(events, step):
    """{unit: first end event of this step}."""
    first = {}
    for event in events:
        if event.get("event") == "end" and event.get("step") == step and event.get("ok") is not None:
            first.setdefault(event["unit"], event)
    return first


def days(root):
    root = Path(root)
    events = read_jsonl(var(root) / "log.jsonl")
    ticks = read_jsonl(var(root) / "ticks.log")
    lessons = read_jsonl(root / ".ai/lessons.jsonl")
    out = defaultdict(lambda: {"landed": [], "first_checks": [], "splits": 0, "hand": [], "idle": Counter(),
                               "ticks": 0, "skipped_ticks": 0, "cost_usd": 0.0, "lessons": [], "decisions": [],
                               "refusals": [], "defects": []})
    enqueued = {e["unit"]: e["at"] for e in events if e.get("event") == "enqueue"}
    for unit, event in _first(events, "check").items():
        out[event["at"][:10]]["first_checks"].append(bool(event["ok"]))
    for event in events:
        day = out[event["at"][:10]]
        if event.get("to") == "landed":
            start = enqueued.get(event["unit"])
            minutes = round((parse_time(event["at"]) - parse_time(start)).total_seconds() / 60) if start else None
            day["landed"].append({"unit": event["unit"], "pr": event.get("pr"), "minutes_to_land": minutes})
        if event.get("event") == "end" and event.get("ok") is False:
            day["refusals"].append({"unit": event["unit"], "step": event["step"], "why": event.get("outcome", "")})
        if event.get("event") == "defect":
            day["defects"].append({"unit": event["unit"], "note": event["note"]})
        if event.get("to") == "needs_split":
            day["splits"] += 1
        if event.get("event") == "hand":
            day["hand"].append({"unit": event["unit"], "reason": event["reason"], "note": event["note"]})
        if isinstance(event.get("cost_usd"), (int, float)):
            day["cost_usd"] += event["cost_usd"]
    for tick in ticks:
        day = out[tick["at"][:10]]
        day["ticks"] += 1
        if tick.get("skipped"):
            day["skipped_ticks"] += 1
        elif tick.get("idle_reason"):
            day["idle"][tick["idle_reason"].split(";")[0]] += 1
    for lesson in lessons:
        out[lesson["at"][:10]]["lessons"].append(lesson["title"])
    for card in collect(root, "human"):
        if card["at"]:
            out[card["at"][:10]]["decisions"].append(card["title"])
    result = []
    for date in sorted(out, reverse=True):
        day = out[date]
        checks = day.pop("first_checks")
        result.append({**day, "date": date, "idle": dict(day["idle"]), "cost_usd": round(day["cost_usd"], 2),
                       "first_try_green": f"{sum(checks)} of {len(checks)}" if checks else "no build checks"})
    return result


def markdown(day):
    lines = [f"# Factory day {day['date']}", "",
             f"- Units landed: {len(day['landed'])}" + "".join(
                 f"\n  - {u['unit']} {u['pr'] or ''} ({u['minutes_to_land']} minutes from queue to landed)"
                 for u in day["landed"]),
             f"- Refusals: {len(day['refusals'])}" + "".join(
                 f"\n  - {r['unit']} at {r['step']}: {r['why']}" for r in day["refusals"]),
             f"- Escaped defects: {len(day['defects'])}" + "".join(f"\n  - {d['unit']}: {d['note']}" for d in day["defects"]),
             f"- First-try green (first build check passed): {day['first_try_green']}",
             f"- Units sent to split: {day['splits']}",
             f"- Hand corrections: {len(day['hand'])}" + "".join(f"\n  - {h['unit']}: {h['reason']}, {h['note']}" for h in day["hand"]),
             f"- Clock ticks: {day['ticks']} (skipped because one was running: {day['skipped_ticks']})",
             "- Idle ticks by reason: " + (", ".join(f"{k} ({v})" for k, v in day["idle"].items()) or "none"),
             f"- Model cost recorded: {day['cost_usd']} US dollars",
             "- Lessons filed: " + ("; ".join(day["lessons"]) or "none"),
             "- Decisions asked of the human: " + ("; ".join(day["decisions"]) or "none"), "",
             f"Written by factory/daily_report.py at {now()}."]
    return "\n".join(lines) + "\n"


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = Path(root or Path.cwd())
    found = [d for d in days(root) if args.day is None or d["date"] == args.day][:1]
    if not found:
        print("no records for that day", file=sys.stderr)
        return 1
    text = markdown(found[0])
    if args.write:
        folder = var(root) / "daily"
        folder.mkdir(exist_ok=True)
        (folder / f"{found[0]['date']}.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
