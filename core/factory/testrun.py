"""Run pytest in a folder and return one record per test, with the failure cause.

Every pytest run the factory makes (red check, build check, each guard mutant, merged suite) runs
the unit's code, which a model wrote. So it runs scrubbed:
- environment: only an allow list (PATH, locale, TERM, TZ); no tokens, no gh or cloud credentials;
  HOME and TMPDIR point to a fresh temporary folder (PYTHONUSERBASE keeps user-installed pytest);
- network: off where the OS allows it. Linux and WSL2: bubblewrap with --unshare-net, when it can
  start (some Ubuntu setups block unprivileged namespaces; then the run is NOT network-isolated).
  macOS: sandbox-exec with a deny-network profile. Set FACTORY_TEST_NETWORK=allow to turn it off.
NETWORK_ISOLATION tells which one is in use; the red and build checks report it.
"""
import os
import platform
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

from common import read_jsonl

HERE = Path(__file__).resolve().parent
KEEP = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "SYSTEMROOT")


def _isolation():
    if os.environ.get("FACTORY_TEST_NETWORK") == "allow":
        return []
    if platform.system() == "Linux" and shutil.which("bwrap"):
        prefix = ["bwrap", "--dev-bind", "/", "/", "--unshare-net", "--"]
        try:
            if subprocess.run(prefix + ["true"], capture_output=True, timeout=10).returncode == 0:
                return prefix
        except (OSError, subprocess.TimeoutExpired):
            pass
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]
    return []


ISOLATION = _isolation()
NETWORK_ISOLATION = ISOLATION[0] if ISOLATION else "none"


def scrubbed_env(scratch, report):
    env = {name: os.environ[name] for name in KEEP if name in os.environ}
    home = Path(scratch) / "home"
    (home / "tmp").mkdir(parents=True)
    env.update(HOME=str(home), TMPDIR=str(home / "tmp"), PYTHONUSERBASE=site.getuserbase(),
               PYTHONDONTWRITEBYTECODE="1", FACTORY_PYTEST_REPORT=str(report), PYTHONPATH=str(HERE))
    return env


def run(folder, args=(), timeout=None):
    """Return (exit code, {test id: record}, [collection error ids], output text)."""
    with tempfile.TemporaryDirectory(prefix="factory-pytest-") as scratch:
        report = Path(scratch) / "report.jsonl"
        result = subprocess.run(
            [*ISOLATION, sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-p", "factory_pytest_plugin", "--tb=short", *args],
            cwd=folder, env=scrubbed_env(scratch, report), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout, check=False)
        records, collect_errors = {}, []
        for record in read_jsonl(report):
            if record["when"] == "collect":
                collect_errors.append(record["id"])
            elif record["id"] not in records or record["outcome"] == "failed":
                records[record["id"]] = record
    return result.returncode, records, collect_errors, result.stdout


def failed(records):
    return sorted(name for name, record in records.items() if record["outcome"] == "failed")


def base_id(test_id):
    """A parametrized id test_x[1] belongs to the named test test_x."""
    return test_id.split("[", 1)[0]
