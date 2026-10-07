"""The lessons ledger .ai/lessons.jsonl, kept by code: strikes, the two-strikes rule, the daily cap.

  lessons.py add <id> --title T --lesson L --shape check|rule [--measure "metric name"]
  lessons.py strike <id> [--date YYYY-MM-DD]   add a strike; two within seven days -> status ready
  lessons.py apply <id> --by TEXT               mark applied; refused past two changes in one day
  lessons.py ready                              lessons that earned a change
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from common import now, read_jsonl

WINDOW_DAYS, STRIKES_NEEDED, CHANGES_PER_DAY = 7, 2, 2


class LessonRefused(ValueError):
    """The ledger change breaks the two-strikes rule or the daily cap."""


def path(root):
    return Path(root) / ".ai/lessons.jsonl"


def save(root, lessons):
    path(root).parent.mkdir(parents=True, exist_ok=True)
    path(root).write_text("".join(json.dumps(item) + "\n" for item in lessons))


def find(lessons, ident):
    for item in lessons:
        if item["id"] == ident:
            return item
    raise LessonRefused(f"no lesson {ident}")


def is_ready(item, today):
    recent = [d for d in item.get("strikes", []) if date.fromisoformat(d) > today - timedelta(days=WINDOW_DAYS)]
    return len(recent) >= STRIKES_NEEDED


def strike(root, ident, day=None):
    lessons = read_jsonl(path(root))
    item = find(lessons, ident)
    day = day or now()[:10]
    item.setdefault("strikes", []).append(day)
    if item.get("status", "open") == "open" and is_ready(item, date.fromisoformat(day)):
        item["status"] = "ready"
    save(root, lessons)
    return item


def apply(root, ident, by, day=None):
    lessons = read_jsonl(path(root))
    item = find(lessons, ident)
    day = day or now()[:10]
    if item.get("status") != "ready":
        raise LessonRefused(f"{ident} is {item.get('status', 'open')}; a change needs {STRIKES_NEEDED} strikes "
                            f"within {WINDOW_DAYS} days")
    if sum(i.get("applied_on") == day for i in lessons) >= CHANGES_PER_DAY:
        raise LessonRefused(f"already {CHANGES_PER_DAY} changes on {day}; this one waits for tomorrow")
    item.update(status="applied", applied_by=by, applied_on=day)
    save(root, lessons)
    return item


def main(argv=None, root=None):
    root = root or Path.cwd()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("ident")
    add.add_argument("--title", required=True)
    add.add_argument("--lesson", required=True)
    add.add_argument("--shape", choices=("check", "rule"), required=True)
    add.add_argument("--measure", default="")
    hit = sub.add_parser("strike")
    hit.add_argument("ident")
    hit.add_argument("--date")
    done = sub.add_parser("apply")
    done.add_argument("ident")
    done.add_argument("--by", required=True)
    sub.add_parser("ready")
    args = parser.parse_args(argv)
    try:
        if args.command == "add":
            lessons = read_jsonl(path(root))
            if any(i["id"] == args.ident for i in lessons):
                raise LessonRefused(f"lesson {args.ident} exists")
            item = {"id": args.ident, "at": now(), "title": args.title, "lesson": args.lesson,
                    "shape": args.shape, "measure": args.measure, "strikes": [], "status": "open"}
            save(root, lessons + [item])
            result = item
        elif args.command == "strike":
            result = strike(root, args.ident, args.date)
        elif args.command == "apply":
            result = apply(root, args.ident, args.by)
        else:
            result = [i for i in read_jsonl(path(root)) if i.get("status") == "ready"]
    except LessonRefused as error:
        print(f"lessons: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
