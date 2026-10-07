"""1.2.2: on a GitHub origin the factory opens and merges its own pull requests and never pushes to the base
unless factory.toml says landing = "direct". The fake gh answers in the shapes of a real gh run
(fixtures/gh-api-protection-real.json); the protected-branch answer follows the GitHub REST docs (no real capture)."""
import json
import os
from pathlib import Path

import pytest
from conftest import GREEN, git, roles_project

import common
import factory_init
import land
import metrics

REAL = json.loads((Path(__file__).parent / "fixtures/gh-api-protection-real.json").read_text())
PROTECTED = json.dumps({"required_pull_request_reviews": {"required_approving_review_count": 1},
                        "required_status_checks": {"strict": True, "contexts": ["ci"]}})


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    """A gh on PATH. protection: 'open' (the real 404 shape), 'protected' (docs shape), 'forbidden'.
    enterprise: hosts gh is signed in to besides github.com. Every call is recorded."""
    folder = tmp_path / "fakebin"
    folder.mkdir()
    state = {"protection": "open", "enterprise": [], "log": tmp_path / "gh-calls.jsonl"}

    def write():
        answers = {"open": (REAL["not_protected"]["stdout"], REAL["not_protected"]["stderr"], 1),
                   "protected": (PROTECTED, "", 0), "forbidden": ('{"message":"Must have admin rights"}', "HTTP 403", 1)}
        out, err, code = answers[state["protection"]]
        script = f"""#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
open({str(state["log"])!r}, "a").write(json.dumps(args) + "\\n")
if args[:2] == ["auth", "status"]:
    sys.exit(0 if args[-1] in {state["enterprise"]!r} + ["github.com"] else 1)
if args[:1] == ["api"]:
    print({out!r}); print({err!r}, file=sys.stderr); sys.exit({code})
if args[:2] == ["pr", "create"]:
    print("https://github.example/o/r/pull/7")
"""
        (folder / "gh").write_text(script)
        (folder / "gh").chmod(0o755)
    state["write"] = write
    write()
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    return state


def repo_with_origin(make_repo, url, name="repo"):
    root = make_repo({"tests/test_ok.py": GREEN}, name)
    git(root, "remote", "add", "origin", url)
    return root


@pytest.mark.parametrize("protection, expected", [("open", "pr_merge"), ("protected", "auto"), ("forbidden", "pr_merge")])
def test_a_github_origin_lands_by_pull_request_and_a_protected_base_by_auto_merge(make_repo, fake_gh, protection, expected):
    fake_gh["protection"] = protection
    fake_gh["write"]()
    root = repo_with_origin(make_repo, "https://github.com/acme/tool.git")
    plan = land.landing_plan(root)
    assert plan["github"] and plan["landing"] == expected
    assert ("could not be read" in plan["why"]) == (protection == "forbidden")
    calls = [json.loads(l) for l in fake_gh["log"].read_text().splitlines()]
    assert ["api", "repos/acme/tool/branches/main/protection"] in calls


def test_direct_is_the_default_only_without_a_github_host_and_init_says_why(make_repo, fake_gh):
    fake_gh["enterprise"] = ["ghe.example.com"]
    fake_gh["write"]()
    enterprise = repo_with_origin(make_repo, "git@ghe.example.com:acme/tool.git", "ghe")
    assert land.landing_plan(enterprise)["landing"] == "pr_merge"
    gitlab = repo_with_origin(make_repo, "https://gitlab.example.com/acme/tool.git", "gitlab")
    plan = land.landing_plan(gitlab)
    assert plan["landing"] == "direct" and "not a GitHub host" in plan["why"]
    assert land.effective_landing(gitlab, {"landing": ""}) == ("direct", "default for a non-GitHub origin (gitlab.example.com)")
    assert land.effective_landing(enterprise, {"landing": ""})[0] == "pr_merge"
    assert land.effective_landing(enterprise, {"landing": "direct"}) == ("direct", "set in factory.toml")


REPORT = {"at": "t", "tools": {"claude": {"available": True, "answered": ["claude-sonnet-5-5", "claude-sonnet-5"]},
                               "codex": {"available": False, "answered": []}}}


