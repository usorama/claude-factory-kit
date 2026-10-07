#!/usr/bin/env python3
"""Render only valid matrices. Output goes to stdout for explicit redirection."""

import html
import sys

from validate_matrix import compute_path_schedule, outcome_completion_report, read_and_validate


def cell(value):
    text = html.escape(str(value), quote=False)
    for char in ("\\", "`", "*", "_", "[", "]", "|"):
        text = text.replace(char, f"&#{ord(char)};")
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render(matrix):
    rows = matrix["slices"]
    engines = matrix["engines"]
    waves, states = compute_path_schedule(rows, worst=True)
    success, success_states = compute_path_schedule(rows)
    conditional = any("runs_if" in row or "blocked_by_any" in row for row in rows)
    headers = ["Slice", "Behavior"] + [f"{e['id']}: {e['title']}" for e in engines] + ["Wave", "Blocked by"]
    if conditional:
        headers[-2:] = ["Success path wave", "Worst path wave", "Blocked by", "Blocked by any", "Runs if"]
    lines = ["# Slice matrix", "", cell(matrix["source"]["description"]), "",
             "| " + " | ".join(map(cell, headers)) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        values = [f"{row['id']}: {row['title']}", row["behavior"]]
        values += [row["engines"].get(e["id"], "") for e in engines]
        sid = row["id"]
        if conditional:
            values += [success.get(sid, success_states.get(sid, "unscheduled")),
                       waves.get(sid, states.get(sid, "unscheduled")),
                       ", ".join(row["blocked_by"]) or "None",
                       " OR ".join(" AND ".join(group) for group in row.get("blocked_by_any", [])) or "None",
                       "Conditional: all failed or not selected: " + ", ".join(row["runs_if"]["failed"]) if "runs_if" in row else "Always"]
        else:
            values += [waves[sid], ", ".join(row["blocked_by"]) or "None"]
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += ["", "## Computed waves", "", "A row needs every mandatory blocker to pass and one complete alternative group to pass.", ""]
    schedules = [("success path", success, success_states), ("worst path", waves, states)] if conditional else [(None, waves, states)]
    if conditional:
        lines += ["The success path skips every conditional slice. The worst path triggers every condition, so its referenced candidates fail. These are planned scenarios, not execution evidence.", ""]
    for label, path, path_states in schedules:
        if label:
            lines += [f"### {label}", ""]
        for wave in sorted(set(path.values())):
            ids = ", ".join(cell(row["id"]) + (f" ({path_states[row['id']]})" if conditional else "")
                            for row in rows if path.get(row["id"]) == wave)
            lines.append(f"- Wave {wave}: {ids}")
        if label:
            for row in rows:
                if row["id"] not in path:
                    lines.append(f"- {cell(row['id'])}: {path_states.get(row['id'], 'unscheduled')}")
            lines.append("")
    lines += ["", "## Planned outcome timing", ""]
    report = outcome_completion_report(matrix)
    lines += [cell(report[0]), ""]
    lines += ["- " + cell(line) for line in report[1:]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("R8: usage: render_matrix.py MATRIX.json", file=sys.stderr)
        return 1
    matrix, errors = read_and_validate(args[0])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if matrix.get("stop") is True:
        print(f"STOP: {matrix['reason']}", file=sys.stderr)
        return 3
    print(render(matrix), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
