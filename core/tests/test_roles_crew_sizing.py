"""1.2.0: the roles file and the model probe, reviewer independence, the crew's triggers and gates,
sizing at cut time, research first, review notes as backlog rows, and the plan check."""
import json
import subprocess
import tomllib
from pathlib import Path

import pytest
from conftest import CORE, GREEN, WORK_PC, git, roles_project, unit_files

import common
import crew
import drive
import modelrun
import probe
import research_check
import review
import tick
import unit_check
from common import read_queue, write_queue
from test_clock import queue_of, runners_all, states

FIX = Path(__file__).parent / "fixtures"


def roles(text):
    return tomllib.loads(text)["roles"]


def test_the_probe_maps_requirements_to_the_models_that_answered(tmp_path):
    rows = roles_project(tmp_path, WORK_PC)
    pinned = {r["role"]: (r["model"], r["why"]) for r in rows}
    assert pinned["chief-of-staff"][0] == "claude-sonnet-5-5" and pinned["builder"][0] == "claude-sonnet-5-5"
    assert pinned["reviewer"] == ("claude-sonnet-5", "same maker, different version")
    assert pinned["summarizer"][0] == "claude-haiku-5"
    roles_project(tmp_path, ["claude-sonnet-5-5"])
    text = (tmp_path / "factory.toml").read_text()
    assert 'same_tool_review = "fresh-session"' in text and "inspector-grumble-same-tool.v1.md" in text
    with pytest.raises(probe.MappingRefused, match="role chief-of-staff needs codex"):
        roles_project(tmp_path, WORK_PC, preset="codex-only")


def test_the_probe_counts_only_models_that_really_answered(tmp_path):
    fakes = CORE / "sample/fakes"
    run = lambda cmd, **kw: subprocess.run([str(fakes / cmd[0]), *cmd[1:]], env={"PATH": "/usr/bin:/bin",
                                           "FAKE_MODELS": "claude-sonnet-5,gpt-6-luna"}, **kw)
    report = probe.probe(which=lambda name: True, run=run)
    assert report["tools"]["claude"]["answered"] == ["claude-sonnet-5"]
    assert report["tools"]["codex"]["answered"] == ["gpt-6-luna"]


@pytest.mark.parametrize("fixture, output", [("claude-json-unknown-model.json", "claude-json"),
                                             ("codex-jsonl-unknown-model.jsonl", "codex-jsonl")])
def test_a_pinned_model_that_stops_answering_stops_the_unit_with_a_card_and_no_fallback(tmp_path, fixture, output):
    real = (FIX / fixture).read_text()
    stderr = json.loads(real).get("_stderr", "") if output == "claude-json" else ""
    with pytest.raises(drive.ModelGone):
        modelrun.classify(1, real, stderr, output)
    queue_of(tmp_path, "red")

    def gone(entry):
        raise drive.ModelGone("There's an issue with the selected model (claude-sonnet-5).")
    drive.tick(tmp_path, runners_all(gone))
    assert states(tmp_path) == ["errored"]
    assert list((tmp_path / "var/factory/asks").glob("DEC-roles-*.md"))


@pytest.mark.parametrize("edit, reason", [
    (lambda t: t.replace('model = "claude-sonnet-5"\n', 'model = "sonnet"\n'), "never a moving alias"),
    (lambda t: t.replace('prompt = ".ai/prompts/builder.v1.md"', 'prompt = ".ai/prompts/builder.md"'), "versioned file"),
    (lambda t: t.replace('"--model", "{model}", "--effort"', '"--effort"'), "must pass {model}"),
    (lambda t: t.replace('form = "review-json"', 'form = "diff"'), "must produce form review-json"),
])
def test_the_roles_file_refuses_an_unpinned_or_mismatched_role(tmp_path, edit, reason):
    roles_project(tmp_path, edit=edit)
    assert reason in common.config_problem(common.config(tmp_path), tmp_path)


