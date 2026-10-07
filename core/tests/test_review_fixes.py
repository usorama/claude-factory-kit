"""Fixes from the independent review: machinery vs unit failures, pauses and budgets, retry cap,
toolchain pin, landing modes, scrubbed test runs, brief check, one clock per repo, lessons, defects."""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import GREEN, brief, git, roles_project, unit_files, unit_worktree

import brief_check
import common
import consistency
import drive
import fingerprint
import land
import lessons
import metrics
import runners
import testrun
import tick
from common import read_queue, write_queue
from test_clock import queue_of, runners_all, states

REAL = (Path(__file__).parent / "fixtures/claude-json-real.json").read_text()


def answer(**change):
    return json.dumps({**json.loads(REAL), **change})


@pytest.mark.parametrize("code, stdout, stderr, kind", [
    (0, answer(is_error=True, subtype="error_during_execution"), "", drive.RetryOnce),
    (0, answer(subtype="error_max_turns"), "", drive.RetryOnce),
    (1, "", "Not logged in. Please run /login", drive.RetryOnce),
    (1, answer(is_error=True, result="Claude usage limit reached. Your limit will reset at 5pm"), "", drive.UsageLimit),
    (0, answer(api_error_status=429, is_error=True), "", drive.UsageLimit),
])
def test_a_model_or_machinery_failure_is_never_the_units_fault(code, stdout, stderr, kind):
    assert runners.classify(0, REAL, "")[0] == "ok"
    with pytest.raises(kind):
        runners.classify(code, stdout, stderr)


def test_a_builder_stopped_by_a_denied_tool_uses_no_attempt(make_repo, tmp_path):
    root = make_repo({"tests/test_unit.py": GREEN, "src/__init__.py": "", **unit_files()})
    fake = tmp_path / "fake-claude"
    denied = answer(result="I could not run the tests", permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "make"}}])
    fake.write_text(f"#!/bin/sh\ncat > /dev/null\ncat <<'EOF'\n{denied}\nEOF\n")
    fake.chmod(0o755)
    roles_project(root, edit=lambda text: text.replace('command = ["claude", "-p"', f'command = ["{fake}", "-p"', 1))
    build = runners.make_runners(root)["build"]
    entry = {"unit": ".ai/units/R1/1.json", "worktree": str(unit_worktree(root)), "attempts": 0}
    with pytest.raises(drive.RetryOnce, match="denied a tool"):
        build(entry)
    assert "--max-turns" in common.config(root)["roles"]["builder"]["command"]


def test_a_usage_limit_pauses_model_steps_and_the_daily_budget_holds_them_with_one_card(clock_repo):
    root = clock_repo
    queue_of(root, "red")

    def limited(entry):
        raise drive.UsageLimit("usage limit reached")
    drive.tick(root, runners_all(limited))
    entry = read_queue(root)["units"][0]
    assert entry["state"] == "red" and entry["attempts"] == 0 and common.paused_until(root)
    assert tick.tick_once(root, runners_all(limited))["held"] == 1
    (common.var(root) / "paused-until").unlink()
    common.spend(root, "builder", 99.0)  # every model run's cost goes to the spend ledger
    line = tick.tick_once(root, runners_all(limited))
    assert line["held"] == 1 and line["idle_reason"].startswith("daily budget reached")
    tick.tick_once(root, runners_all(limited))
    assert len(list((common.var(root) / "asks").glob("DEC-budget-*.md"))) == 1


def test_retries_are_capped_but_waiting_for_a_pr_never_stops_the_unit(tmp_path):
    queue_of(tmp_path, "reviewed")

    def moved(entry):
        raise drive.Retry("main moved")
    for _ in range(common.DEFAULTS["max_retries"]):
        drive.tick(tmp_path, runners_all(moved))
    assert states(tmp_path) == ["reviewed"]
    drive.tick(tmp_path, runners_all(moved))
    assert states(tmp_path) == ["errored"]
    queue_of(tmp_path, "pr_open")
    for _ in range(6):
        drive.tick(tmp_path, runners_all(lambda e: (_ for _ in ()).throw(drive.Retry("waits", counts=False))))
    assert states(tmp_path) == ["pr_open"]


def test_the_clock_refuses_another_host_and_a_reviewer_that_is_the_builder(clock_repo):
    text = (clock_repo / "factory.toml").read_text()
    (clock_repo / "factory.toml").write_text('clock_host = "some-other-host"\n' + text)
    assert "not the clock host" in tick.tick_once(clock_repo, {})["skipped"]
    same = text.replace('model = "claude-sonnet-5"\n', 'model = "claude-sonnet-5-5"\n')
    (clock_repo / "factory.toml").write_text(f'clock_host = "{socket.gethostname()}"\n' + same)
    assert "the builder and the reviewer are the same model" in tick.tick_once(clock_repo, {})["skipped"]
    report = consistency.check(clock_repo, consistency.parse_time(common.now()))
    assert "ticks_skipped" not in {f["code"] for f in report["findings"]}
    tick.tick_once(clock_repo, {})
    report = consistency.check(clock_repo, consistency.parse_time(common.now()))
    assert "ticks_skipped" in {f["code"] for f in report["findings"]}


