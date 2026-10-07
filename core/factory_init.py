#!/usr/bin/env python3
"""Set up (or update) the factory in a project repo. Used by `factory init` and every adapter.

  factory init --plan  [--project DIR] [--preset P] [--adapter A]     show what would happen
  factory init --apply [--project DIR] [--preset P] [--adapter A] [--overwrite PATH ...]

Footprint: personal (the default) changes no tracked file; the factory's files are hidden through
.git/info/exclude, settings go to .claude/settings.local.json and the rules import to CLAUDE.local.md.
shared writes .claude/settings.json, CLAUDE.md, .gitignore and a pre-commit hook for the whole team.
  factory init --apply --update     replace every kit file that changed (after /plugin update or git pull)
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
IGNORE_LINES = ("var/factory/", "__pycache__/", "*.pyc", ".sabotage-tmp/", "*.factory-new", ".factory-review.json",
                ".factory-crew-*.json", "factory.toml.proposed")
FOOTPRINTS = ("personal", "shared")
# Personal setup (the default): every path the factory creates is hidden through .git/info/exclude, a file that
# stays on this machine. Nothing tracked changes, so teammates' tools and the repo's history stay as they were.
PERSONAL_EXCLUDE = ("factory/", ".ai/", "crew/", "dashboard/", "var/factory/", "factory.toml", "factory.toml.proposed",
                    ".factory-clone", ".claude/settings.local.json", "CLAUDE.local.md", ".codex/profiles/",
                    "*.factory-new", ".factory-review.json", ".factory-crew-*.json", ".sabotage-tmp/")
PERSONAL_IF_NEW = ("state.md", "plan/")


def items(preset="claude-only", adapter="claude-code", footprint="personal"):
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
    if adapter == "claude-code":  # personal: the git-ignored local settings file, never the team's shared one
        pairs.append(("claude/settings.json", ".claude/settings.json" if footprint == "shared" else ".claude/settings.local.json"))
    found += [(templates / src, dst) for src, dst in pairs]
    found += [(p, f".ai/prompts/crew/{p.name}") for p in sorted((CORE / "templates/prompts/crew").glob("*.md"))]
    found += [(CORE / "factory/crew.toml", "factory/crew.toml")]
    planning = CORE / "planning/slice-matrix"
    found += [(planning / "scripts/validate_matrix.py", "factory/planning/validate_matrix.py"),
              (planning / "scripts/render_matrix.py", "factory/planning/render_matrix.py"),
              (planning / "schema/slice-matrix.schema.json", "factory/schema/slice-matrix.schema.json")]
    return found


def tracked(project, path):
    return subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=project, capture_output=True).returncode == 0


def git_path(project, name):
    out = subprocess.run(["git", "rev-parse", "--git-path", name], cwd=project, capture_output=True, text=True)
    return (project / out.stdout.strip()) if out.returncode == 0 else None


def exclude(project, lines):
    """Add lines to .git/info/exclude (shared by all worktrees of this clone, never pushed)."""
    path = git_path(project, "info/exclude")
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text().splitlines() if path.exists() else []
    new = [line for line in lines if line not in old]
    if new:
        path.write_text("\n".join(old + ["# factory kit (personal setup)", *new]) + "\n")
    return new


def plan(project, preset="claude-only", adapter="claude-code", footprint="personal"):
    if preset not in PRESETS or adapter not in ADAPTERS:
        raise ValueError(f"preset is one of {', '.join(PRESETS)}; adapter is one of {', '.join(ADAPTERS)}")
    if footprint not in FOOTPRINTS:
        raise ValueError(f"footprint is one of {', '.join(FOOTPRINTS)}")
    rows = []
    for source, target in items(preset, adapter, footprint):
        if not source.is_file():
            raise FileNotFoundError(f"the kit is missing {source.relative_to(CORE.parent)}")
        path = project / target
        if footprint == "personal" and target not in PROJECT_OWNED and tracked(project, target):
            raise ValueError(f"{target} is tracked by the team's repository; a personal setup never changes tracked "
                             "files. Use --footprint shared only if the team agreed, or move that file first.")
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


def apply(project, overwrite=(), preset="claude-only", adapter="claude-code", probe_report=None, footprint="personal",
          factory_clone=False, update=False):
    done = []
    if footprint == "personal":
        hidden = exclude(project, [*PERSONAL_EXCLUDE, *[p for p in PERSONAL_IF_NEW if not tracked(project, p.rstrip("/"))]])
        done.append("personal setup: nothing tracked changes; factory files are hidden in .git/info/exclude"
                    + (f" ({len(hidden)} new lines)" if hidden else ""))
    if factory_clone:
        (project / ".factory-clone").write_text("This clone belongs to the factory: the clock runs only here.\n")
        done.append("marked this folder as the factory's own clone (.factory-clone)")
    if not (project / "factory.toml").exists():
        import probe
        report = probe_report or probe.probe()
        text, rows = probe.roles_file(probe.load_preset(preset), report)
        sys.path.insert(0, str(CORE / "factory"))
        import land
        chosen = land.landing_plan(project)
        if chosen["github"]:  # written explicitly, so the mode in use is visible in factory.toml
            text = f'# Landing chosen by factory init: {chosen["why"]}\nlanding = "{chosen["landing"]}"\n' + text
        else:  # not written: no explicit direct, so a later GitHub origin is never pushed to directly
            text = f'# Landing: {chosen["why"]}. Not written here, so it follows the origin.\n' + text
        (project / "var/factory").mkdir(parents=True, exist_ok=True)
        (project / "var/factory/probe.json").write_text(json.dumps(report, indent=1))
        probe_cost = 0.0
        with (project / "var/factory/spend.jsonl").open("a") as ledger:  # the probe's calls count like any model run
            for tool, found in report["tools"].items():
                for model, cost in (found.get("cost_usd") or {}).items():
                    ledger.write(json.dumps({"at": report["at"], "who": f"probe:{model}", "cost_usd": cost}) + "\n")
                    probe_cost += cost
        if probe_cost:
            done.append(f"model probe cost: ${round(probe_cost, 4)} (recorded in the spend ledger)")
        (project / "factory.toml").write_text(f'footprint = "{footprint}"\n' + text)
        done += [f"role {r['role']}: {r['tool']}:{r['model']} ({r['why']})" for r in rows]
        done += probe.cost_summary(tomllib.loads(text))
    for (source, target), row in zip(items(preset, adapter, footprint), plan(project, preset, adapter, footprint)):
        path = project / target
        path.parent.mkdir(parents=True, exist_ok=True)
        refresh = update and row["action"] == "differs"  # --update replaces every kit file that is not project-owned
        if row["action"] == "create" or target in overwrite or refresh:
            shutil.copy2(source, path)
            done.append(f"wrote {target}")
        elif row["action"] == "differs":
            shutil.copy2(source, path.with_name(path.name + ".factory-new"))
            done.append(f"kept {target}; kit version in {target}.factory-new")
    for script in (project / "factory").glob("*.sh"):
        script.chmod(0o755)
    (project / "var/factory/dashboard").mkdir(parents=True, exist_ok=True)
    (project / "factory/VERSION").write_text((CORE.parent / "VERSION").read_text())
    (project / "factory/KIT").write_text(str(CORE.parent) + "\n")  # where the kit lives, for the update check
    rules = (project / ".ai/factory-agents.md").read_text()
    if adapter == "claude-code":  # personal: the person's own CLAUDE.local.md; shared: the team's CLAUDE.md
        claude_md = project / ("CLAUDE.md" if footprint == "shared" else "CLAUDE.local.md")
        text = claude_md.read_text() if claude_md.exists() else ""
        if IMPORT_LINE not in text:
            claude_md.write_text(text + ("\n" if text and not text.endswith("\n") else "") +
                                 f"\n# Factory rules (from the factory kit)\n{IMPORT_LINE}\n")
            done.append(f"{claude_md.name} imports .ai/factory-agents.md")
    elif footprint == "shared":
        managed_block(project, "AGENTS.md", rules)
        done.append("AGENTS.md carries the factory rules in a managed block")
    else:
        done.append("personal setup: AGENTS.md is the team's file and was not changed; the factory's rules are in "
                    ".ai/factory-agents.md, and the chief launcher passes them to the session")
    roles = tomllib.loads((project / "factory.toml").read_text())["roles"]
    generated = [Path(p).relative_to(project) for p in agents_gen.generate_all(project)]
    done += [f"generated {p}" for p in generated]
    if footprint == "personal":
        exclude(project, [str(p) for p in generated if p.parts[0] == ".claude"])
    if footprint == "shared":
        ignore = project / ".gitignore"
        lines = ignore.read_text().splitlines() if ignore.exists() else []
        ignore.write_text("\n".join(lines + [line for line in IGNORE_LINES if line not in lines]) + "\n")
        hooks_path = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=project, capture_output=True, text=True)
        hook = git_path(project, "hooks/pre-commit")
        if hooks_path.stdout.strip():  # a team hooks folder (husky and the like) is the team's, never the factory's
            done.append("core.hooksPath is set: the factory's pre-commit check was not installed (add "
                        "python3 factory/consistency.py --staged to your team hook if wanted)")
        elif hook and not hook.exists():
            hook.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CORE / "templates/pre-commit", hook)
            hook.chmod(0o755)
            done.append("installed the pre-commit hook")
    sys.path.insert(0, str(project / "factory"))
    import protect
    protect.snapshot(project)
    done.append("protected files recorded: a change to factory/, factory.toml, prompts or rules waits for factory approve")
    import common
    import land
    host, modes = land.host_modes(project)
    mode, source = land.effective_landing(project, common.config(project))
    done.append(f"origin host: {host}; landing modes that work here: {', '.join(modes)}")
    done.append(f"landing in use: {mode} ({source}); {land.landing_plan(project)['why']}")
    caches = [p for p in subprocess.run(["git", "ls-files"], cwd=project, capture_output=True, text=True).stdout.split()
              if "__pycache__" in Path(p).parts or p.endswith((".pyc", ".pyo"))]
    if caches:
        done.append(f"WARNING: the repo tracks {len(caches)} Python cache file(s), for example {caches[0]}. Remove them once: "
                    "git rm -r --cached $(git ls-files '*.pyc' '*/__pycache__/*') and commit; .gitignore now ignores them.")
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
    parser.add_argument("--footprint", default="personal", choices=FOOTPRINTS,
                        help="personal (default): nothing tracked changes; shared: the team's repo gets the factory files")
    parser.add_argument("--factory-clone", action="store_true",
                        help="mark this folder as the factory's own clone (.factory-clone); the clock runs only there")
    parser.add_argument("--update", action="store_true",
                        help="replace every kit file that changed (factory scripts, presets, templates), keep project-owned files")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    if not (project / ".git").exists():
        print(f"factory init: {project} is not the top of a git repo", file=sys.stderr)
        return 2
    try:
        footprint = args.footprint
        if (project / "factory.toml").exists() and "--footprint" not in (argv or sys.argv):
            footprint = tomllib.loads((project / "factory.toml").read_text()).get("footprint", "personal")
        result = (plan(project, args.preset, args.adapter, footprint) if args.plan
                  else apply(project, set(args.overwrite), args.preset, args.adapter,
                             json.loads(args.probe_file.read_text()) if args.probe_file else None, footprint,
                             args.factory_clone, args.update))
    except (FileNotFoundError, ValueError) as error:
        print(f"factory init: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
