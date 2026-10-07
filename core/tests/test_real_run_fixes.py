"""1.2.1: defects found by the first real Claude-only run. Each test has a sabotage noted in FIXES.md."""
import json
import subprocess
from pathlib import Path

import pytest
from conftest import CORE, GREEN, git, plan_matrix, roles_project, unit_files

import build_check
import common
import crew
import drive
import land
import probe
import runners
import tick
from common import read_queue

FIX = Path(__file__).parent / "fixtures"
IDENT = ["-c", "user.name=t", "-c", "user.email=t@localhost"]


def commit(root, message):
    git(root, "add", "-A")
    git(root, *IDENT, "commit", "-q", "-m", message)


@pytest.fixture
def landing_repo(make_repo, tmp_path):
    """A repo with a bare origin (no forge at all) and a unit branch one commit ahead of main."""
    root = make_repo({"tests/test_ok.py": GREEN})
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git"))
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "checkout", "-q", "-b", "unit/R1/1")
    (root / "feature.py").write_text("X = 1\n")
    commit(root, "unit")
    return root


UNIT = {"paragraph": "Adds X. Sabotage: remove it.", "title": "Add X", "tests": [], "files": ["feature.py"]}


@pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
def test_direct_landing_pushes_the_tested_commit_with_plain_git_and_no_gh(landing_repo, method):
    landed, merged = land.land(landing_repo, UNIT, "main", (), "PASS", gh="/no/such/gh", mode="direct", method=method)
    remote = git(landing_repo, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert merged and remote == landed
    shown = subprocess.run(["git", "show", f"{landed}:feature.py"], cwd=landing_repo, capture_output=True, text=True)
    assert shown.stdout == "X = 1\n"


def test_direct_landing_never_overwrites_a_main_that_moved(landing_repo, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    (other / "late.txt").write_text("someone else landed first\n")
    commit(other, "late")
    git(other, "push", "-q", "origin", "main")
    moved = git(other, "rev-parse", "HEAD")
    tested = land.merged_suite(landing_repo, git(landing_repo, "rev-parse", "origin/main"), ())
    with pytest.raises(land.MainMoved):
        land.push_direct(landing_repo, tested, "main", git(landing_repo, "rev-parse", "origin/main"))
    assert git(landing_repo, "ls-remote", "origin", "refs/heads/main").split()[0] == moved


def test_init_says_which_landing_modes_work_for_the_origin(landing_repo, make_repo):
    assert land.host_modes(make_repo({"x": "x"}, "no-origin"))[0] == "none (no origin yet)"
    assert land.host_modes(landing_repo) == ("local", ["direct"])
    git(landing_repo, "remote", "set-url", "origin", "https://gitlab.example.invalid/team/repo.git")
    host, modes = land.host_modes(landing_repo)
    assert host == "gitlab.example.invalid" and modes == ["direct"]


def test_python_caches_never_count_as_the_units_change_and_never_block_a_catch_up(make_repo):
    root = make_repo({"tests/test_unit.py": "def test_a():\n    from src.newmod import go\n    assert go() == 1\n"
                      "def test_b():\n    from src.newmod import go\n    assert go()\ndef test_c():\n    from src.newmod import go\n    assert go() > 0\n",
                      "src/__init__.py": "", "src/__pycache__/old.cpython-312.pyc": "stale", **unit_files(tests=("a", "b", "c"))})
    base = git(root, "rev-parse", "HEAD")
    (root / "src/newmod.py").write_text("def go():\n    return 1\n")
    (root / "src/__pycache__/old.cpython-312.pyc").write_text("rewritten by a test run")
    (root / "src/__pycache__/newmod.cpython-312.pyc").write_text("new")
    result = build_check.build_check(".ai/units/R1/1.json", root, base, guard=False)
    assert result["files_changed"] == ["src/newmod.py"]
    assert land.restore_caches(root) == ["src/__pycache__/old.cpython-312.pyc"]
    assert (root / "src/__pycache__/old.cpython-312.pyc").read_text() == "stale"


def crew_repo(make_repo, cap=15.0, plan=True):
    files = {"plan/backlog.md": "| ID | Status |\n|---|---|\n| R1 | building |\n", "tests/test_ok.py": GREEN}
    if plan:
        files["plan/slice-matrix.json"] = plan_matrix("R1")
    root = make_repo(files)
    roles_project(root, edit=lambda text: text.replace("daily_budget_usd = 15.0", f"daily_budget_usd = {cap}"))
    return root


def fake_run(cost=0.4, write=True, denied=False):
    calls = []

    def run(command, cwd, input, env, **kw):
        calls.append(command)
        answer = json.loads((FIX / "claude-json-real.json").read_text())
        answer["total_cost_usd"] = cost
        if denied:
            answer["permission_denials"] = [{"tool_name": "Write", "tool_input": {"file_path": env["FACTORY_CREW_OUTPUT"]}}]
        if write:
            Path(env["FACTORY_CREW_OUTPUT"]).write_text(json.dumps(
                {"row": "R1", "verdict": "not_done", "criterion": "NONE", "evidence": "x", "evidence_command": ""}))
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")
    run.calls = calls
    return run


def test_crew_runs_count_toward_the_daily_budget_which_stops_the_next_run_with_one_card(make_repo):
    root = crew_repo(make_repo, cap=0.5)
    run = fake_run(cost=0.4)
    crew.run_agent(root, "sweeper-sid", "before_cut", "R1", {"row": "R1"}, run=run)
    assert common.spent_today(root) == 0.4
    crew.run_agent(root, "sweeper-sid", "before_cut", "R2", {"row": "R2"}, run=run)  # crosses the cap
    assert list((common.var(root) / "asks").glob("DEC-budget-*.md"))
    with pytest.raises(crew.CrewRefused, match="daily budget reached"):
        crew.run_agent(root, "sweeper-sid", "before_cut", "R3", {"row": "R3"}, run=run)
    assert len(run.calls) == 2 and len(list((common.var(root) / "asks").glob("DEC-budget-*.md"))) == 1


def test_a_build_does_not_start_when_the_budget_is_spent(make_repo):
    root = crew_repo(make_repo, cap=1.0)
    common.spend(root, "crew:sorter-sam", 1.2)
    build = runners.make_runners(root)["build"]
    (root / ".ai/units/R1").mkdir(parents=True)
    (root / ".ai/units/R1/1.json").write_text(json.loads(json.dumps(unit_files()[".ai/units/R1/1.json"])))
    with pytest.raises(drive.Retry, match="daily budget reached") as stopped:
        build({"unit": ".ai/units/R1/1.json", "worktree": str(root), "attempts": 0})
    assert stopped.value.counts is False


def test_a_crew_refusal_stops_at_once_with_a_card_and_is_not_retried_while_the_card_is_open(make_repo):
    root = crew_repo(make_repo)
    run = fake_run(write=False, denied=True)
    with pytest.raises(crew.CrewRefused, match="denied a tool"):
        crew.run_agent(root, "sweeper-sid", "before_cut", "R1", {"row": "R1"}, run=run)
    card = common.var(root) / "asks/crew-sweeper-sid-R1.md"
    assert card.exists() and "machinery" in card.read_text()
    with pytest.raises(crew.CrewRefused, match="close the card"):
        crew.run_agent(root, "sweeper-sid", "before_cut", "R1", {"row": "R1"}, run=run)
    assert len(run.calls) == 1
    command = run.calls[0]
    assert command[command.index("--max-turns") + 1] == "20" and command[command.index("--max-budget-usd") + 1] == "0.75"


def test_before_cut_requires_a_plan_or_records_that_planning_was_skipped(make_repo):
    root = crew_repo(make_repo, plan=False)
    with pytest.raises(crew.CrewRefused, match="no planning matrix"):
        crew.before_cut(root, "R1", "| R1 | building |", run=fake_run())
    (root / "plan/slice-matrix.json").write_text(plan_matrix("R9"))
    with pytest.raises(crew.CrewRefused, match="not a slice"):
        crew.before_cut(root, "R1", "| R1 | building |", run=fake_run())
    (root / "factory.toml").write_text('planning = "skip"\n' + (root / "factory.toml").read_text())
    (root / "plan/slice-matrix.json").unlink()
    run = fake_run()
    def run_cover(command, cwd, input, env, **kw):
        done = run(command, cwd, input, env, **kw)
        if "plan-coverage" in env["FACTORY_ROLE"]:
            Path(env["FACTORY_CREW_OUTPUT"]).write_text(json.dumps({"row": "R1", "items": [], "dropped": [], "orphaned": []}))
        return done
    result = crew.before_cut(root, "R1", "| R1 | building |", run=run_cover)
    assert result["planning"].startswith("skipped")
    assert any(e.get("event") == "planning_skipped" for e in common.read_jsonl(common.var(root) / "log.jsonl"))


def test_review_notes_are_not_triaged_at_model_cost(make_repo, monkeypatch):
    root = crew_repo(make_repo)
    started = []
    monkeypatch.setattr(crew, "run_agent", lambda *args, **kwargs: started.append(args))  # never a real model run
    (root / "plan/backlog.md").write_text("| ID | Status |\n|---|---|\n| N-R1-U1-1 | todo |\n| R2 | todo |\n")
    assert tick.triage_next(root) == "R2" and [a[3] for a in started] == ["R2"]


def test_init_shows_the_expected_cost_and_the_preset_caps(tmp_path):
    roles_project(tmp_path)
    cfg = common.config(tmp_path)
    assert (cfg["daily_budget_usd"], cfg["max_budget_review_usd"], cfg["max_budget_crew_usd"]) == (15.0, 1.5, 0.75)
    lines = probe.cost_summary(cfg)
    assert lines[0].startswith("expected model cost: about $0.57 per unit") and "units a day" in lines[1]


def test_reported_cost_comes_from_the_spend_ledger_so_a_review_is_never_counted_twice(tmp_path):
    import daily_report
    import metrics
    (tmp_path / "var/factory").mkdir(parents=True)
    common.spend(tmp_path, "reviewer", 0.16)
    common.log(tmp_path, event="end", step="review", unit="u", cost_usd=0.16)  # the review step's receipt
    common.log(tmp_path, event="crew", agent="inspector-grumble", cost_usd=0.16)  # the same run, as a crew record
    numbers = {n["name"]: n["value"] for n in metrics.factory_numbers(tmp_path)["numbers"]}
    assert numbers["Model cost recorded"] == 0.16 and daily_report.days(tmp_path)[0]["cost_usd"] == 0.16
