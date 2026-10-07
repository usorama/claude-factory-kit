"""Real-model smoke test: the real claude CLI, no fakes. Skipped unless FACTORY_REAL_SMOKE=1 and a model answers.

It catches what fake tools cannot (permissions, untrusted work folders, answer files, cost recording):
one crew pass before the cut (Sweeper Sid and the plan coverage auditor write their answer files), one tiny
unit built and reviewed for real, landed with plain git onto a local bare origin. The setup follows
SETUP-CHECKLIST.md: the team repo is pushed to its origin, the factory gets its own clone (with a git identity), and
`factory init --apply --factory-clone` sets it up there. Spend is capped at
FACTORY_SMOKE_BUDGET (default 1.0 US dollars) by the factory's own daily budget.
  FACTORY_REAL_SMOKE=1 python3 -m pytest -q tests/test_real_smoke.py -s
Models: FACTORY_SMOKE_BUILDER (default claude-haiku-4-5) and FACTORY_SMOKE_REVIEWER (default claude-sonnet-5-5).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core"
SAMPLE = CORE / "sample"
BUILDER = os.environ.get("FACTORY_SMOKE_BUILDER", "claude-haiku-4-5")
REVIEWER = os.environ.get("FACTORY_SMOKE_REVIEWER", "claude-sonnet-5-5")
BUDGET = float(os.environ.get("FACTORY_SMOKE_BUDGET", "1.0"))


def answers(model):
    try:
        result = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--no-session-persistence",
                                 "--max-turns", "1"], input="Reply with exactly the word: ok", capture_output=True,
                                text=True, timeout=120)
        return json.loads(result.stdout).get("subtype") == "success"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(os.environ.get("FACTORY_REAL_SMOKE") != "1" or not shutil.which("claude"),
                                reason="set FACTORY_REAL_SMOKE=1 on a machine where claude is signed in")


def sh(*command, cwd, check=True):
    result = subprocess.run([str(c) for c in command], cwd=cwd, capture_output=True, text=True)
    assert not check or result.returncode == 0, f"{command}\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


def test_a_real_crew_pass_build_review_and_landing(tmp_path):
    if not (answers(BUILDER) and answers(REVIEWER)):
        pytest.skip(f"{BUILDER} or {REVIEWER} does not answer here")
    origin, team, repo = tmp_path / "origin.git", tmp_path / "team", tmp_path / "work"
    sh("git", "init", "-q", "--bare", "-b", "main", origin, cwd=tmp_path)
    shutil.copytree(SAMPLE / "seed", team)  # items 8 and 9: the team's repo on its origin, then the factory's clone
    sh("git", "init", "-q", "-b", "main", cwd=team)
    sh("git", "add", "-A", cwd=team)
    sh("git", "-c", "user.name=smoke", "-c", "user.email=smoke@localhost", "commit", "-q", "-m", "seed", cwd=team)
    sh("git", "remote", "add", "origin", origin, cwd=team)
    sh("git", "push", "-q", "-u", "origin", "main", cwd=team)
    sh("git", "clone", "-q", origin, repo, cwd=tmp_path)
    sh("git", "config", "user.name", "Smoke Test", cwd=repo)  # item 2: the factory commits as the person
    sh("git", "config", "user.email", "smoke@example.invalid", cwd=repo)
    report = {"at": "smoke", "tools": {"claude": {"available": True, "answered": [REVIEWER, BUILDER]},
                                       "codex": {"available": False, "answered": []}}}
    (tmp_path / "probe.json").write_text(json.dumps(report))
    sh(sys.executable, CORE / "cli.py", "init", "--apply", "--factory-clone", "--project", repo, "--probe-file",
       tmp_path / "probe.json", cwd=repo)
    toml = (repo / "factory.toml").read_text()
    blocks = re.split(r"(?m)^(?=\[roles\.)", toml)
    for i, block in enumerate(blocks):  # the cheap pair: a small builder, a different reviewer, low effort
        role = re.match(r"\[roles\.([a-z-]+)\]", block)
        if role:
            model = REVIEWER if role.group(1) in ("reviewer", "chief-of-staff") else BUILDER
            block = re.sub(r'(?m)^model = ".*"$', f'model = "{model}"', block)
            blocks[i] = re.sub(r'(?m)^effort = ".*"$', 'effort = "low"', block)
    toml = "".join(blocks).replace("same_tool_review", "#same_tool_review").replace(
        'inspector-grumble-same-tool.v1.md', 'inspector-grumble.v1.md')
    toml = re.sub(r"(?m)^daily_budget_usd = .*$", f"daily_budget_usd = {BUDGET}", toml)
    toml = re.sub(r"(?m)^(landing|lanes) = .*\n", "", toml)  # init may have written a landing choice already
    (repo / "factory.toml").write_text('landing = "direct"\nlanes = 1\n' + toml)
    sh(sys.executable, CORE / "cli.py", "approve", "--yes", "--project", repo, cwd=repo)  # the person's own edit
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    (repo / "state.md").write_text(f"# State\n\n## Position\nUpdated {stamp} UTC.\n\n- W1 building (smoke test).\n")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-q", "--allow-empty", "-m", "factory set up (personal: nothing tracked changed)", cwd=repo)
    sh("git", "push", "-q", "origin", "main", cwd=repo)
    factory = [sys.executable, CORE / "cli.py"]

    cut = json.loads(sh(*factory, "crew", "before-cut", "W1", "--project", repo, cwd=repo))
    assert cut["planning"] == "planned" and cut["already_done"] is False
    tree = Path(sh(sys.executable, "factory/tick.py", "worktree", "W1", "1", cwd=repo))
    shutil.copytree(SAMPLE / "cuts/W1-U1", tree, dirs_exist_ok=True)
    sh("git", "add", "-A", cwd=tree)
    sh("git", "commit", "-q", "-m", "W1-U1: cut", cwd=tree)
    sh(sys.executable, "factory/tick.py", "enqueue", ".ai/units/W1/1.json", tree, cwd=repo)
    for _ in range(8):
        sh(sys.executable, "factory/tick.py", "tick", cwd=repo)
        state = json.loads(sh(sys.executable, "factory/tick.py", "status", cwd=repo))[0]["state"]
        if state not in ("cut", "red", "built", "checked", "reviewed"):
            break
    log = [json.loads(l) for l in (repo / "var/factory/log.jsonl").read_text().splitlines()]
    spend = [json.loads(l) for l in (repo / "var/factory/spend.jsonl").read_text().splitlines()]
    receipts = [(e.get("agent") or e.get("step"), e.get("model"), e.get("cost_usd")) for e in log if e.get("cost_usd") is not None]
    print("\nreceipts:", json.dumps(receipts), "\nspent:", round(sum(s["cost_usd"] for s in spend), 4))
    print("denials:", json.dumps([(e.get("step") or e.get("agent"), e.get("first_denial")) for e in log if e.get("denials")]))
    reports = sorted((repo / "var/factory/reports").glob("*.md")) if (repo / "var/factory/reports").exists() else []
    print("reports mentioning run_tests:", [p.name for p in reports if "run_tests" in p.read_text()])
    assert state == "landed", [e.get("outcome") for e in log if e.get("event") == "end"][-4:]
    crew_ok = [e for e in log if e.get("event") == "crew" and e.get("ok")]
    assert {e["agent"] for e in crew_ok} >= {"sweeper-sid", "plan-coverage-auditor"}
    assert {m for _, m, _ in receipts} >= {BUILDER, REVIEWER}
    assert sum(s["cost_usd"] for s in spend) <= BUDGET + 0.5  # one run may cross the cap; then nothing starts
    check = tmp_path / "check"
    sh("git", "clone", "-q", origin, check, cwd=tmp_path)
    sh(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", cwd=check)
