"""Red check, build check, guard, unit shape and the review form."""
import json
from pathlib import Path

import pytest
from conftest import GREEN, git, unit_files

import build_check
import red_check
import review
import modelrun
import unit_check

RED = "def test_a():\n    from src.newmod import go\n    assert go() == 1\n"


def red_repo(make_repo, unit_tests, extra=None, **unit_kwargs):
    files = {"tests/test_unit.py": unit_tests, "tests/test_other.py": GREEN, **unit_files(**unit_kwargs)}
    return make_repo({**files, **(extra or {})})


def test_a_valid_red_passes_and_reports_the_suite(make_repo):
    root = red_repo(make_repo, RED + RED.replace("test_a", "test_b") + RED.replace("test_a", "test_c"))
    result = red_check.red_check(".ai/units/R1/1.json", root)
    assert {k: result[k] for k in ("ok", "red", "tolerated_red", "suite_passed")} == {
        "ok": True, "red": 3, "tolerated_red": 0, "suite_passed": 1}


@pytest.mark.parametrize("broken, reason", [
    ("def test_c():\n    undefined_helper()\n", "test_c fails on a NameError in the test file itself"),
    ("def test_c():\n    import yaml_never_installed_here\n", "importing yaml_never_installed_here, which is not"),
    ("import pytest\n@pytest.fixture\ndef boom():\n    raise OSError('x')\ndef test_c(boom):\n    pass\n",
     "test_c fails in its fixture"),
])
def test_a_red_test_broken_by_its_own_file_is_refused(make_repo, broken, reason):
    root = red_repo(make_repo, RED + RED.replace("test_a", "test_b") + broken)
    with pytest.raises(red_check.RedCheckRefused, match=reason):
        red_check.red_check(".ai/units/R1/1.json", root)


def test_other_units_red_tests_are_tolerated_by_exact_id_only(make_repo):
    other = "def test_m():\n    assert False\ndef test_m_extra():\n    assert False\n"
    root = red_repo(make_repo, RED + RED.replace("test_a", "test_b") + RED.replace("test_a", "test_c"),
                    extra={"tests/test_queued.py": other})
    with pytest.raises(red_check.RedCheckRefused, match="test_m_extra failed outside the unit"):
        red_check.red_check(".ai/units/R1/1.json", root, tolerated={"tests/test_queued.py::test_m"})
    both = {"tests/test_queued.py::test_m", "tests/test_queued.py::test_m_extra"}
    assert red_check.red_check(".ai/units/R1/1.json", root, tolerated=both)["tolerated_red"] == 2


def test_a_stopped_unit_is_tolerated_only_while_its_card_is_open(make_repo, tmp_path):
    root = make_repo({"x.txt": "x"})
    other = tmp_path / "other"
    (other / ".ai/units/R2").mkdir(parents=True)
    (other / ".ai/units/R2/1.json").write_text(json.dumps({"tests": ["tests/test_r2.py::test_x"]}))
    (root / "var/factory/asks").mkdir(parents=True)
    queue = {"units": [{"unit": ".ai/units/R2/1.json", "worktree": str(other), "state": "needs_split"}]}
    (root / "var/factory/queue.json").write_text(json.dumps(queue))
    assert red_check.tolerated_tests(root) == set()
    (root / "var/factory/asks/R2-U1.md").write_text("# R2-U1 stopped\n")
    assert red_check.tolerated_tests(root) == {"tests/test_r2.py::test_x"}


def test_a_brief_that_cites_a_runtime_or_missing_file_is_refused(make_repo):
    tests = RED + RED.replace("test_a", "test_b") + RED.replace("test_a", "test_c")
    root = red_repo(make_repo, tests, brief_extra="- Read var/factory/queue.json first.")
    with pytest.raises(red_check.RedCheckRefused, match="runtime file var/factory/queue.json"):
        red_check.red_check(".ai/units/R1/1.json", root)
    root = make_repo({"tests/test_unit.py": tests, **unit_files(brief_extra="- Read docs/missing.md.")}, "two")
    with pytest.raises(red_check.RedCheckRefused, match="docs/missing.md, which is not readable"):
        red_check.red_check(".ai/units/R1/1.json", root)


GUARDED = "def go(x):\n    if x is None or x < 0:\n        raise ValueError('bad')\n    return 1\n"
BUILT_TESTS = ("import pytest\nfrom src.newmod import go\n"
               "def test_a():\n    assert go(1) == 1\n"
               "def test_b():\n    with pytest.raises(ValueError):\n        go(None)\n"
               "def test_c():\n    assert go(2) == 1\n")


