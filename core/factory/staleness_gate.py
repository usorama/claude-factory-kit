"""Staleness gate: refuse to publish the dashboard when anything on it is older than its sources.

1. Data sections (data.json): a source file changed after the section's as_of -> stale.
   Fix: run factory/metrics.py again.
2. Static sections in the page (<section data-static data-asof="YYYY-MM-DD" data-sources="a b">):
   a source changed (last git commit, or an uncommitted edit) on a later day than data-asof -> stale.
   Fix: update the text in place and its data-asof. Never add a second section to cover it.
3. A static section that contains a digit -> refused. Numbers come from data, never typed.
Usage: staleness_gate.py [--html dashboard/index.html] [--data var/factory/dashboard/data.json] [--publish OUT]
Exit 0 clean (and OUT written), 1 stale or typed numbers (nothing written).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from common import parse_time

STATIC = re.compile(r"<section\s([^>]*\bdata-static\b[^>]*)>(.*?)</section>", re.DOTALL)
ATTR = re.compile(r'data-(asof|sources|title)="([^"]*)"')
PLACEHOLDER = '<script id="factory-data" type="application/json">null</script>'


def changed_at(root, name):
    """When a source last changed: its mtime if it differs from git, else its last commit time."""
    path = Path(root) / name
    if not path.exists():
        return None
    files = [p for p in path.rglob("*") if p.is_file()] + [path] if path.is_dir() else [path]
    mtime = datetime.fromtimestamp(max(p.stat().st_mtime for p in files), timezone.utc)
    dirty = subprocess.run(["git", "status", "--porcelain", "--", name], cwd=root, capture_output=True, text=True)
    if dirty.returncode != 0 or dirty.stdout.strip():
        return mtime
    committed = subprocess.run(["git", "log", "-1", "--format=%cI", "--", name], cwd=root,
                               capture_output=True, text=True).stdout.strip()
    return datetime.fromisoformat(committed) if committed else mtime


def data_findings(root, data):
    found = []
    for name, section in data["sections"].items():
        as_of = parse_time(section["as_of"])
        for source in section["sources"]:
            path = Path(root) / source
            if not path.exists():
                continue
            files = [p for p in path.rglob("*") if p.is_file()] + [path] if path.is_dir() else [path]
            newest = datetime.fromtimestamp(max(p.stat().st_mtime for p in files), timezone.utc)
            if newest > as_of:
                found.append(f"data section '{name}' is older than {source}; run factory/metrics.py")
    return found


def static_findings(root, html):
    found = []
    for attributes, body in STATIC.findall(html):
        attrs = dict(ATTR.findall(attributes))
        title = attrs.get("title", "untitled")
        if "asof" not in attrs or "sources" not in attrs:
            found.append(f"static section '{title}' must declare data-asof and data-sources")
            continue
        as_of = date.fromisoformat(attrs["asof"])
        for source in attrs["sources"].split():
            when = changed_at(root, source)
            if when and when.date() > as_of:
                found.append(f"static section '{title}' (as of {as_of}) is older than {source} "
                             f"(changed {when.date()}); update the text in place and its data-asof")
        text = re.sub(r"<[^>]+>", " ", body)
        digit = re.search(r"\d+", text)
        if digit:
            found.append(f"static section '{title}' has a typed number '{digit.group()}'; numbers come from data")
    return found


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--html", default="dashboard/index.html")
    parser.add_argument("--data", default="var/factory/dashboard/data.json")
    parser.add_argument("--publish")
    args = parser.parse_args(argv)
    root = Path(root or Path.cwd())
    html = (root / args.html).read_text()
    data = json.loads((root / args.data).read_text())
    findings = data_findings(root, data) + static_findings(root, html)
    for finding in findings:
        print(f"STALE: {finding}", file=sys.stderr)
    if findings:
        print("staleness gate: refused; nothing published", file=sys.stderr)
        return 1
    if args.publish:
        if PLACEHOLDER not in html:
            print("staleness gate: the page has no data placeholder", file=sys.stderr)
            return 1
        payload = json.dumps(data).replace("</", "<\\/")
        out = root / args.publish
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html.replace(PLACEHOLDER, PLACEHOLDER.replace(">null<", f">{payload}<")))
        print(f"staleness gate: clean; wrote {args.publish}")
    else:
        print("staleness gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
