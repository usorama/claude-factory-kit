---
description: Set up the factory in this repo - probes the models this machine can use, writes the roles file, rules, state, backlog, lessons, prompts and dashboard. Asks before overwriting anything.
argument-hint: "[claude-only|codex-only|claude-codex|generic]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" init *), Bash(git status *), Bash(which *)
---
Set up the factory in the current repo. Preset: $ARGUMENTS (default claude-only; it needs no Codex).

1. Check this is the top of a git repo with a green test suite (`python3 -m pytest -q`). If not, say so and stop.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" init --plan --preset <preset> --adapter claude-code` and show the result as a short table.
3. Tell the person: when the project has no factory.toml yet, init will make one tiny call per candidate model
   of each installed tool (about ten calls, a few cents of usage) to find the exact models this machine can use.
   Ask ONE question: go ahead, and for each target marked "differs", overwrite it or keep theirs
   (recommend: overwrite files under factory/, keep everything else).
4. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" init --apply --preset <preset> --adapter claude-code [--overwrite <paths>]`.
5. Show the role lines (role, model, why). If the reviewer runs on the builder's model, say plainly that the
   review is weaker (fresh session only). If init refused, show the reason and suggest another preset.
6. Next steps, in plain words: fill state.md's Position time, commit, then /factory-install-clock.
Never edit factory.toml models by hand; a re-probe is `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" probe` and a person approves it with `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" roles accept`.
