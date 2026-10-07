#!/usr/bin/env bash
# Set up the 5-minute clock for one repo, check the tools, and prove it with one tick.
# Usage: bash factory/install-clock.sh <path to the work repo> [--print]   (--print: show, change nothing)
set -euo pipefail
REPO="$(cd "${1:?usage: install-clock.sh <repo> [--print]}" && pwd -P)"
PRINT="${2:-}"
TICK="$REPO/factory/tick.sh"
fail() { echo "NOT READY: $1" >&2; exit 1; }

case "$REPO" in /mnt/*) fail "the repo is under /mnt; move it into your Linux home folder" ;; esac
[ -f "$HOME/.factory-env.sh" ] && . "$HOME/.factory-env.sh"
ROLE_TOOLS="$(python3 -c 'import sys, tomllib; r = tomllib.load(open(sys.argv[1], "rb")).get("roles", {}); print(" ".join(sorted({v["tool"] for v in r.values() if v.get("tool") in ("claude", "codex")})))' "$REPO/factory.toml")"
for tool in python3 git gh $ROLE_TOOLS; do command -v "$tool" > /dev/null || fail "$tool not found on PATH (set it in ~/.factory-env.sh)"; done
gh auth status > /dev/null 2>&1 || fail "gh is not signed in: run gh auth login"
echo "tools: $(python3 --version), $(git --version), roles use: ${ROLE_TOOLS:-other}"
host="$(hostname)"
python3 - "$REPO/factory.toml" "$host" "$PRINT" <<'EOF'
import re, sys, tomllib
path, host, show_only = sys.argv[1], sys.argv[2], sys.argv[3] == "--print"
text = open(path).read()
current = tomllib.loads(text).get("clock_host", "")
if current not in ("", host):
    sys.exit(f"NOT READY: factory.toml names {current} as the clock host; one clock per repo")
line = f'clock_host = "{host}"'
text = re.sub(r'(?m)^clock_host = .*$', line, text) if re.search(r'(?m)^clock_host = ', text) else line + "\n" + text
if not show_only:
    open(path, "w").write(text)
print(f"clock host: {host} (commit factory.toml so no second machine runs a clock)")
EOF

case "$(uname -s)" in
  Darwin)
    PLIST="$HOME/Library/LaunchAgents/local.factory-tick.$(basename "$REPO").plist"
    BODY="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
<key>Label</key><string>local.factory-tick.$(basename "$REPO")</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>$TICK</string><string>$REPO</string></array>
<key>StartInterval</key><integer>300</integer>
</dict></plist>"
    if [ "$PRINT" = "--print" ]; then echo "$BODY"; exit 0; fi
    echo "$BODY" > "$PLIST"; launchctl unload "$PLIST" 2> /dev/null || true; launchctl load "$PLIST"
    echo "launchd: $PLIST" ;;
  Linux)
    LINE="*/5 * * * * /bin/bash $TICK $REPO"
    if grep -qi microsoft /proc/version 2> /dev/null; then
      echo "WSL2: cron needs systemd. If 'systemctl is-active cron' is not active: add [boot] systemd=true"
      echo "      to /etc/wsl.conf, run 'wsl --shutdown' in PowerShell, then 'sudo systemctl enable --now cron'."
      echo "      Or use Windows Task Scheduler every 5 minutes with:"
      echo "      wsl.exe -d Ubuntu -- bash -lc \"$TICK $REPO\""
    fi
    if [ "$PRINT" = "--print" ]; then echo "$LINE"; exit 0; fi
    ( crontab -l 2> /dev/null | grep -vF "$TICK" ; echo "$LINE" ) | crontab -
    echo "cron: $LINE" ;;
  *) fail "unknown system $(uname -s); on Windows run this inside WSL2" ;;
esac

bash "$TICK" "$REPO" || true
tail -1 "$REPO/var/factory/ticks.log"
python3 "$REPO/factory/consistency.py" > /dev/null && echo "READY: one tick ran and the records agree." \
  || echo "One tick ran. Fix the findings shown by: python3 factory/consistency.py"
