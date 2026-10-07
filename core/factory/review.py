"""The review JSON form: what the reviewer writes, and how code decides the verdict.

Form: {"verdict": "PASS"|"REJECT", "high": [finding], "notes": [text], "suite_result_seen": bool}
A finding: {"kind", "test_or_paragraph_line", "file", "line", "reproduce_command", "cut"?: true}
A high finding blocks only when it is complete, its kind is on the closed list, and its file is in
the unit's file list. Anything else is downgraded to a note (a backlog row). Code, not the
reviewer's own verdict word, decides PASS or REJECT. The reviewer's prompt is the role's
versioned prompt file (.ai/prompts/reviewer*.v<N>.md).
Usage: review.py <form.json> <unit.json>
"""
import json
import sys
from pathlib import Path

REQUIRED = ("kind", "test_or_paragraph_line", "file", "line", "reproduce_command")
KINDS = ("test_does_not_test_its_name", "paragraph_false_for_plain_input",
         "data_lost_on_normal_path", "test_weakened")


class FormInvalid(ValueError):
    """The reviewer did not leave a usable form; the review counts as an error, not a verdict."""


def parse(form, files):
    if not isinstance(form, dict) or not isinstance(form.get("high"), list) \
            or not isinstance(form.get("notes"), list):
        raise FormInvalid("the form needs lists 'high' and 'notes'")
    if form.get("suite_result_seen") is not True:
        raise FormInvalid("the reviewer did not see the whole suite run")
    blocking, notes = [], [str(note) for note in form["notes"]]
    for finding in form["high"]:
        finding = finding if isinstance(finding, dict) else {}
        missing = [k for k in REQUIRED if not finding.get(k)]
        if "line" not in missing and (type(finding["line"]) is not int or finding["line"] <= 0):
            missing.append("line")
        name = finding.get("test_or_paragraph_line") or "unnamed finding"
        if missing:
            notes.append(f"{name}: downgraded; missing {', '.join(missing)}")
        elif finding["kind"] not in KINDS:
            notes.append(f"{name}: downgraded; kind {finding['kind']} is not on the closed list")
        elif finding["file"] not in files:
            notes.append(f"{name}: downgraded; {finding['file']} is outside the unit")
        else:
            blocking.append(finding)
    return {"verdict": "REJECT" if blocking else "PASS", "blocking": blocking, "notes": notes,
            "cut": any(item.get("cut") is True for item in blocking)}


def file_notes(root, unit_label, notes):
    """Every note and downgraded finding becomes a todo row in plan/backlog.md (only a complete high
    finding naming an acceptance line can REJECT; nothing else is lost or blocks)."""
    from common import now, queue_lock
    path = Path(root) / "plan/backlog.md"
    if not notes or not path.exists():
        return 0
    with queue_lock(root):
        text = path.read_text()
        rows = [f"| N-{unit_label}-{i} | todo | {now()[:10]} | {' '.join(str(n).split()).replace('|', '/')[:300]} "
                f"| review note on {unit_label} |" for i, n in enumerate(notes, 1)
                if f"| N-{unit_label}-{i} |" not in text]
        path.write_text(text.rstrip("\n") + "\n" + "\n".join(rows) + "\n" if rows else text)
    return len(rows)


def summary(parsed):
    head = "CUT" if parsed["cut"] else parsed["verdict"]
    lines = [head] + [f"{b['file']}:{b['line']} {b['kind']}: {b['reproduce_command']}" for b in parsed["blocking"]]
    return "\n".join(lines + [f"note: {n}" for n in parsed["notes"]])


if __name__ == "__main__":
    try:
        unit = json.loads(open(sys.argv[2]).read())
        result = parse(json.loads(open(sys.argv[1]).read()), unit["files"])
    except (OSError, ValueError, IndexError, KeyError) as error:
        print(f"malformed form: {error}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(result, indent=1))
    sys.exit(1 if result["verdict"] == "REJECT" else 0)
