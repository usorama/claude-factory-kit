"""Ask cards in var/factory/asks/ (answered ones move to asks/answered/).

Two kinds, never mixed:
- unit-stop  <row>-U<n>.md, For: orchestrator. Written by the clock when a unit stops. The
             orchestrator handles it (reset, rebuild, split, re-cut) and closes it in the same step.
             It is NEVER pushed to the human.
- decision   DEC-<id>.md, For: human. Only for money, accounts or passwords, production, messages
             to real people, or a real product choice. One question, with a recommendation.
Usage:
  asks.py list [--for human|orchestrator]
  asks.py decide <id> --question TEXT --recommend TEXT
  asks.py close <id> --answer TEXT
  asks.py notify-text           one line for a phone push: human decisions only, or nothing
"""
import argparse
import json
import re
import sys
from pathlib import Path

from common import label, now, var


def folder(root):
    path = var(root) / "asks"
    (path / "answered").mkdir(parents=True, exist_ok=True)
    return path


def write_unit_card(root, entry):
    """Write a stop card unless one is open, or this same stop was already answered."""
    name = label(entry["unit"])
    last = entry["log"][-1] if entry["log"] else {"step": "?", "outcome": "?", "at": now()}
    path = folder(root) / f"{name}.md"
    answered = folder(root) / "answered" / f"{name}.md"
    if path.exists() or (answered.exists() and f"At: {last['at']}" in answered.read_text()):
        return False
    path.write_text(f"# {name} stopped: {entry['state']}\n\nFor: orchestrator\nKind: unit-stop\n"
                    f"State: {entry['state']}\nStep: {last['step']}\nAt: {last['at']}\n"
                    f"Outcome: {str(last['outcome']).splitlines()[0][:500] if last['outcome'] else ''}\n\n"
                    "The orchestrator handles this (reset, rebuild, split or re-cut) and closes this card. "
                    "The human is not asked.\n")
    return True


def decide(root, ident, question, recommend):
    if not re.fullmatch(r"[A-Za-z0-9-]+", ident):
        raise ValueError("a decision id uses letters, digits and dashes only")
    path = folder(root) / f"DEC-{ident}.md"
    path.write_text(f"# {question}\n\nFor: human\nKind: decision\nAsked: {now()}\n"
                    f"Recommendation: {recommend}\nReply: approve DEC-{ident} or reject DEC-{ident}\n")
    return path


def close(root, ident, answer):
    path = folder(root) / f"{ident}.md"
    if not path.exists():
        raise ValueError(f"no open card {ident}")
    target = folder(root) / "answered" / path.name
    target.write_text(path.read_text() + f"\nAnswer: {answer}\nAnswered: {now()}\n")
    path.unlink()
    return target


def read_card(path, answered):
    text = path.read_text()
    fields = dict(re.findall(r"^([A-Z][A-Za-z]+): (.*)$", text, re.MULTILINE))
    title = next((line[2:] for line in text.splitlines() if line.startswith("# ")), path.stem)
    return {"id": path.stem, "title": title, "for": fields.get("For", "orchestrator"),
            "kind": fields.get("Kind", "unit-stop"), "state": fields.get("State"),
            "at": fields.get("At") or fields.get("Asked"), "recommendation": fields.get("Recommendation"),
            "reply": fields.get("Reply"), "outcome": fields.get("Outcome"),
            "answer": fields.get("Answer"), "answered": answered}


def collect(root, who=None):
    base = folder(root)
    cards = [read_card(p, False) for p in sorted(base.glob("*.md"))]
    cards += [read_card(p, True) for p in sorted((base / "answered").glob("*.md"))]
    return [c for c in cards if who is None or c["for"] == who]


def notify_text(root):
    open_human = [c for c in collect(root, "human") if not c["answered"]]
    if not open_human:
        return ""
    titles = "; ".join(c["title"] for c in open_human)
    return f"{len(open_human)} decision(s) wait for you: {titles}"[:200]


def main(argv=None, root=Path.cwd()):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--for", dest="who", choices=("human", "orchestrator"))
    asking = sub.add_parser("decide")
    asking.add_argument("ident")
    asking.add_argument("--question", required=True)
    asking.add_argument("--recommend", required=True)
    closing = sub.add_parser("close")
    closing.add_argument("ident")
    closing.add_argument("--answer", required=True)
    sub.add_parser("notify-text")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            print(json.dumps([c for c in collect(root, args.who) if not c["answered"]], indent=1))
        elif args.command == "decide":
            print(decide(root, args.ident, args.question, args.recommend))
        elif args.command == "close":
            print(close(root, args.ident, args.answer))
        else:
            print(notify_text(root))
    except ValueError as error:
        print(f"asks: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
