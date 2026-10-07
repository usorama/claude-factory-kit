---
description: Install the 5-minute factory clock (cron on Linux and WSL2, launchd on macOS, or the Windows Task Scheduler line). Shows exactly what it will install and asks first.
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" clock *), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" clock), Bash(crontab -l), Bash(uname *)
---
1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" clock --print` and show what it would install and the tool checks.
2. Ask ONE question: install it now? (Recommend yes when the checks passed.) On Windows outside WSL, show the
   Task Scheduler line it printed and stop: the person adds it.
3. On yes, run `python3 "${CLAUDE_PLUGIN_ROOT}/core/cli.py" clock`. It sets clock_host in factory.toml (commit it: one clock per repo) and runs one tick.
4. Report the last tick line and any consistency finding, in plain words.
