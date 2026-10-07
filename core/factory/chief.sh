#!/usr/bin/env bash
# Start the Chief of Staff: the role AND its loop, with the model pinned in factory.toml (never a default).
# Usage: factory/chief.sh [--print] [extra harness arguments, for example --remote-control <name>]
# Keep it running: tmux new -d -s factory "<repo>/factory/chief.sh"
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
[ -f "$HOME/.factory-env.sh" ] && . "$HOME/.factory-env.sh"
cd "$REPO"
PRINT=""
if [ "${1:-}" = "--print" ]; then PRINT=1; shift; fi
read -r TOOL MODEL EFFORT < <(python3 - <<'PY'
import sys
sys.path.insert(0, "factory")
import common
cfg = common.config(".")
problem = common.config_problem(cfg, ".")
if problem:
    sys.exit(f"chief.sh: refusing to start: {problem}")
role = cfg["roles"]["chief-of-staff"]
print(role["tool"], role["model"], role["effort"])
PY
)
LOOP="Run the Chief of Staff loop: each iteration is job tick in .ai/prompts/chief-of-staff-jobs.v1.md; your role is .ai/prompts/chief-of-staff.v1.md; the factory's rules are .ai/factory-agents.md (read them first). Keep going without stopping."
case "$TOOL" in
  claude) CMD=(claude --agent chief-of-staff --model "$MODEL" --effort "$EFFORT" "$@" "/loop $LOOP") ;;
  codex)  CMD=(codex -m "$MODEL" -c "model_reasoning_effort=\"$EFFORT\"" "$@" "$LOOP") ;;
  *) echo "roles.chief-of-staff uses tool '$TOOL': start your harness with model $MODEL and this first instruction:"
     echo "$LOOP"; exit 0 ;;
esac
if [ -n "$PRINT" ]; then printf '%q ' "${CMD[@]}"; echo; exit 0; fi
exec "${CMD[@]}"
