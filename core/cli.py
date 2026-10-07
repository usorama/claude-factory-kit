#!/usr/bin/env python3
"""factory: the one command every adapter (Claude Code, Codex, generic, a person) calls.

  factory init --plan|--apply [--preset claude-only|codex-only|claude-codex|generic]
               [--adapter claude-code|codex|generic] [--overwrite PATH ...]
  factory agents          regenerate agent files from factory.toml (after changing roles or prompts)
  factory chief [--print] start the Chief of Staff role AND its loop with its pinned model (run it in tmux)
  factory tick            one clock tick in this project
  factory clock [--print] install the 5-minute clock (cron, launchd; prints the Task Scheduler line)
  factory dashboard       build the dashboard page through the staleness gate; prints its path
  factory retro           daily report, the claim verifier on it, the Bookie's scorecard, lessons ready
  factory crew before-cut <row> | handoff <file>   start a crew agent on its trigger (code, never a session)
  factory probe [--preset P]   probe the exact models that answer here; writes factory.toml.proposed
  factory roles accept    approve factory.toml.proposed (a person decides; nothing switches by itself)
  factory promote-lesson <id> --plugin-repo DIR [--files factory/x.py ...] [--push]
  factory check [repo]    check the kit repo itself: core, adapters, manifests, versions
All commands act on the project in the current folder (or --project DIR).
"""
import subprocess
import sys
import tomllib
from pathlib import Path

CORE = Path(__file__).resolve().parent
COMMANDS = ("init", "agents", "chief", "tick", "clock", "dashboard", "retro", "crew", "probe", "roles", "promote-lesson", "check")
sys.path.insert(0, str(CORE))


def project_arg(args):
    if "--project" in args:
        i = args.index("--project")
        return Path(args[i + 1]).resolve(), args[:i] + args[i + 2:]
    return Path.cwd(), args


def run_project(project, *command):
    return subprocess.run([sys.executable, *command], cwd=project).returncode


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    command, rest = args[0], args[1:]
    if command == "init":
        import factory_init
        return factory_init.main(rest)
    if command == "check":
        import check_kit
        problems = check_kit.problems(rest[0] if rest else CORE.parent)
        print("\n".join(problems) or "kit check: clean")
        return 1 if problems else 0
    if command == "promote-lesson":
        import promote_lesson
        return promote_lesson.main(rest)
    project, rest = project_arg(rest)
    if not (project / "factory/tick.py").is_file():
        print(f"factory: {project} has no factory/; run: factory init --apply", file=sys.stderr)
        return 2
    if command == "agents":
        import agents_gen
        print("\n".join(agents_gen.generate_all(project)))
        return 0
    if command == "chief":
        return subprocess.run(["bash", "factory/chief.sh", *rest], cwd=project).returncode
    if command == "tick":
        return run_project(project, "factory/tick.py", "tick")
    if command == "clock":
        return subprocess.run(["bash", "factory/install-clock.sh", str(project), *rest], cwd=project).returncode
    if command == "dashboard":
        import build_dashboard
        print(build_dashboard.build(project))
        return 0
    if command == "retro":
        code = run_project(project, "factory/daily_report.py", "--write")
        reports = sorted((project / "var/factory/daily").glob("*.md"))
        if not code and reports:
            code = run_project(project, "factory/crew.py", "retro", str(reports[-1]))
        return code or run_project(project, "factory/lessons.py", "ready")
    if command == "crew":
        return run_project(project, "factory/crew.py", *rest)
    if command == "probe":
        import probe
        return probe.main(["--project", str(project), *rest])
    if command == "roles":
        proposed = project / "factory.toml.proposed"
        if rest[:1] != ["accept"] or not proposed.exists():
            print("factory roles accept: approves factory.toml.proposed (written by factory probe)", file=sys.stderr)
            return 2
        (project / "factory.toml").write_text(proposed.read_text())
        proposed.unlink()
        subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'factory'); import common; "
                        "common.log('.', event='roles_accepted', note='factory.toml.proposed approved by a person')"],
                       cwd=project, check=False)
        import agents_gen
        print("\n".join(agents_gen.generate_all(project)))
        return 0
    print(f"factory: unknown command {command}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
