#!/usr/bin/env python3
"""The only way a builder, reviewer or crew agent runs tests: pytest in the factory's scrubbed, sandboxed run
(no tokens, a temporary home, no network, writes only inside the work folder and a scratch folder).
Usage (from the unit's work folder): python3 <factory>/run_tests.py [test ids or pytest arguments]
Prints pytest's own output, then one line per failing test, and exits with pytest's exit code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from testrun import FILESYSTEM_ISOLATION, NETWORK_ISOLATION, TestTimeout, failed, run  # noqa: E402


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        code, records, collect_errors, output = run(Path.cwd(), args)
    except TestTimeout as error:
        print(f"run_tests: {error}")
        return 124
    print(output.rstrip())
    for name in collect_errors + failed(records):
        print(f"FAILED {name}")
    print(f"run_tests: exit {code}; network isolation {NETWORK_ISOLATION}; filesystem isolation {FILESYSTEM_ISOLATION}")
    return code


if __name__ == "__main__":
    sys.exit(main())
