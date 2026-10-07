#!/usr/bin/env bash
# Plugin Stop hook: the chief of staff may not end its turn while the project's records disagree.
# It runs the PLUGIN's own consistency check against the open project, never a script the project ships: any repo
# a person opens could otherwise run its own code in their session at every stop. A project without the factory
# (no factory.toml) is untouched.
PLUGIN="$(cd "$(dirname "$0")/../../.." && pwd -P)"
input=$(cat)
case "$input" in *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) exit 0 ;; esac
[ -n "${FACTORY_ROLE:-}" ] && exit 0   # builder, reviewer and crew sessions started by the clock
cd "${CLAUDE_PROJECT_DIR:-.}" 2> /dev/null || exit 0
[ -f factory.toml ] || exit 0
[ "$(git rev-parse --git-dir 2>/dev/null)" = "$(git rev-parse --git-common-dir 2>/dev/null)" ] || exit 0  # a unit work folder
python3 "$PLUGIN/core/factory/consistency.py" > /dev/null 2>&1 && exit 0
echo "Records disagree or something is stale. Run python3 factory/consistency.py and fix each finding, or write in state.md why it waits." >&2
exit 2
