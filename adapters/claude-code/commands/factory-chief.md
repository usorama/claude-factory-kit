---
description: One pass of the Chief of Staff loop by hand (normally `factory chief` starts the role and its loop) - job tick, or the job you name (cut, verify, stop, review, close, retro, report).
argument-hint: "[tick|cut <row>|verify <unit>|stop <unit>|review <pr>|close <row>|retro|report]"
allowed-tools: Bash(python3 factory/*), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" *), Bash(git status *), Bash(git diff *), Bash(git log *), Bash(git add *), Bash(git commit *), Bash(git worktree *), Bash(date *)
---
Act as the Chief of Staff: read .ai/prompts/chief-of-staff.v1.md, then run the job "$ARGUMENTS" (default: tick) exactly as
.ai/prompts/chief-of-staff-jobs.v1.md lists its steps. Never pick or change a model and never start a code-only role
yourself: ask code (`python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" crew ...`, `python3 factory/tick.py ...`). To run the
role continuously, start it with `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" chief` in tmux instead.
End with a short report: outcome first, then "for your information" decisions, then any decision waiting for the
human (one question, with a recommendation).
