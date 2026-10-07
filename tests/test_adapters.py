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
    """A team repo with history, as init finds it."""
    root = tmp_path / name
    (root / "tests").mkdir(parents=True)
    (root / "tests/test_ok.py").write_text("def test_ok():\n    assert True\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "team")
    return root


def fake_env(home=None):
    env = dict(os.environ, PATH=f"{FAKES}{os.pathsep}{os.environ['PATH']}", FACTORY_FAKE_MODELS=MODELS)
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
                 ".ai/prompts/builder.v1.md", ".ai/prompts/crew/quill.v1.md", "crew/quill/AGENT.md",
                 "dashboard/index.html", "plan/backlog.md", "state.md", ".ai/lessons.jsonl", "var/factory/dashboard"):
        assert (root / path).exists(), path
    assert f'model = "{builder}"' in (root / "factory.toml").read_text()
    # personal setup, the default: nothing tracked changed and nothing new shows to git
    assert subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout == ""
    assert not (root / "CLAUDE.md").exists() and not (root / "AGENTS.md").exists() and not (root / ".gitignore").exists()
    assert not (root / ".claude/settings.json").exists()
    if adapter == "claude-code":
        assert "@.ai/factory-agents.md" in (root / "CLAUDE.local.md").read_text()
        assert (root / ".claude/settings.local.json").exists()
        agent = (root / ".claude/agents/builder.md").read_text() if preset == "claude-only" else ""
        assert preset != "claude-only" or "model: claude-sonnet-5-5" in agent
    if preset == "codex-only":
        assert 'model = "gpt-6-sol"' in (root / ".codex/profiles/factory-builder.config.toml").read_text()
    plan = subprocess.run([sys.executable, str(installed / "core/cli.py"), "init", "--plan", "--project", str(root),
                           "--preset", preset, "--adapter", adapter], capture_output=True, text=True)
    assert all(row["action"] != "create" for row in json.loads(plan.stdout))  # a second run changes nothing