def test_init_writes_the_github_landing_into_factory_toml_and_shows_the_mode_in_use(make_repo, fake_gh):
    github = repo_with_origin(make_repo, "https://github.com/acme/tool.git", "gh-init")
    done = factory_init.apply(github, preset="claude-only", adapter="claude-code", probe_report=REPORT)
    assert 'landing = "pr_merge"' in (github / "factory.toml").read_text()
    assert any(line.startswith("landing in use: pr_merge (set in factory.toml)") for line in done)
    local = make_repo({"tests/test_ok.py": GREEN}, "local-init")
    done = factory_init.apply(local, preset="claude-only", adapter="claude-code", probe_report=REPORT)
    assert "\nlanding = " not in (local / "factory.toml").read_text()
    assert any("landing in use: direct" in line for line in done)


@pytest.fixture
def unit_on_github(make_repo, tmp_path):
    """A unit branch whose origin is configured as GitHub, rewritten by git (insteadOf) to a local bare repo, so no
    network is used while the factory sees a GitHub origin."""
    root = make_repo({"tests/test_ok.py": GREEN}, "unit")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "remote", "set-url", "origin", "https://github.com/acme/tool.git")
    git(root, "config", f"url.{bare}.insteadOf", "https://github.com/acme/tool.git")
    git(root, "checkout", "-q", "-b", "unit/R1/1")
    (root / "feature.py").write_text("X = 1\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "unit")
    return root, bare


UNIT = {"paragraph": "Adds X. Sabotage: remove it.", "title": "Add X", "tests": ["tests/test_ok.py::test_ok"],
        "files": ["feature.py"]}


def test_no_mode_pushes_to_the_base_of_a_github_origin_unless_direct_is_explicit(unit_on_github, fake_gh):
    root, bare = unit_on_github
    before = git(bare, "rev-parse", "main")
    with pytest.raises(land.DirectToGitHubRefused, match='landing = "direct"'):
        land.land(root, UNIT, "main", (), "PASS", mode="direct", direct_explicit=False)
    assert git(bare, "rev-parse", "main") == before
    landed, merged = land.land(root, UNIT, "main", (), "PASS", mode="direct", direct_explicit=True)
    assert merged and git(bare, "rev-parse", "main") == landed


def test_pr_merge_opens_a_pull_request_with_the_review_verdict_and_merges_it_itself(unit_on_github, fake_gh):
    root, bare = unit_on_github
    base_before = git(bare, "rev-parse", "main")
    pr, merged = land.land(root, UNIT, "main", (), "PASS\nnote: rename x", mode="pr_merge")
    calls = [json.loads(l) for l in fake_gh["log"].read_text().splitlines()]
    create = next(c for c in calls if c[:2] == ["pr", "create"])
    assert "Factory review verdict:\nPASS\nnote: rename x" in create[create.index("--body") + 1]
    merge = next(c for c in calls if c[:2] == ["pr", "merge"])
    assert merged and "--auto" not in merge and "--match-head-commit" in merge
    assert git(bare, "rev-parse", "main") == base_before  # the base changed only through the PR, never a push
    assert git(bare, "rev-parse", "unit/R1/1") == git(root, "rev-parse", "HEAD")


def test_the_dashboard_shows_the_landing_mode_in_use(tmp_path):
    roles_project(tmp_path)
    (tmp_path / "var/factory").mkdir(parents=True, exist_ok=True)
    assert metrics.now_section(tmp_path)["landing"] == {"mode": "direct", "why": "default for a non-GitHub origin (none)"}
    (tmp_path / "factory.toml").write_text('landing = "pr_merge"\n' + (tmp_path / "factory.toml").read_text())
    assert metrics.now_section(tmp_path)["landing"]["mode"] == "pr_merge"


def test_the_dashboard_stays_local_unless_factory_toml_allows_publishing(tmp_path):
    import build_dashboard
    roles_project(tmp_path)
    (tmp_path / "factory").mkdir(exist_ok=True)
    for name in ("common.py", "tomlw.py"):
        (tmp_path / "factory" / name).write_text((Path(__file__).resolve().parents[1] / "factory" / name).read_text())
    (tmp_path / "factory/presets").mkdir()
    (tmp_path / "factory/presets/claude-only.toml").write_text(
        (Path(__file__).resolve().parents[1] / "factory/presets/claude-only.toml").read_text())
    assert build_dashboard.publish_setting(tmp_path) == "local"
    (tmp_path / "factory.toml").write_text('dashboard_publish = "artifact"\n' + (tmp_path / "factory.toml").read_text())
    assert build_dashboard.publish_setting(tmp_path) == "artifact"
