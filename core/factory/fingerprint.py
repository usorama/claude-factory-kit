"""Host equivalence: one pinned toolchain plus one input snapshot.

Two hosts are equivalent for the factory only when they run the same pinned tools on the same
inputs. A host that differs gives different test results (seen: a cloud host with another Python
and no pytest ran nothing; with pins it still differed on inputs that existed on one host only).
  fingerprint.py                       print this host's toolchain and input snapshot
  fingerprint.py --check factory/toolchain.json   exit 1 when a pinned tool differs in major.minor
                      (tick.sh runs this); a patch difference only warns. Either way the versions
                      seen are saved to var/factory/toolchain-seen.json for consistency.py.
  fingerprint.py --compare a.json b.json          exit 1 when two hosts' fingerprints differ
"""
import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

TOOLS = {"git": ["git", "--version"], "gh": ["gh", "--version"], "claude": ["claude", "--version"],
         "codex": ["codex", "--version"],
         "pytest": [sys.executable, "-m", "pytest", "--version"]}


def version(command):
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "missing"
    text = (out.stdout or out.stderr).strip().splitlines()
    return text[0] if out.returncode == 0 and text else "missing"


def toolchain():
    tools = {name: version(command) for name, command in TOOLS.items()}
    return {"python": platform.python_version(), "machine": platform.machine(), **tools}


def snapshot(root):
    """Hash of the inputs the checks read: tracked files at HEAD, the queue's test lists, the config."""
    root = Path(root)
    digest = hashlib.sha256()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    digest.update(head.encode())
    for name in ("factory.toml", "var/factory/queue.json"):
        path = root / name
        digest.update(path.read_bytes() if path.exists() else b"-")
    return {"head": head, "inputs_sha256": digest.hexdigest()}


def major_minor(text):
    found = re.search(r"\d+\.\d+", str(text))
    return found.group() if found else str(text)


def differences(pinned, mine):
    """(blocking, warnings): a major.minor change blocks; a patch change only warns."""
    blocking, warnings = [], []
    for name, want in pinned.items():
        have = mine.get(name)
        if have == want:
            continue
        line = f"{name}: pinned {want!r}, found {have!r}"
        (warnings if major_minor(have) == major_minor(want) else blocking).append(line)
    return blocking, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check")
    parser.add_argument("--compare", nargs=2)
    args = parser.parse_args(argv)
    if args.compare:
        a, b = (json.loads(Path(p).read_text()) for p in args.compare)
        diffs = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        print("equivalent" if not diffs else "differ: " + ", ".join(diffs))
        return 1 if diffs else 0
    mine = {**toolchain(), **snapshot(Path.cwd())}
    if args.check:
        blocking, warnings = differences(json.loads(Path(args.check).read_text()), mine)
        seen = Path("var/factory/toolchain-seen.json")
        seen.parent.mkdir(parents=True, exist_ok=True)
        seen.write_text(json.dumps({"tools": mine, "blocking": blocking, "warnings": warnings}, indent=1))
        for line in blocking + warnings:
            print(f"toolchain differs: {line}", file=sys.stderr)
        return 1 if blocking else 0
    print(json.dumps(mine, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