def test_a_shared_setup_writes_the_team_files_only_when_asked_and_a_personal_one_refuses_tracked_targets(tmp_path):
    shared = project(tmp_path, "shared")
    result = subprocess.run([sys.executable, str(REPO / "core/cli.py"), "init", "--apply", "--project", str(shared),
                             "--footprint", "shared"], env=fake_env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "@.ai/factory-agents.md" in (shared / "CLAUDE.md").read_text() and (shared / ".claude/settings.json").exists()
    assert "var/factory/" in (shared / ".gitignore").read_text().splitlines()
    assert "var/" not in (shared / ".gitignore").read_text().splitlines()  # a project's own var/ stays visible
    team = project(tmp_path, "team")
    (team / "factory").mkdir()
    (team / "factory/tick.py").write_text("# the team's own file\n")
    git(team, "add", "-A")
    git(team, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "team")
    result = subprocess.run([sys.executable, str(REPO / "core/cli.py"), "init", "--apply", "--project", str(team)],
                            env=fake_env(), capture_output=True, text=True)
    assert result.returncode == 2 and "is tracked by the team's repository" in result.stderr
    assert (team / "factory/tick.py").read_text() == "# the team's own file\n"


def test_a_setup_without_the_clone_flag_says_exactly_how_to_mark_the_clone_and_that_step_works(tmp_path):
    root = project(tmp_path)
    git(root, "config", "user.name", "Test Person")
    git(root, "config", "user.email", "person@example.invalid")
    init = [sys.executable, str(REPO / "core/cli.py"), "init", "--apply", "--project", str(root)]
    first = subprocess.run(init, env=fake_env(), capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert "factory init --apply --factory-clone" in next(l for l in json.loads(first.stdout) if l.startswith("next:"))
    tick = subprocess.run([sys.executable, "factory/tick.py", "tick"], cwd=root, capture_output=True, text=True)
    assert "factory init --apply --factory-clone" in tick.stdout + tick.stderr  # the refusal names the same step
    again = subprocess.run([*init, "--factory-clone"], env=fake_env(), capture_output=True, text=True)
    assert again.returncode == 0 and (root / ".factory-clone").is_file()
    assert not any(l.startswith("next:") for l in json.loads(again.stdout))
    tick = subprocess.run([sys.executable, "factory/tick.py", "tick"], cwd=root, capture_output=True, text=True)
    assert "factory's clone" not in tick.stdout + tick.stderr


def test_a_shared_setup_never_puts_its_hook_in_a_team_hooks_folder(tmp_path):
    root = project(tmp_path)
    git(root, "config", "core.hooksPath", ".husky/_")
    result = subprocess.run([sys.executable, str(REPO / "core/cli.py"), "init", "--apply", "--project", str(root),
                             "--footprint", "shared"], env=fake_env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (root / ".husky").exists() and "core.hooksPath is set" in result.stdout


def test_an_outdated_project_copy_is_reported_and_one_command_refreshes_it(tmp_path):
    root, home = project(tmp_path), tmp_path / "home"
    home.mkdir()
    cli = [sys.executable, str(REPO / "core/cli.py"), "init", "--apply", "--project", str(root)]
    assert subprocess.run(cli, env=fake_env(home), capture_output=True, text=True).returncode == 0
    (root / "factory/VERSION").write_text("1.0.0\n")  # as if the kit was updated after this project was set up
    (root / "factory/tick.py").write_text((root / "factory/tick.py").read_text() + "# an old line\n")
    check = subprocess.run([sys.executable, "factory/consistency.py"], cwd=root, env=fake_env(home), capture_output=True, text=True)
    assert "kit_outdated" in check.stdout and "factory init --apply --update" in check.stdout
    assert subprocess.run([*cli, "--update"], env=fake_env(home), capture_output=True, text=True).returncode == 0
    assert (root / "factory/tick.py").read_text() == (REPO / "core/factory/tick.py").read_text()
    check = subprocess.run([sys.executable, "factory/consistency.py"], cwd=root, env=fake_env(home), capture_output=True, text=True)
    assert "kit_outdated" not in check.stdout


def test_the_codex_skills_are_generated_from_the_claude_commands_and_call_the_core(tmp_path):
    subprocess.run(["bash", str(REPO / "adapters/codex/install.sh")], env=dict(os.environ, CODEX_HOME=str(tmp_path)),
                   check=True, capture_output=True)
    skills = sorted(p.parent.name for p in tmp_path.glob("skills/*/SKILL.md"))
    assert skills == sorted(p.stem for p in (REPO / "adapters/claude-code/commands").glob("*.md"))
    text = (tmp_path / "skills/factory-init/SKILL.md").read_text()
    assert f"{REPO}/core/cli.py" in text and "--adapter codex" in text and "CLAUDE_PLUGIN_ROOT" not in text


def test_the_codex_skills_keep_any_install_path_intact(tmp_path):
    kit = tmp_path / "my code-projects" / "factory-kit"  # spaces, dashes and a "/factory-" inside the path
    shutil.copytree(REPO, kit, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    subprocess.run(["bash", str(kit / "adapters/codex/install.sh")], env=dict(os.environ, CODEX_HOME=str(tmp_path / "codex")),
                   check=True, capture_output=True)
    text = (tmp_path / "codex/skills/factory-init/SKILL.md").read_text()
    assert f'python3 "{kit}/core/cli.py"' in text and "projectsthe skill" not in text
    assert "the skill factory-install-clock" in (tmp_path / "codex/skills/factory-init/SKILL.md").read_text()


def test_the_generic_cli_drives_the_core(tmp_path):
    root = project(tmp_path)
    tool = REPO / "adapters/generic/bin/factory"
    result = subprocess.run([str(tool), "init", "--apply", "--project", str(root), "--preset", "generic",
                             "--adapter", "generic"], env=fake_env(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert subprocess.run([str(tool), "tick", "--project", str(root)], capture_output=True).returncode == 0
    ticks = (root / "var/factory/ticks.log").read_text()
    assert "is not the factory's clone" in ticks  # not the factory's own clone: nothing runs
    (root / ".factory-clone").write_text("")
    subprocess.run([str(tool), "tick", "--project", str(root)], capture_output=True)
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


def edit(path, old, new):
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))


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
    (lambda c: edit(c / "core/factory/crew.toml", '"Bash(git commit *)", "WebFetch"', '"Bash(git commit *)", "Edit", "WebFetch"'),
     "denies Edit or Write outright"),
    (lambda c: edit(c / "core/factory/crew.toml", '"Edit(.ai/specs/*)"', '"Write(.ai/specs/*)"'), "never matches in Claude Code"),
    (lambda c: edit(c / "core/factory/crew.toml", '"Bash(ls *)", "Edit(.factory-crew-*)"]\nsandbox = "workspace-write"\n\n[agents.sweeper-sid]',
                    '"Bash(ls *)"]\nsandbox = "workspace-write"\n\n[agents.sweeper-sid]'), "sorter-sam must be allowed Edit"),
    (lambda c: edit(c / "core/factory/presets/claude-only.toml", '"--allowedTools", ', ''), "must carry --permission-mode and --allowedTools"),
    (lambda c: edit(c / "core/factory/presets/claude-only.toml", '"{run_tests}"', '"Bash(python3 -m pytest *)"'),
     "lets a model run code unfenced"),
    (lambda c: edit(c / "core/factory/crew.toml", '"{run_tests}"', '"Bash"'), "lets a model run code unfenced"),
    (lambda c: edit(c / "core/templates/claude/settings.json", '"Edit(./.ai/prompts/**)",', ''), "must deny Edit(./.ai/prompts/**)"),
    (lambda c: edit(c / "adapters/claude-code/commands/factory-retro.md", "allowed-tools:", "allowed-tools: Bash(factory approve --yes),"),
     "pre-approves approve"),
    (lambda c: edit(c / "adapters/claude-code/commands/factory-retro.md", "allowed-tools:", "allowed-tools: Bash(python3 factory/*),"),
     "pre-approves every factory script"),
])
def test_a_broken_adapter_fails_its_check(tmp_path, change, expected):
    found = check_kit.problems(sabotaged(tmp_path, change))
    assert any(expected in line for line in found), found


@pytest.mark.skipif(not CLAUDE, reason="claude is not installed")
def test_claude_plugin_validate_refuses_a_broken_manifest(tmp_path):
    copy = sabotaged(tmp_path, lambda c: (c / ".claude-plugin/plugin.json").write_text('{"name": "factory", "agents": "x"}'))
    result = subprocess.run([CLAUDE, "plugin", "validate", str(copy)], capture_output=True, text=True)
    assert result.returncode != 0


def test_the_plugin_stop_hook_never_runs_a_script_the_project_ships(tmp_path):
    root = project(tmp_path)
    (root / "factory").mkdir()
    planted = tmp_path / "planted-ran.txt"
    (root / "factory/stop_hook.sh").write_text(f"#!/bin/sh\necho ran > {planted}\n")
    (root / "factory/consistency.py").write_text(f"open({str(planted)!r}, 'w').write('ran')\n")
    (root / "factory.toml").write_text("")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env.pop("FACTORY_ROLE", None)
    subprocess.run(["bash", str(REPO / "adapters/claude-code/hooks/stop_hook.sh")], input="{}", env=env,
                   capture_output=True, text=True, cwd=root)
    assert not planted.exists()