FOUR = BUILT_TESTS + "def test_d():\n    with pytest.raises(ValueError):\n        go(-1)\n"


def built_repo(make_repo, tests=BUILT_TESTS, name="repo"):
    names = ("a", "b", "c", "d") if "test_d" in tests else ("a", "b", "c")
    root = make_repo({"tests/test_unit.py": tests, "src/__init__.py": "", **unit_files(tests=names)}, name)
    base = git(root, "rev-parse", "HEAD")
    (root / "src/newmod.py").write_text(GUARDED)
    return root, base


def test_the_guard_refuses_a_check_no_named_test_protects(make_repo):
    root, base = built_repo(make_repo)
    with pytest.raises(build_check.BuildCheckRefused, match=r"src/newmod.py:2 \(`x < 0` removed\)"):
        build_check.build_check(".ai/units/R1/1.json", root, base)
    root, base = built_repo(make_repo, FOUR, "four")
    assert build_check.build_check(".ai/units/R1/1.json", root, base, guard=True)["guard"]["checks"] == 3


def test_build_check_refuses_changed_tests_and_files_outside_the_list(make_repo):
    root, base = built_repo(make_repo, FOUR)
    (root / "notes.txt").write_text("stray")
    with pytest.raises(build_check.BuildCheckRefused, match="notes.txt is outside the file list"):
        build_check.build_check(".ai/units/R1/1.json", root, base)
    (root / "notes.txt").unlink()
    with open(root / "tests/test_unit.py", "a") as stream:
        stream.write("\n")
    with pytest.raises(build_check.BuildCheckRefused, match="tests/test_unit.py changed"):
        build_check.build_check(".ai/units/R1/1.json", root, base)


@pytest.mark.parametrize("change, reason", [
    ({"files": ["a.py", "b.py", "c.py", "d.py"]}, "at most 3 code files"),
    ({"tests": ["t.py::test_a"]}, "3 to 5 tests"),
    ({"paragraph": "Edit src/x.py. Sabotage: none."}, "code or a file path"),
    ({"paragraph": "Does a thing."}, "one sabotage"),
    ({"files": ["state.md"]}, "may not touch state.md"),
])
def test_the_unit_shape_check_refuses_each_rule(tmp_path, change, reason):
    unit = json.loads(unit_files()[".ai/units/R1/1.json"])
    (tmp_path / "u.json").write_text(json.dumps({**unit, **change}))
    with pytest.raises(unit_check.UnitRefused, match=reason):
        unit_check.check_unit(tmp_path / "u.json")


def finding(**change):
    base = {"kind": "test_weakened", "test_or_paragraph_line": "t", "file": "a.py", "line": 3,
            "reproduce_command": "pytest t"}
    return {**base, **change}


def test_code_decides_the_verdict_from_complete_findings_inside_the_unit():
    form = {"verdict": "REJECT", "suite_result_seen": True, "notes": [],
            "high": [finding(file="other.py"), finding(line=0), finding(kind="style")]}
    parsed = review.parse(form, ["a.py"])
    assert parsed["verdict"] == "PASS" and len(parsed["notes"]) == 3
    parsed = review.parse({**form, "high": [finding(cut=True)]}, ["a.py"])
    assert parsed["verdict"] == "REJECT" and parsed["cut"] is True
    with pytest.raises(review.FormInvalid, match="did not see the whole suite"):
        review.parse({**form, "suite_result_seen": False}, ["a.py"])


def test_cost_and_tokens_are_read_from_a_real_claude_json_answer():
    real = (Path(__file__).parent / "fixtures/claude-json-real.json").read_text()
    text, extra = modelrun.claude_usage(real)
    assert text == "ok" and extra["cost_usd"] > 0 and extra["output_tokens"] == 42 and extra["turns"] == 1
    assert modelrun.claude_usage("plain words") == ("plain words", {})


def test_landing_runs_the_suite_on_the_unit_merged_with_the_newest_main(make_repo):
    import land
    root = make_repo({"tests/test_ok.py": GREEN})
    git(root, "checkout", "-q", "-b", "unit")
    (root / "feature.py").write_text("X = 1\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "unit")
    git(root, "checkout", "-q", "main")
    (root / "tests/test_main.py").write_text("def test_new_on_main():\n    from feature import X\n    assert X == 2\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "main moved")
    main = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "unit")
    with pytest.raises(land.LandRefused, match="test_new_on_main fails on the merged result"):
        land.merged_suite(root, main, tolerated=())
    land.merged_suite(root, main, tolerated={"tests/test_main.py::test_new_on_main"})
    assert git(root, "worktree", "list").count("\n") == 0  # the temporary worktree is gone
