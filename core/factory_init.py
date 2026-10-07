#!/usr/bin/env python3
"""Set up (or update) the factory in a project repo. Used by `factory init` and every adapter.

  factory init --plan  [--project DIR] [--preset P] [--adapter A]     show what would happen
  factory init --apply [--project DIR] [--preset P] [--adapter A] [--overwrite PATH ...]

Presets (roles file factory.toml): claude-only (default, no Codex needed), codex-only, claude-codex,
generic (fill in your own commands). Adapters: claude-code (CLAUDE.md imports the rules; agent files
in .claude/agents), codex (a managed block in AGENTS.md; profiles in .codex/profiles), generic
(a managed block in AGENTS.md).
Actions per target: create, same, differs (kept; the kit's version is written as <path>.factory-new
unless named in --overwrite), keep (project-owned). Project-owned files hold the project's own
state, roles and lessons and are never replaced unless named: they live in the project, so kit
updates never overwrite local self-improvement. Scripts go to <project>/factory/ (the clock runs
them from there, never from a plugin cache). Re-run after an update to see which scripts changed.
"""
import argparse
import filecmp
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

CORE = Path(__file__).resolve().parent
sys.path.insert(0, str(CORE))
import agents_gen  # noqa: E402

PRESETS = ("claude-only", "codex-only", "claude-codex", "generic")
ADAPTERS = ("claude-code", "codex", "generic")
PROJECT_OWNED = {"state.md", "plan/backlog.md", "factory.toml", ".ai/lessons.jsonl", ".ai/factory-rules.md",
                 ".ai/defect-library.md"} | {f".ai/prompts/{p.name}" for p in (CORE / "templates/prompts").glob("*.md")} | {
    f".ai/prompts/crew/{p.name}" for p in (CORE / "templates/prompts/crew").glob("*.md")}
IMPORT_LINE = "@.ai/factory-agents.md"
BEGIN, END = "<!-- factory:begin (managed by factory init; edit .ai/factory-agents.md) -->", "<!-- factory:end -->"
IGNORE_LINES = ("var/", "__pycache__/", ".sabotage-tmp/", "*.factory-new", ".factory-review.json", ".factory-crew-*.json",
                "factory.toml.proposed")


def items(preset="claude-only", adapter="claude-code"):
    """(source in the kit, target in the project)."""
    found = [(p, f"factory/{p.name}") for p in sorted((CORE / "factory").iterdir())
             if p.is_file() and p.suffix in (".py", ".sh")]
    found += [(p, f"factory/presets/{p.name}") for p in sorted((CORE / "factory/presets").glob("*.toml"))]
    found += [(p, f".ai/prompts/{p.name}") for p in sorted((CORE / "templates/prompts").glob("*.md"))]
    templates = CORE / "templates"
    pairs = [("dashboard/index.html", "dashboard/index.html"), ("dashboard/PUBLISH.md", "dashboard/PUBLISH.md"),
             ("factory-agents.md", ".ai/factory-agents.md"), ("../../RULES.md", ".ai/factory-rules.md"),
             ("../../PRINCIPLES.md", ".ai/factory-principles.md"), ("defect-library.md", ".ai/defect-library.md"),
             ("state.md", "state.md"), ("plan/backlog.md", "plan/backlog.md"), ("lessons.jsonl", ".ai/lessons.jsonl")]
    if adapter == "claude-code":
        pairs.append(("claude/settings.json", ".claude/settings.json"))
    found += [(templates / src, dst) for src, dst in pairs]
    found += [(p, f".ai/prompts/crew/{p.name}") for p in sorted((CORE / "templates/prompts/crew").glob("*.md"))]
    found += [(CORE / "factory/crew.toml", "factory/crew.toml")]
    planning = CORE / "planning/slice-matrix"
    found += [(planning / "scripts/validate_matrix.py", "factory/planning/validate_matrix.py"),
              (planning / "scripts/render_matrix.py", "factory/planning/render_matrix.py"),
              (planning / "schema/slice-matrix.schema.json", "factory/schema/slice-matrix.schema.json")]
    return found


def plan(project, preset="claude-only", adapter="claude-code"):
    if preset not in PRESETS or adapter not in ADAPTERS:
        raise ValueError(f"preset is one of {', '.join(PRESETS)}; adapter is one of {', '.join(ADAPTERS)}")
    rows = []
    for source, target in items(preset, adapter):
        if not source.is_file():
            raise FileNotFoundError(f"the kit is missing {source.relative_to(CORE.parent)}")
        path = project / target
        action = ("create" if not path.exists() else "same" if filecmp.cmp(source, path, shallow=False)
                  else "keep (project-owned)" if target in PROJECT_OWNED else "differs")
        rows.append({"target": target, "action": action})
    rows.append({"target": "factory.toml", "action": "keep (project-owned)" if (project / "factory.toml").exists() else
                 "create from a model probe: one tiny call per candidate model of each installed tool"})
    return rows


