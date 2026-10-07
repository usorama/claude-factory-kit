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


def file_notes(root, unit_label, notes, cap=50):
    """Review notes and downgraded findings never block and are never lost. They go word for word to
    var/factory/notes/<unit>.md (at most cap of them), and plan/backlog.md gets one todo row per unit that points
    there, so a chatty reviewer never floods the file the team reads. Returns the number of notes recorded."""
    from common import now, queue_lock, var
    path = Path(root) / "plan/backlog.md"
    if not notes or not path.exists():
        return 0
    label = "".join(c if c.isalnum() or c in "-_." else "_" for c in unit_label)
    row_id = f"N-{label}"
    with queue_lock(root):
        text = path.read_text()
        if f"| {row_id} |" in text:
            return 0
        kept = [" ".join(str(n).split()) for n in notes][:cap]
        folder = var(root) / "notes"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{label}.md").write_text(f"# Review notes on {unit_label}\n\n" + "".join(f"- {n}\n" for n in kept)
                                            + (f"\n({len(notes) - cap} more notes were dropped)\n" if len(notes) > cap else ""))
        row = (f"| {row_id} | todo | {now()[:10]} | {len(kept)} review note(s) in var/factory/notes/{label}.md "
               f"| review notes on {unit_label} |")
        path.write_text(text.rstrip("\n") + "\n" + row + "\n")
    return len(kept)


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
