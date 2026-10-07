#!/usr/bin/env bash
# Install the factory's Codex skills into $CODEX_HOME/skills (default ~/.codex/skills).
# The skills are generated from the Claude Code commands (one source): ${CLAUDE_PLUGIN_ROOT} becomes this kit's path.
# Usage: bash adapters/codex/install.sh            Then, in a project: python3 <kit>/core/cli.py init --apply --preset codex-only --adapter codex
set -euo pipefail
KIT="$(cd "$(dirname "$0")/../.." && pwd -P)"
DEST="${CODEX_HOME:-$HOME/.codex}/skills"
python3 - "$KIT" "$DEST" <<'PY'
import re, sys
from pathlib import Path
kit, dest = Path(sys.argv[1]), Path(sys.argv[2])
for command in sorted((kit / "adapters/claude-code/commands").glob("*.md")):
    text = command.read_text().replace("${CLAUDE_PLUGIN_ROOT}", str(kit))
    front, body = text.split("---", 2)[1], text.split("---", 2)[2]
    description = re.search(r"^description: (.*)$", front, re.M).group(1)
    body = body.replace("$ARGUMENTS", "the arguments the person gave").replace("/factory-", "the skill factory-")
    body = body.replace("--adapter claude-code", "--adapter codex").replace("If you have the Artifact tool", "If your harness can publish an artifact")
    target = dest / command.stem / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"---\nname: {command.stem}\ndescription: {description}\n---\n"
                      f"<!-- Generated from adapters/claude-code/commands/{command.name} by adapters/codex/install.sh -->\n{body}")
    print(f"installed {target}")
PY
