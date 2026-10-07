#!/usr/bin/env python3
"""Check the kit repo itself: the Claude Code plugin manifests, every path an adapter refers to, every
`core/cli.py <command>` an adapter calls, the generic CLI, the Codex skill generator, the files `factory init`
copies, and that VERSION, plugin.json and the CHANGELOG agree.  Usage: check_kit.py [repo]  (exit 1 on a problem)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)")
CLI_CALL = re.compile(r"core/cli\.py\"?\s+([a-z-]+)")
PROJECT_SCRIPT = re.compile(r"python3 factory/([\w/]+\.py)")


def problems(repo):
    repo, found = Path(repo), []
    try:
        market = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
        manifest = json.loads((repo / ".claude-plugin/plugin.json").read_text())
    except (OSError, ValueError) as error:
        return [f"plugin manifests unreadable: {error}"]
    names = [p.get("name") for p in market.get("plugins", [])]
    if manifest.get("name") not in names:
        found.append(f"marketplace.json lists {names}, plugin.json names {manifest.get('name')!r}")
    version = manifest.get("version", "")
    if (repo / "VERSION").read_text().strip() != version if (repo / "VERSION").exists() else True:
        found.append(f"VERSION does not say {version}")
    top = re.search(r"^## (\d+\.\d+\.\d+)", (repo / "CHANGELOG.md").read_text(), re.M) if (repo / "CHANGELOG.md").exists() else None
    if not top or top.group(1) != version:
        found.append(f"CHANGELOG.md top entry is not {version}")
    for key in ("commands", "skills", "hooks"):
        for path in [manifest.get(key)] if isinstance(manifest.get(key), str) else manifest.get(key) or []:
            if not (repo / path).exists():
                found.append(f"plugin.json {key} path {path} does not exist")
    sys.path.insert(0, str(repo / "core"))
    try:
        cli = __import__("cli")
        commands = set(cli.COMMANDS)
        import factory_init
        found += [f"factory init copies {s.relative_to(repo)}, which does not exist"
                  for s, _ in factory_init.items() if not s.is_file()]
    finally:
        sys.path.pop(0)
        for name in ("cli", "factory_init", "agents_gen"):
            sys.modules.pop(name, None)
    import tomllib
    named = [a["prompt"] for a in tomllib.loads((repo / "core/factory/crew.toml").read_text())["agents"].values()]
    for preset in sorted((repo / "core/factory/presets").glob("*.toml")):
        named += [r["prompt"] for r in tomllib.loads(preset.read_text())["roles"].values()]
    named.append(".ai/prompts/inspector-grumble-same-tool.v1.md")
    lists = [("crew.toml", tomllib.loads((repo / "core/factory/crew.toml").read_text()))]
    lists += [(p.name, tomllib.loads(p.read_text())) for p in sorted((repo / "core/factory/presets").glob("*.toml"))]
    for source, data in lists:
        launchers = list(data.get("commands", {}).items()) + [(n, r.get("command")) for n, r in data.get("roles", {}).items()]
        rules = [t for a in data.get("agents", {}).values() for t in a.get("tools", [])]
        rules += [t for r in data.get("roles", {}).values() for t in r.get("tools", []) + r.get("deny", [])]
        for rule in rules:
            if str(rule).startswith("Write("):
                found.append(f"{source}: {rule} never matches in Claude Code; write rules are Edit(<path>)")
        for name, command in launchers:
            if not command or command[0] != "claude":
                continue
            if "--allowedTools" not in command or "--permission-mode" not in command:
                found.append(f"{source}: the claude command of {name} must carry --permission-mode and --allowedTools "
                             "(an unattended work folder is untrusted; its project allow list is ignored)")
            denied = command[command.index("--disallowedTools") + 1:] if "--disallowedTools" in command else []
            if "Edit" in denied or "Write" in denied:
                found.append(f"{source}: the claude command of {name} denies Edit or Write outright, which also blocks "
                             "the answer file the agent must write")
    for name, agent in tomllib.loads((repo / "core/factory/crew.toml").read_text())["agents"].items():
        if name == "inspector-grumble":
            continue  # it is the reviewer role; its permissions come from the roles file
        if "Edit(.factory-crew-*)" not in agent.get("tools", []):
            found.append(f"crew.toml: {name} must be allowed Edit(.factory-crew-*) to write its answer file")
        if agent.get("sandbox") == "read-only":
            found.append(f"crew.toml: {name} has a read-only Codex sandbox but must write its answer file")
    for prompt in sorted(set(named)):
        if not (repo / "core/templates/prompts" / prompt.removeprefix(".ai/prompts/")).is_file():
            found.append(f"the prompt {prompt} that a role or crew agent names does not exist in core/templates/prompts")
    for path in sorted((repo / "adapters").rglob("*")):
        if not path.is_file() or path.suffix not in (".md", ".json", ".sh", ""):
            continue
        text = path.read_text(errors="replace")
        for ref in REF.findall(text):
            if not (repo / ref).exists():
                found.append(f"{path.relative_to(repo)} refers to {ref}, which does not exist")
        for script in PROJECT_SCRIPT.findall(text):
            if not (repo / "core/factory" / script).exists() and not script.startswith("planning/"):
                found.append(f"{path.relative_to(repo)} runs factory/{script}, which the kit does not ship")
        for word in CLI_CALL.findall(text):
            if word not in commands:
                found.append(f"{path.relative_to(repo)} calls core/cli.py {word}, which is not a command")
    tool = repo / "adapters/generic/bin/factory"
    if not tool.is_file() or not os.access(tool, os.X_OK):
        found.append("adapters/generic/bin/factory is missing or not executable")
    elif subprocess.run([str(tool), "--help"], capture_output=True).returncode:
        found.append("adapters/generic/bin/factory --help fails")
    if not (repo / "adapters/codex/install.sh").is_file():
        found.append("adapters/codex/install.sh is missing")
    return found


if __name__ == "__main__":
    lines = problems(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
    print("\n".join(lines) or "kit check: clean")
    sys.exit(1 if lines else 0)
