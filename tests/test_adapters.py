"""Adapters: the Claude Code plugin installs from the local marketplace and sets a project up for every
preset; the Codex skills and the generic CLI call the same core; the agent guard refuses a model or a
code-only role; and a broken adapter fails its check (sabotages)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FAKES = REPO / "core/sample/fakes"
sys.path.insert(0, str(REPO / "core"))
import check_kit  # noqa: E402

MODELS = "claude-sonnet-5-5,claude-sonnet-5,claude-sonnet-4-6,claude-haiku-5,gpt-6-sol,gpt-6-astra,gpt-6-luna"
CLAUDE = shutil.which("claude")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def project(tmp_path, name="project"):
    root = tmp_path / name
    (root / "tests").mkdir(parents=True)
    (root / "tests/test_ok.py").write_text("def test_ok():\n    assert True\n")
    git(root, "init", "-q", "-b", "main")
    return root


def fake_env(home=None):
    env = dict(os.environ, PATH=f"{FAKES}{os.pathsep}{os.environ['PATH']}", FAKE_MODELS=MODELS)
    if home:
        env["HOME"] = str(home)
    return env


def test_the_kit_check_is_clean_and_the_plugin_validates():
    assert check_kit.problems(REPO) == []
    if CLAUDE:
        result = subprocess.run([CLAUDE, "plugin", "validate", "--strict", str(REPO)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """Install the plugin from the local marketplace into an isolated HOME; return the installed copy."""
    if not CLAUDE:
        pytest.skip("claude is not installed; the install path cannot be exercised here")
    home = tmp_path_factory.mktemp("home")
    env = dict(os.environ, HOME=str(home))
    for command in (["plugin", "marketplace", "add", str(REPO)], ["plugin", "install", "factory@factory-kit"]):
        result = subprocess.run([CLAUDE, *command], env=env, capture_output=True, text=True, timeout=300, cwd=home)
        assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads((home / ".claude/plugins/installed_plugins.json").read_text())
    return Path(record["plugins"]["factory@factory-kit"][0]["installPath"])


@pytest.mark.parametrize("preset, adapter, builder", [
    ("claude-only", "claude-code", "claude-sonnet-5-5"), ("codex-only", "codex", "gpt-6-sol"),
    ("claude-codex", "claude-code", "gpt-6-sol"), ("generic", "generic", "<builder-model>")])
def test_a_fresh_install_sets_up_a_project_for_each_preset(installed, tmp_path, preset, adapter, builder):
    root = project(tmp_path)
    result = subprocess.run([sys.executable, str(installed / "core/cli.py"), "init", "--apply", "--project", str(root),
                             "--preset", preset, "--adapter", adapter], env=fake_env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for path in ("factory/tick.py", "factory/crew.toml", "factory/planning/validate_matrix.py", "factory.toml",
                 ".ai/prompts/builder.v1.md", ".ai/prompts/crew/quill.v1.md", "crew/quill/memory.md",
                 "dashboard/index.html", "plan/backlog.md", "state.md", ".ai/lessons.jsonl", "var/factory/dashboard"):
        assert (root / path).exists(), path
    assert f'model = "{builder}"' in (root / "factory.toml").read_text()
    if adapter == "claude-code":
        assert "@.ai/factory-agents.md" in (root / "CLAUDE.md").read_text()
        agent = (root / ".claude/agents/builder.md").read_text() if preset == "claude-only" else ""
        assert preset != "claude-only" or "model: claude-sonnet-5-5" in agent
    else:
        assert "factory:begin" in (root / "AGENTS.md").read_text()
    if preset == "codex-only":
        assert 'model = "gpt-6-sol"' in (root / ".codex/profiles/factory-builder.config.toml").read_text()
    plan = subprocess.run([sys.executable, str(installed / "core/cli.py"), "init", "--plan", "--project", str(root),
                           "--preset", preset, "--adapter", adapter], capture_output=True, text=True)
    assert all(row["action"] != "create" for row in json.loads(plan.stdout))  # a second run changes nothing


def test_the_codex_skills_are_generated_from_the_claude_commands_and_call_the_core(tmp_path):
    subprocess.run(["bash", str(REPO / "adapters/codex/install.sh")], env=dict(os.environ, CODEX_HOME=str(tmp_path)),
                   check=True, capture_output=True)
    skills = sorted(p.parent.name for p in tmp_path.glob("skills/*/SKILL.md"))
    assert skills == sorted(p.stem for p in (REPO / "adapters/claude-code/commands").glob("*.md"))
    text = (tmp_path / "skills/factory-init/SKILL.md").read_text()
    assert f"{REPO}/core/cli.py" in text and "--adapter codex" in text and "CLAUDE_PLUGIN_ROOT" not in text


def test_the_generic_cli_drives_the_core(tmp_path):
    root = project(tmp_path)
    tool = REPO / "adapters/generic/bin/factory"
    result = subprocess.run([str(tool), "init", "--apply", "--project", str(root), "--preset", "generic",
                             "--adapter", "generic"], env=fake_env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert subprocess.run([str(tool), "tick", "--project", str(root)], capture_output=True).returncode == 0
    ticks = (root / "var/factory/ticks.log").read_text()
    assert "roles.builder.command is not set" in ticks or "must be an exact model ID" in ticks


@pytest.mark.parametrize("tool_input, code", [
    ({"subagent_type": "researcher", "prompt": "x"}, 0),
    ({"subagent_type": "researcher", "model": "opus", "prompt": "x"}, 2),
    ({"subagent_type": "factory:quill", "prompt": "x"}, 2),
    ({"subagent_type": "reviewer", "prompt": "x"}, 2),
])
def test_the_agent_guard_refuses_a_model_or_a_code_only_role(tmp_path, tool_input, code):
    (tmp_path / "factory.toml").write_text("")
    result = subprocess.run([sys.executable, str(REPO / "adapters/claude-code/hooks/agent_guard.py")],
                            input=json.dumps({"cwd": str(tmp_path), "tool_input": tool_input}), capture_output=True, text=True)
    assert result.returncode == code, result.stderr


def sabotaged(tmp_path, change):
    copy = tmp_path / "kit"
    shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    change(copy)
    return copy


@pytest.mark.parametrize("change, expected", [
    (lambda c: (c / ".claude-plugin/plugin.json").write_text("{ broken"), "plugin manifests unreadable"),
    (lambda c: (c / "adapters/claude-code/hooks/agent_guard.py").unlink(), "agent_guard.py, which does not exist"),
    (lambda c: (c / "adapters/claude-code/commands/factory-retro.md").write_text(
        (c / "adapters/claude-code/commands/factory-retro.md").read_text().replace("cli.py\" retro", "cli.py\" retrospect")),
     "calls core/cli.py retrospect"),
    (lambda c: (c / "adapters/generic/bin/factory").write_text("#!/bin/sh\nexit 3\n"), "--help fails"),
    (lambda c: (c / "adapters/codex/install.sh").unlink(), "install.sh is missing"),
    (lambda c: (c / "core/templates/prompts/crew/quill.v1.md").unlink(), "does not exist"),
])
def test_a_broken_adapter_fails_its_check(tmp_path, change, expected):
    found = check_kit.problems(sabotaged(tmp_path, change))
    assert any(expected in line for line in found), found


@pytest.mark.skipif(not CLAUDE, reason="claude is not installed")
def test_claude_plugin_validate_refuses_a_broken_manifest(tmp_path):
    copy = sabotaged(tmp_path, lambda c: (c / ".claude-plugin/plugin.json").write_text('{"name": "factory", "agents": "x"}'))
    result = subprocess.run([CLAUDE, "plugin", "validate", str(copy)], capture_output=True, text=True)
    assert result.returncode != 0
