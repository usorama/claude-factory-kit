---
description: Share a proven local lesson with every user of the kit - a branch on the kit repo with the lesson, the rule line or the script change, a version bump and a CHANGELOG entry, then a pull request.
argument-hint: "<lesson id> [--files factory/x.py ...]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" promote-lesson *), Bash(git -C * status *), Bash(git -C * log *), Bash(git -C * diff *), Bash(gh repo clone *)
---
Lesson: $ARGUMENTS
1. Find a clean checkout of the kit repo (ask once for its path, or clone it with `gh repo clone <owner>/claude-factory-kit`
   into a temporary folder).
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" promote-lesson <id> --plugin-repo <checkout> [--files ...]` WITHOUT --push. It refuses a lesson that is not
   applied with two strikes. Show the branch, the new version and `git -C <checkout> diff HEAD~1 --stat`.
3. Opening a pull request is visible to other people: ask ONE question before running it again with --push.
4. After the merge, users run /plugin update and then /factory-init to see the changed files (it asks before overwriting).
