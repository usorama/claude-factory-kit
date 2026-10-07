#!/usr/bin/env bash
# Claude Code Stop hook (.claude/settings.json): the orchestrator may not end its turn while
# records disagree or something is stale. It blocks once; on the second stop it lets go, so a
# finding that cannot be fixed now never traps the session in a loop.
input=$(cat)
case "$input" in *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) exit 0 ;; esac
[ -n "${FACTORY_ROLE:-}" ] && exit 0   # builder and reviewer sessions started by the clock
[ "$(git rev-parse --git-dir 2>/dev/null)" = "$(git rev-parse --git-common-dir 2>/dev/null)" ] || exit 0  # a unit work folder
[ -f factory/consistency.py ] || exit 0
python3 factory/consistency.py > /dev/null 2>&1 && exit 0
echo "Records disagree or something is stale. Run python3 factory/consistency.py and fix each finding, or write in state.md why it waits." >&2
exit 2
