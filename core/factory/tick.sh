#!/usr/bin/env bash
# One factory tick. cron (Linux, WSL2), launchd (macOS) or Task Scheduler runs this every 5 minutes.
# factory/install-clock.sh sets the schedule up.  Usage: factory/tick.sh <path to the work repo>
set -u
REPO="${1:?usage: tick.sh <repo>}"
# PATH for the clock: claude, gh, python3 and git must be found. Put exports in this optional file.
# Never put a token in it: tests run as this user (see RULES section 15).
[ -f "$HOME/.factory-env.sh" ] && . "$HOME/.factory-env.sh"
export DISABLE_AUTOUPDATER=1
cd "$REPO" || exit 1
mkdir -p var/factory
skip() {
  echo "{\"at\": \"$(date -u +%Y-%m-%dT%H:%M:%S+00:00)\", \"skipped\": \"$1\"}" >> var/factory/ticks.log
  exit 1
}
case "$(pwd -P)" in /mnt/*) skip "the repo is under /mnt (a Windows drive); move it into the Linux home folder" ;; esac
if [ -f factory/toolchain.json ] && ! python3 factory/fingerprint.py --check factory/toolchain.json \
     2>> var/factory/tick.err; then
  skip "toolchain differs from factory/toolchain.json in a major or minor version"
fi
python3 factory/tick.py tick >> var/factory/tick.out 2>> var/factory/tick.err
status=$?
# Keep the local dashboard current after every tick; the gate refuses anything stale.
python3 factory/metrics.py > /dev/null 2>> var/factory/tick.err &&
  python3 factory/staleness_gate.py --publish var/factory/dashboard/factory-dashboard.html \
    > /dev/null 2>> var/factory/tick.err
exit $status
