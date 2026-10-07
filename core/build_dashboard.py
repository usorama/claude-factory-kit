#!/usr/bin/env python3
"""Build the project's dashboard page from its own records. Used by `factory dashboard` and every adapter.

Runs the project's factory/metrics.py, then the staleness gate, which embeds the data into the
page and refuses anything stale. Prints the absolute path of the page (publish that path as an
artifact; publishing the same path again updates the same link).
Usage: build_dashboard.py [--project DIR]
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parent
OUT = "var/factory/dashboard/factory-dashboard.html"


def build(project):
    if not (project / "factory/metrics.py").is_file():
        raise SystemExit("factory_dashboard: the factory is not set up here; run: factory init --apply")
    page = project / "dashboard/index.html"
    if not page.exists():
        page.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CORE / "templates/dashboard/index.html", page)
    for command in (["factory/metrics.py"], ["factory/staleness_gate.py", "--publish", OUT]):
        result = subprocess.run([sys.executable, *command], cwd=project, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(f"factory_dashboard: {' '.join(command)} refused:\n{result.stderr.strip()}")
    return project / OUT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    print(build(parser.parse_args().project.resolve()))
