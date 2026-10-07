#!/usr/bin/env python3
"""End-to-end dry run with deterministic fake tools (sample/fakes): no network, no model calls.

Makes a tiny repo with a bare 'origin', installs the factory with `factory init` (the model probe
runs against the fake claude and codex, which know only $FAKE_MODELS), runs the crew's before-cut
check, cuts two units of row W1 (unit 2 on top of unit 1, and without a brief, so Quill writes it),
runs clock ticks until both land, closes the row through code (conformance and claim checks), runs
the retro (claim verifier, the Bookie), then builds the dashboard through the staleness gate.
Usage: python3 sample/dry_run.py [folder] [--preset claude-only|codex-only|claude-codex|generic]
                                 [--landing direct|auto|pr_only] [--models id,id,...]
Exit 0 when both units landed, main is green, the expected crew ran, and the records agree.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
SAMPLE = CORE / "sample"
ADAPTER = {"claude-only": "claude-code", "codex-only": "codex", "claude-codex": "claude-code", "generic": "generic"}
DEFAULT_MODELS = "claude-sonnet-5-5,claude-sonnet-5,claude-sonnet-4-6,claude-haiku-5,gpt-6-sol,gpt-6-astra,gpt-6-luna"
EXPECTED_CREW = {"sorter-sam", "sweeper-sid", "plan-coverage-auditor", "quill", "inspector-grumble",
                 "spec-conformance-auditor", "claim-verifier", "the-bookie"}


def sh(*command, cwd, env=None, check=True):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if check and result.returncode:
        raise SystemExit(f"FAILED: {' '.join(map(str, command))}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def option(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main(folder, preset, landing, models):
    top = Path(folder or tempfile.mkdtemp(prefix="factory-dry-run-")).resolve()
    top.mkdir(parents=True, exist_ok=True)
    origin, repo = top / "origin.git", top / "work"
    env = dict(os.environ, PATH=f"{SAMPLE / 'fakes'}{os.pathsep}{os.environ['PATH']}", FAKE_MODELS=models,
               FAKE_SOLUTIONS=str(SAMPLE / "solutions"), FAKE_GH_LOG=str(top / "fake-gh.jsonl"),
               GIT_AUTHOR_NAME="dry-run", GIT_AUTHOR_EMAIL="dry-run@localhost",
               GIT_COMMITTER_NAME="dry-run", GIT_COMMITTER_EMAIL="dry-run@localhost")
    sh("git", "init", "-q", "--bare", "-b", "main", str(origin), cwd=top)
    shutil.copytree(SAMPLE / "seed", repo)
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    factory = [sys.executable, str(CORE / "cli.py")]
    init = json.loads(sh(*factory, "init", "--apply", "--project", str(repo), "--preset", preset,
                         "--adapter", ADAPTER[preset], cwd=repo, env=env))
    toml = (repo / "factory.toml").read_text()
    if preset == "generic":  # a person fills in commands and models; here the generic fake agent does the work
        sys.path.insert(0, str(CORE / "factory"))
        import tomllib, tomlw
        data = tomllib.loads(toml)
        for name, role in data["roles"].items():
            role["model"] = "claude-sonnet-5" if name == "reviewer" else "claude-sonnet-5-5"
            if "command" in role:
                role.update(command=[str(SAMPLE / "fakes/claude"), "--model", "{model}"], output="claude-json")
        data["roles"]["reviewer"]["fresh_session"] = True
        toml = tomlw.dumps(data, "Generic preset, filled in by hand.")
    (repo / "factory.toml").write_text(f"lanes = 4\nlanding = \"{landing}\"\n" + toml)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    (repo / "state.md").write_text(f"# State\n\n## Position\nUpdated {stamp} UTC.\n\n- W1 building.\n")
    shutil.copy(SAMPLE / "seed/plan/backlog.md", repo / "plan/backlog.md")
    sh("git", "add", "-A", cwd=repo, env=env)
    sh("git", "commit", "-q", "-m", "seed and factory", cwd=repo, env=env)
    sh("git", "remote", "add", "origin", str(origin), cwd=repo)
    sh("git", "push", "-q", "-u", "origin", "main", cwd=repo, env=env)

    tick = [sys.executable, "factory/tick.py"]
    sh(*factory, "crew", "before-cut", "W1", "--project", str(repo), cwd=repo, env=env)
    for n, start in ((1, None), (2, "unit/W1/1")):
        extra = ["--from", start] if start else []
        tree = Path(sh(*tick, "worktree", "W1", str(n), *extra, cwd=repo, env=env))
        shutil.copytree(SAMPLE / "cuts" / f"W1-U{n}", tree, dirs_exist_ok=True)
        sh("git", "add", "-A", cwd=tree, env=env)
        sh("git", "commit", "-q", "-m", f"W1-U{n}: cut", cwd=tree, env=env)
        sh(*tick, "enqueue", f".ai/units/W1/{n}.json", str(tree), cwd=repo, env=env)

    history = []
    for _ in range(12):
        line = json.loads(sh(*tick, "tick", cwd=repo, env=env))
        states = [u["state"] for u in json.loads(sh(*tick, "status", cwd=repo, env=env))]
        history.append({"tick": line, "states": states})
        if all(s not in ("cut", "red", "built", "checked", "reviewed", "pr_open") for s in states):
            break
        if landing == "pr_only":  # a person merges each open pull request
            for entry in json.loads((repo / "var/factory/queue.json").read_text())["units"]:
                if entry["state"] == "pr_open":
                    head = sh("git", "rev-parse", "HEAD", cwd=entry["worktree"])
                    sh("gh", "pr", "merge", entry["pr"].rsplit("/", 1)[1], "--merge", "--match-head-commit",
                       head, cwd=entry["worktree"], env=env)
    # The chief of staff asks code to close the row; code runs the row_landed crew, then marks it done.
    sh("git", "pull", "-q", "--ff-only", "origin", "main", cwd=repo, env=env)
    closed = json.loads(sh(*tick, "close-row", "W1", cwd=repo, env=env))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    (repo / "state.md").write_text(f"# State\n\n## Position\nUpdated {stamp} UTC.\n\n- W1 done: both units landed.\n")
    sh("git", "add", "-A", cwd=repo, env=env)
    sh("git", "commit", "-q", "-m", "W1 done", cwd=repo, env=env)
    sh("git", "push", "-q", "origin", "main", cwd=repo, env=env)
    pruned = json.loads(sh(*tick, "prune", cwd=repo, env=env))
    sh(*factory, "retro", "--project", str(repo), cwd=repo, env=env)
    page = sh(*factory, "dashboard", "--project", str(repo), cwd=repo, env=env)
    check = top / "check"
    sh("git", "clone", "-q", str(origin), str(check), cwd=top)
    suite = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=check,
                           capture_output=True, text=True)
    data = json.loads((repo / "var/factory/dashboard/data.json").read_text())
    crew_ran = {c["agent"] for c in data["sections"]["metrics"]["crew"] if c["runs"]}
    units = json.loads((repo / "var/factory/queue.json").read_text())["units"]
    summary = {
        "folder": str(top), "preset": preset, "landing": landing,
        "roles": [line for line in init if line.startswith("role ")],
        "ticks": [h["states"] for h in history],
        "landed": history[-1]["states"] == ["landed", "landed"],
        "row_closed": closed.get("done"), "work_folders_pruned": len(pruned),
        "attempts_used": sum(u["attempts"] for u in units),
        "main_suite": suite.stdout.strip().splitlines()[-1] if suite.stdout.strip() else suite.stderr[-200:],
        "sabotage_undone": "sabotage" not in (check / "textkit/words.py").read_text(),
        "brief_by_quill": (check / ".ai/specs/W1-U2.md").read_text().startswith("# Brief by Quill"),
        "crew_ran": sorted(crew_ran), "page": page,
        "findings": [f["code"] for f in data["sections"]["consistency"]["findings"]],
        "independence": data["sections"]["now"]["review_independence"]["text"],
    }
    print(json.dumps(summary, indent=1))
    ok = (summary["landed"] and summary["row_closed"] and suite.returncode == 0 and summary["sabotage_undone"]
          and summary["brief_by_quill"] and crew_ran == EXPECTED_CREW and not summary["findings"]
          and summary["attempts_used"] == 0)
    print("DRY RUN PASSED" if ok else "DRY RUN FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    words = [a for a in sys.argv[1:] if not a.startswith("--")]
    values = {sys.argv[i + 1] for i, a in enumerate(sys.argv) if a.startswith("--") and i + 1 < len(sys.argv)}
    folder = next((w for w in words if w not in values), None)
    sys.exit(main(folder, option("--preset", "claude-only"), option("--landing", "direct"),
                  option("--models", DEFAULT_MODELS)))