def test_a_patch_update_only_warns_and_a_minor_update_blocks():
    pinned = {"claude": "2.1.290 (Claude Code)", "python": "3.12.3"}
    assert fingerprint.differences(pinned, {"claude": "2.1.301 (Claude Code)", "python": "3.12.3"}) == (
        [], ["claude: pinned '2.1.290 (Claude Code)', found '2.1.301 (Claude Code)'"])
    blocking, _ = fingerprint.differences(pinned, {"claude": "2.2.0 (Claude Code)", "python": "3.12.3"})
    assert blocking and blocking[0].startswith("claude")


def test_a_failing_gh_call_is_a_clean_refusal_with_its_reason_and_the_pr_state_is_read(tmp_path):
    fake = tmp_path / "gh"
    fake.write_text("#!/bin/sh\nif [ \"$2\" = view ]; then echo '{\"state\": \"MERGED\"}'; exit 0; fi\n"
                    "echo 'Base branch policy prohibits the merge' >&2; exit 1\n")
    fake.chmod(0o755)
    with pytest.raises(land.GhFailed, match="Base branch policy prohibits the merge"):
        land.gh_call(str(fake), tmp_path, "pr", "merge", "1")
    assert land.pr_state(tmp_path, "https://github.example/o/r/pull/7", str(fake)) == "MERGED"


def test_the_units_code_runs_without_tokens_and_with_a_temporary_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "secret-value")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "secret-value")
    (tmp_path / "test_env.py").write_text(
        "import os\ndef test_env():\n    assert 'secret-value' not in repr(dict(os.environ))\n"
        f"    assert os.environ['HOME'] != {str(Path.home())!r}\n")
    code, records, _, output = testrun.run(tmp_path)
    assert code == 0, output


@pytest.mark.skipif(testrun.NETWORK_ISOLATION == "none", reason="no network isolation on this host")
def test_the_units_code_cannot_reach_the_network(tmp_path):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    (tmp_path / "test_net.py").write_text(
        "import socket, pytest\ndef test_net():\n    with pytest.raises(OSError):\n"
        f"        socket.create_connection(('127.0.0.1', {port}), timeout=2)\n")
    code, _, _, output = testrun.run(tmp_path)
    server.close()
    assert code == 0, output


@pytest.mark.parametrize("drop, extra, reason", [
    (6, "", "lacks section"),
    (None, "WRONG", "is not one of the unit's tests"),
    (5, "", "lacks section"),
])
def test_the_brief_check_refuses_a_brief_without_its_parts(drop, extra, reason):
    unit = {"tests": ["tests/test_a.py::test_a"]}
    text = brief("tests/test_other.py::test_b" if extra else unit["tests"][0], drop=drop)
    with pytest.raises(brief_check.BriefRefused, match=reason):
        brief_check.check_brief(text, unit)
    no_sabotage = brief(unit["tests"][0]).replace("- Named sabotage: remove the check; that test goes red.", "")
    with pytest.raises(brief_check.BriefRefused, match="names no sabotage"):
        brief_check.check_brief(no_sabotage, unit)
    assert brief_check.check_brief(brief(unit["tests"][0]), unit)["ok"]


def test_strikes_and_the_daily_cap_are_counted_by_code(tmp_path):
    lessons.main(["add", "L1", "--title", "t", "--lesson", "l", "--shape", "check"], root=tmp_path)
    lessons.main(["add", "L2", "--title", "t", "--lesson", "l", "--shape", "rule"], root=tmp_path)
    lessons.main(["add", "L3", "--title", "t", "--lesson", "l", "--shape", "rule"], root=tmp_path)
    assert lessons.strike(tmp_path, "L1", "2026-10-01")["status"] == "open"
    assert lessons.strike(tmp_path, "L1", "2026-10-09")["status"] == "open"  # eight days apart
    assert lessons.strike(tmp_path, "L1", "2026-10-10")["status"] == "ready"
    with pytest.raises(lessons.LessonRefused, match="needs 2 strikes"):
        lessons.apply(tmp_path, "L2", "x", "2026-10-10")
    for ident in ("L2", "L3"):
        lessons.strike(tmp_path, ident, "2026-10-10")
        lessons.strike(tmp_path, ident, "2026-10-10")
    lessons.apply(tmp_path, "L1", "PR 1", "2026-10-10")
    lessons.apply(tmp_path, "L2", "PR 2", "2026-10-10")
    with pytest.raises(lessons.LessonRefused, match="already 2 changes"):
        lessons.apply(tmp_path, "L3", "PR 3", "2026-10-10")


def test_an_escaped_defect_is_recorded_only_for_a_landed_unit_and_counted(tmp_path):
    queue_of(tmp_path, "landed", "red")
    with pytest.raises(tick.Refused, match="has not landed"):
        tick.defect(tmp_path, ".ai/units/R1/1.json", "x")
    tick.defect(tmp_path, ".ai/units/R0/1.json", "wrong total on main")
    numbers = {n["name"]: n["value"] for n in metrics.factory_numbers(tmp_path)["numbers"]}
    assert numbers["Escaped defects"] == 1
