#!/usr/bin/env bash
# Plugin Stop hook: runs the project's own factory/stop_hook.sh. A project without the factory is untouched.
cd "${CLAUDE_PROJECT_DIR:-.}" 2> /dev/null || exit 0
[ -f factory/stop_hook.sh ] || { cat > /dev/null; exit 0; }
exec bash factory/stop_hook.sh
