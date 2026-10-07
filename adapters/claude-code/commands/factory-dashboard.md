---
description: Build the factory dashboard from this repo's records (through the staleness gate). It stays a local file unless factory.toml says dashboard_publish = "artifact".
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" dashboard *), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" dashboard)
---
1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" dashboard`. It rebuilds the numbers and refuses if anything is stale;
   fix what it names, never bypass it.
2. Read its last line. Only when it says "publish: allowed" may you publish the printed file as an artifact (the same
   path every time updates the same link). Otherwise give the person the file path to open in their browser: the
   page holds the project's work log, and sending it to an outside service needs the person's choice in factory.toml.
3. Say in one line what changed since the last build (units landed, stops, decisions waiting).
The page has the tabs Now, Daily report, Factory metrics, Workflow, Decisions waiting and Lessons.