def test_reviewer_independence_refuses_a_reused_session_and_a_same_model_review_without_a_fresh_prompt(tmp_path):
    roles_project(tmp_path)
    assert common.config_problem(common.config(tmp_path), tmp_path) is None
    reviewer_block = lambda t, old, new: t[:t.index("[roles.reviewer]")] + t[t.index("[roles.reviewer]"):].replace(old, new, 1)
    roles_project(tmp_path, edit=lambda t: reviewer_block(t, '"--no-session-persistence", ', '"--continue", '))
    assert "reuses a session" in common.config_problem(common.config(tmp_path), tmp_path)
    roles_project(tmp_path, edit=lambda t: reviewer_block(t, '"--no-session-persistence", ', ""))
    assert "fresh session" in common.config_problem(common.config(tmp_path), tmp_path)
    roles_project(tmp_path, ["claude-sonnet-5-5"])
    cfg = common.config(tmp_path)
    assert common.config_problem(cfg, tmp_path) is None and common.review_independence(cfg)[0] == "fresh-session"
    roles_project(tmp_path, ["claude-sonnet-5-5"], edit=lambda t: t.replace("inspector-grumble-same-tool.v1.md", "builder.v1.md"))
    assert "different review prompt" in common.config_problem(common.config(tmp_path), tmp_path)


EXPECTED = {
    ("row_untriaged", ()): ["sorter-sam"],
    ("before_cut", ()): ["sweeper-sid", "plan-coverage-auditor"],
    ("plan_changed", ()): ["plan-coverage-auditor"],
    ("unit_without_brief", ("lib/util.py",)): ["quill"],
    ("check_passed", ("lib/util.py",)): ["inspector-grumble"],
    ("check_passed", ("lib/auth/login.py",)): ["inspector-grumble", "lockjaw"],
    ("check_passed", ("web/page.html",)): ["inspector-grumble", "thomasina"],
    ("row_landed", ("lib/util.py",)): ["spec-conformance-auditor", "claim-verifier"],
    ("row_landed", ("api/orders.py",)): ["spec-conformance-auditor", "thomasina", "claim-verifier"],
    ("done_claim", ()): ["claim-verifier"],
    ("handoff", ()): ["claim-verifier"],
    ("daily_report", ()): ["claim-verifier"],
    ("daily_retro", ()): ["the-bookie"],
}


@pytest.mark.parametrize("event, files", list(EXPECTED))
def test_each_trigger_starts_exactly_the_expected_agents(event, files):
    assert crew.triggered(event, {"files": list(files)}) == EXPECTED[(event, files)]
    assert crew.triggered("check_passed", {"files": ["lib/x.py"], "risk_class": "money"}) == ["inspector-grumble", "lockjaw"]


def crew_project(make_repo, sweep):
    root = make_repo({"plan/backlog.md": "| ID | Status |\n|---|---|\n| R1 | building |\n", "tests/test_ok.py": GREEN})
    roles_project(root)

    def run(command, cwd, input, env, **kw):
        name = env["FACTORY_ROLE"].split(":", 1)[1]
        forms = {"sweeper-sid": sweep, "plan-coverage-auditor": {"row": "R1", "items": [], "dropped": [], "orphaned": []}}
        Path(env["FACTORY_CREW_OUTPUT"]).write_text(json.dumps(forms[name]))
        return subprocess.CompletedProcess(command, 0, (FIX / "claude-json-real.json").read_text(), "")
    return root, run


def test_a_done_sweep_closes_the_row_only_after_code_reruns_its_evidence(make_repo):
    failing = {"row": "R1", "verdict": "done", "criterion": "C3", "evidence": "x", "evidence_command": "exit 3"}
    root, run = crew_project(make_repo, failing)
    assert crew.before_cut(root, "R1", "| R1 | building |", run=run)["already_done"] is False
    assert tick.backlog(root)["R1"] == "building"
    passing = dict(failing, evidence_command="python3 -m pytest -q tests/test_ok.py")
    root2, run2 = crew_project(lambda files: make_repo(files, "second"), passing)
    assert crew.before_cut(root2, "R1", "| R1 | building |", run=run2)["already_done"] is True
    assert tick.backlog(root2)["R1"].startswith("done")
    with pytest.raises(crew.CrewRefused, match="evidence_command"):
        crew.check_form("sweep", dict(failing, evidence_command=""), {})


