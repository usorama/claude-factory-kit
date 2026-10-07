#!/usr/bin/env python3
"""Find the exact models this machine can use, and map role requirements to them with a fixed rule.

Probe: for every tool on PATH that models.toml knows, one tiny call per candidate exact model ID
("Reply with the word ok"). A model counts only if the call succeeds. Aliases are never probed.
Rule, the same everywhere:
  1. A role takes the first answering model of its tool, walking its `prefer` families in order and,
     inside a family, the candidate order of models.toml (newest first).
  2. The reviewer skips the builder's exact model. If nothing else answers, it takes the same model
     in a fresh session with the different review prompt (reviewer-same-tool), and the roles file
     says same_tool_review = "fresh-session" (the dashboard marks that weaker).
  3. A role whose tool has no answering model stops init with the reason; nothing falls back.
A re-probe never changes a running project: `factory probe` writes factory.toml.proposed and shows
the difference; a person approves with `factory roles accept`.
"""
import json
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

CORE = Path(__file__).resolve().parent
sys.path.insert(0, str(CORE / "factory"))
import tomlw  # noqa: E402

QUESTION = "Reply with exactly the word: ok"


class MappingRefused(ValueError):
    """A role has no model that answered."""


def family(tool, model):
    return model.split("-")[1] if tool == "claude" and model.count("-") >= 2 else model


def answered(tool, spec, model, run=subprocess.run):
    command = [part.format(model=model) for part in spec["probe"]]
    try:
        result = run(command, input=QUESTION, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)[:200]
    if result.returncode:
        return False, (result.stderr or result.stdout).strip()[-200:]
    if spec["output"] == "claude-json":
        try:
            data = json.loads(result.stdout)
        except ValueError:
            return False, "no JSON answer"
        ok = not data.get("is_error") and data.get("subtype") == "success"
        return ok, "" if ok else str(data.get("result"))[:200]
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith("{")]
    failed = [e for e in events if e.get("type") in ("turn.failed", "error")]
    ok = any(e.get("type") == "turn.completed" for e in events) and not failed
    return ok, "" if ok else json.dumps(failed[:1])[:200]


def probe(models=None, which=shutil.which, run=subprocess.run):
    models = models or tomllib.loads((CORE / "models.toml").read_text())
    report = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tools": {}}
    for tool, spec in models.items():
        if not which(spec["probe"][0]):
            report["tools"][tool] = {"available": False, "answered": [], "refused": {}}
            continue
        answers = {model: answered(tool, spec, model, run) for model in spec["candidates"]}
        report["tools"][tool] = {"available": True, "answered": [m for m, (ok, _) in answers.items() if ok],
                                 "refused": {m: why for m, (ok, why) in answers.items() if not ok}}
    return report


def pick(role, answers, skip=None):
    for want in role["prefer"]:
        for model in answers:
            if family(role["tool"], model) == want and model != skip:
                return model
    return None


def map_roles(preset, report):
    """Return (roles dict with models filled in, rows to show, same_tool_review value)."""
    roles, rows, same_tool = {}, [], ""
    order = ["chief-of-staff", "builder", "reviewer", "researcher", "summarizer"]
    for name in order + [n for n in preset["roles"] if n not in order]:
        role = dict(preset["roles"][name])
        if role["tool"] == "other":
            roles[name] = role
            rows.append({"role": name, "tool": "other", "model": role.get("model"), "why": "set by hand (generic preset)"})
            continue
        tool = report["tools"].get(role["tool"], {})
        answers = tool.get("answered", [])
        skip = roles["builder"]["model"] if name == "reviewer" and roles["builder"]["tool"] == role["tool"] else None
        model = pick(role, answers, skip)
        why = f"first answering model of {', '.join(role['prefer'])}"
        if model is None and skip and pick(role, answers):
            model, same_tool = skip, "fresh-session"
            role["prompt"] = ".ai/prompts/inspector-grumble-same-tool.v1.md"
            why = "only the builder's model answers: same model, fresh session, different review prompt (weaker)"
        elif name == "reviewer" and model and roles["builder"]["tool"] == role["tool"]:
            same_family = family(role["tool"], model) == family(role["tool"], skip)
            why = "same maker, different version" if same_family else "same maker, different model family"
        elif name == "reviewer" and model:
            why = "different maker"
        if model is None:
            state = "is not installed" if not tool.get("available") else "answered with none of the wanted families"
            raise MappingRefused(f"role {name} needs {role['tool']} ({', '.join(role['prefer'])}), which {state}; "
                                 "choose another preset or install the tool")
        for key in ("tier", "prefer"):
            role.pop(key, None)
        roles[name] = {"tool": role.pop("tool"), "model": model, **role}
        rows.append({"role": name, "tool": roles[name]["tool"], "model": model, "why": why})
    return roles, rows, same_tool


def roles_file(preset, report):
    roles, rows, same_tool = map_roles(preset, report)
    data = {"preset": preset["preset"], "probed_at": report["at"]}
    if same_tool:
        data["same_tool_review"] = same_tool
    data["roles"] = roles
    comment = ("Roles file written by `factory init` from the probe of " + report["at"] + ".\n"
               "Every model is an exact ID that answered on this machine. Change it only through\n"
               "`factory probe` + `factory roles accept`, or by hand with a reason in state.md.")
    return tomlw.dumps(data, comment), rows


def load_preset(name):
    return tomllib.loads((CORE / "factory/presets" / f"{name}.toml").read_text())


def main(argv=None):
    """factory probe [--project DIR] [--preset P] [--probe-file F]: write factory.toml.proposed."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--preset")
    parser.add_argument("--probe-file", type=Path, help="use a saved probe report instead of calling the tools")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    current = project / "factory.toml"
    name = args.preset or (tomllib.loads(current.read_text())["preset"] if current.exists() else "claude-only")
    report = json.loads(args.probe_file.read_text()) if args.probe_file else probe()
    (project / "var/factory").mkdir(parents=True, exist_ok=True)
    (project / "var/factory/probe.json").write_text(json.dumps(report, indent=1))
    try:
        text, rows = roles_file(load_preset(name), report)
    except MappingRefused as error:
        print(f"factory probe: {error}", file=sys.stderr)
        return 2
    (project / "factory.toml.proposed").write_text(text)
    print(json.dumps({"proposed": "factory.toml.proposed", "roles": rows,
                      "approve_with": "factory roles accept"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
