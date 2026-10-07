---
description: Build the factory dashboard from this repo's records (through the staleness gate) and publish it - as a claude.ai artifact when the Artifact tool is available, otherwise as a local HTML file.
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" dashboard *), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" dashboard)
---
1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" dashboard`. It rebuilds the numbers and refuses if anything is stale; fix what it names, never bypass it.
2. If you have the Artifact tool, publish the printed file path as an artifact. Publish the same path every time:
   that updates the same link. Otherwise print the file path so the person can open it.
3. Say in one line what changed since the last publish (units landed, stops, decisions waiting).
The page has the tabs Now, Daily report, Factory metrics, Workflow, Decisions waiting and Lessons.
