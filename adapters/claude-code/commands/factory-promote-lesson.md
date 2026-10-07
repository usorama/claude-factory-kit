---
description: Share a proven local lesson with every user of the kit - a local branch on a kit checkout with the lesson, the rule line or the script change, a version bump and a CHANGELOG entry. The person reads the exact text and types the push.
argument-hint: "<lesson id> [--files factory/x.py ...]"
allowed-tools: Bash(git -C * status *), Bash(git -C * log *), Bash(git -C * diff *), Bash(git -C * show *)
---
Lesson: $ARGUMENTS
1. Find a clean checkout of the kit repo (ask once for its path, or ask the person to clone it).
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" promote-lesson <id> --plugin-repo <checkout> [--files ...]`. It refuses a
   lesson that is not applied with two strikes, commits on a local branch, and prints the exact text and the remote URL.
3. Show the person that text in full and the remote URL. Lesson text can name a project or its details, and pushing
   makes it visible to everyone who can read that remote. Never run --push yourself.
4. If the person wants it shared, they type the push themselves:
   `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" promote-lesson <id> --plugin-repo <checkout> --push --confirm-remote <remote URL>`.
   It refuses unless the URL matches the checkout's remote exactly.
5. After the merge, users run /plugin update and then /factory-init to see the changed files (it asks before overwriting).