def test_a_unit_is_queued_only_after_the_sweep_and_a_coverage_audit_of_the_current_plan(make_repo):
    root, run = crew_project(make_repo, {"row": "R1", "verdict": "not_done", "criterion": "NONE", "evidence": "x",
                                         "evidence_command": ""})
    assert "before-cut R1" in crew.cut_refusal(root, "R1")
    crew.before_cut(root, "R1", "| R1 | building |", run=run)
    assert crew.cut_refusal(root, "R1") is None
    (root / "plan/backlog.md").write_text((root / "plan/backlog.md").read_text() + "| R2 | todo |\n")
    assert "plan changed" in crew.cut_refusal(root, "R1")
    with pytest.raises(crew.CrewRefused):
        crew.check_form("coverage", {"items": [{"status": "MAYBE"}], "dropped": [], "orphaned": []}, {})
    assert crew.check_form("coverage", {"items": [{"status": "DROPPED"}], "dropped": [], "orphaned": []}, {}) == "dropped"


@pytest.mark.parametrize("change, reason", [
    ({"files": ["a.py", "b.py", "c.py", "d.py"]}, "at most 3 code files"),
    ({"estimate_minutes": 121}, "too big for one session"),
    ({"seam": ""}, "seam must name"),
    ({"outside_tool": True}, "reviewed research file"),
])
def test_an_oversized_or_unsized_unit_is_refused_at_cut_time(tmp_path, change, reason):
    unit = json.loads(unit_files()[".ai/units/R1/1.json"])
    (tmp_path / "u.json").write_text(json.dumps({**unit, **change}))
    with pytest.raises(unit_check.UnitRefused, match=reason):
        unit_check.check_unit(tmp_path / "u.json")


def test_a_unit_over_twice_its_estimate_is_sent_to_split(tmp_path):
    queue_of(tmp_path, "red")
    queue = read_queue(tmp_path)
    queue["units"][0]["estimate_minutes"] = 10
    write_queue(tmp_path, queue)
    drive.tick(tmp_path, runners_all(lambda e: (True, "built", {"minutes_model": 15})))
    assert states(tmp_path) == ["built"]
    queue = read_queue(tmp_path)
    queue["units"][0]["state"] = "checked"
    write_queue(tmp_path, queue)
    drive.tick(tmp_path, runners_all(lambda e: (True, "PASS", {"minutes_model": 6})))
    assert states(tmp_path) == ["needs_split"] and "over twice its estimate" in read_queue(tmp_path)["units"][0]["log"][-1]["outcome"]


def test_research_and_summary_forms_are_checked_by_code():
    good = "## Outcome\nok\n## Facts\n## Options\n## Recommendation\n## Sources\n- https://example.org/doc\n## Not verified\n"
    assert research_check.check_research(good)["ok"]
    with pytest.raises(research_check.ResearchRefused, match="Sources names no link"):
        research_check.check_research(good.replace("https://example.org/doc", "none"))
    with pytest.raises(research_check.ResearchRefused, match="heading"):
        research_check.check_summary("# Day\nall good")


def test_review_notes_become_backlog_rows_and_never_block(tmp_path):
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan/backlog.md").write_text("| ID | Status |\n|---|---|\n")
    assert review.file_notes(tmp_path, "R1-U1", ["rename x", "a | pipe"]) == 2
    assert review.file_notes(tmp_path, "R1-U1", ["rename x", "a | pipe"]) == 0
    assert tick.backlog(tmp_path) == {"N-R1-U1-1": "todo", "N-R1-U1-2": "todo"}


def test_a_plan_that_breaks_the_slice_rules_is_a_finding(tmp_path):
    import consistency
    (tmp_path / "plan").mkdir()
    bad = (CORE / "planning/slice-matrix/examples/bad-r1-hours.json").read_text()
    (tmp_path / "plan/slice-matrix.json").write_text(bad)
    (tmp_path / "var/factory").mkdir(parents=True)
    codes = {f["code"] for f in consistency.check(tmp_path)["findings"]}
    assert "plan_invalid" in codes
    (tmp_path / "plan/slice-matrix.json").write_text((CORE / "planning/slice-matrix/examples/toy.json").read_text())
    assert "plan_invalid" not in {f["code"] for f in consistency.check(tmp_path)["findings"]}