def managed_block(project, name, text):
    """Put the factory rules into AGENTS.md between markers; text outside the markers is never touched."""
    path = project / name
    old = path.read_text() if path.exists() else ""
    block = f"{BEGIN}\n{text.rstrip()}\n{END}\n"
    new = (re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", lambda _: block, old, flags=re.S)
           if BEGIN in old else old + ("\n" if old and not old.endswith("\n") else "") + block)
    path.write_text(new)


def apply(project, overwrite=(), preset="claude-only", adapter="claude-code", probe_report=None):
    done = []
    if not (project / "factory.toml").exists():
        import probe
        report = probe_report or probe.probe()
        text, rows = probe.roles_file(probe.load_preset(preset), report)
        (project / "var/factory").mkdir(parents=True, exist_ok=True)
        (project / "var/factory/probe.json").write_text(json.dumps(report, indent=1))
        (project / "factory.toml").write_text(text)
        done += [f"role {r['role']}: {r['tool']}:{r['model']} ({r['why']})" for r in rows]
    for (source, target), row in zip(items(preset, adapter), plan(project, preset, adapter)):
        path = project / target
        path.parent.mkdir(parents=True, exist_ok=True)
        if row["action"] == "create" or target in overwrite:
            shutil.copy2(source, path)
            done.append(f"wrote {target}")
        elif row["action"] == "differs":
            shutil.copy2(source, path.with_name(path.name + ".factory-new"))
            done.append(f"kept {target}; kit version in {target}.factory-new")
    for script in (project / "factory").glob("*.sh"):
        script.chmod(0o755)
    (project / "var/factory/dashboard").mkdir(parents=True, exist_ok=True)
    (project / "factory/VERSION").write_text((CORE.parent / "VERSION").read_text())
    rules = (project / ".ai/factory-agents.md").read_text()
    if adapter == "claude-code":
        claude_md = project / "CLAUDE.md"
        text = claude_md.read_text() if claude_md.exists() else ""
        if IMPORT_LINE not in text:
            claude_md.write_text(text + ("\n" if text and not text.endswith("\n") else "") +
                                 f"\n# Factory rules (from the factory kit)\n{IMPORT_LINE}\n")
            done.append("CLAUDE.md imports .ai/factory-agents.md")
    else:
        managed_block(project, "AGENTS.md", rules)
        done.append("AGENTS.md carries the factory rules in a managed block")
    roles = tomllib.loads((project / "factory.toml").read_text())["roles"]
    done += [f"generated {Path(p).relative_to(project)}" for p in agents_gen.generate_all(project)]
    for name in tomllib.loads((project / "factory/crew.toml").read_text())["agents"]:
        memory = project / "crew" / name / "memory.md"
        if not memory.exists():
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text(f"# {name}: project memory\n\nCode appends one dated line per run that taught something.\n")
    ignore = project / ".gitignore"
    lines = ignore.read_text().splitlines() if ignore.exists() else []
    ignore.write_text("\n".join(lines + [line for line in IGNORE_LINES if line not in lines]) + "\n")
    hooks = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=project, capture_output=True, text=True)
    hook = project / hooks.stdout.strip() / "pre-commit"
    if hooks.returncode == 0 and not hook.exists():
        hook.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CORE / "templates/pre-commit", hook)
        hook.chmod(0o755)
        done.append("installed the pre-commit hook")
    pin = project / "factory/toolchain.json"
    if not pin.exists():
        seen = json.loads(subprocess.run([sys.executable, "factory/fingerprint.py"], cwd=project,
                                         capture_output=True, text=True).stdout or "{}")
        tools = ("python", "machine", "git", "gh", "pytest") + tuple(
            t for t in ("claude", "codex") if any(r.get("tool") == t for r in roles.values()))
        pin.write_text(json.dumps({k: seen.get(k) for k in tools}, indent=1))
        done.append("pinned this machine's tools in factory/toolchain.json")
    return done


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--preset", default="claude-only", choices=PRESETS)
    parser.add_argument("--adapter", default="claude-code", choices=ADAPTERS)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", nargs="*", default=[])
    parser.add_argument("--probe-file", type=Path, help="use a saved probe report instead of calling the tools")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    if not (project / ".git").exists():
        print(f"factory init: {project} is not the top of a git repo", file=sys.stderr)
        return 2
    try:
        result = (plan(project, args.preset, args.adapter) if args.plan
                  else apply(project, set(args.overwrite), args.preset, args.adapter,
                             json.loads(args.probe_file.read_text()) if args.probe_file else None))
    except (FileNotFoundError, ValueError) as error:
        print(f"factory init: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
