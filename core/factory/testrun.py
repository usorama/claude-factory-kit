"""Run pytest in a folder and return one record per test, with the failure cause.

Every pytest run the factory makes (red check, build check, each guard mutant, merged suite, and the
builder's, reviewer's and crew's own runs through run_tests.py) runs code a model wrote. So it runs fenced:
- environment: only an allow list (PATH, locale, TERM, TZ); no tokens, no gh or cloud credentials; HOME and
  TMPDIR point to a fresh temporary folder (PYTHONUSERBASE keeps user-installed pytest);
- files: Linux and WSL2 use bubblewrap. The whole disk is read-only, the person's home folder is hidden
  (an empty folder takes its place), /tmp is empty, and only the work folder, the scratch folder and the
  paths in FACTORY_ALLOW_PATHS (factory.toml sandbox_allow_paths) can be written. Python's own folders stay
  readable. macOS uses sandbox-exec with a profile that refuses writes outside those folders and reads
  inside the home folder (not verified on a Mac yet);
- network: off (bubblewrap --unshare-all; the macOS profile denies network);
- time: each run stops after FACTORY_TEST_TIMEOUT seconds (factory.toml test_timeout_minutes); the whole
  process group is killed, and the run counts as a refusal (TestTimeout), never a hang.
When bubblewrap cannot start (some Ubuntu setups block unprivileged namespaces), the run is NOT fenced;
NETWORK_ISOLATION and FILESYSTEM_ISOLATION say so, and the red and build checks report them.
Set FACTORY_TEST_NETWORK=allow to turn the fence off on purpose.
"""
import os
import platform
import shutil
import signal
import site
import subprocess
import sys
import tempfile
from pathlib import Path

from common import read_jsonl

HERE = Path(__file__).resolve().parent
KEEP = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "SYSTEMROOT")


class TestTimeout(ValueError):
    """A test run passed its time limit; the factory killed it."""


def _bwrap_works():
    try:
        return subprocess.run(["bwrap", "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent", "--", "true"],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _kind():
    if os.environ.get("FACTORY_TEST_NETWORK") == "allow":
        return "none"
    if platform.system() == "Linux" and shutil.which("bwrap") and _bwrap_works():
        return "bwrap"
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    return "none"


KIND = _kind()
NETWORK_ISOLATION = KIND
FILESYSTEM_ISOLATION = KIND


def allow_paths():
    return [Path(p).expanduser().resolve() for p in os.environ.get("FACTORY_ALLOW_PATHS", "").split(os.pathsep) if p]


def readable_paths():
    """Folders Python and the factory need even though they may sit inside the hidden home folder."""
    found = {Path(site.getuserbase()), Path(sys.prefix), Path(sys.base_prefix), HERE}
    return sorted({p.resolve() for p in found if p.exists()})


def git_dirs(folder):
    """The repo's git folder, read-only, so a test that asks git about its own repo still works."""
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=folder,
                         capture_output=True, text=True)
    path = Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    return [path.resolve()] if path and path.exists() else []


def fence(folder, scratch):
    """The command prefix that fences a test run to the work folder and the scratch folder."""
    folder, scratch, home = Path(folder).resolve(), Path(scratch).resolve(), Path.home().resolve()
    writable = [folder, scratch, *allow_paths()]
    readable = readable_paths() + git_dirs(folder)
    if KIND == "bwrap":  # empty /tmp and home first, then bind back what is needed (read-only), then the writable folders
        prefix = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", str(home)]
        for path in readable:
            prefix += ["--ro-bind", str(path), str(path)]
        for path in writable:
            prefix += ["--bind", str(path), str(path)]
        return prefix + ["--unshare-all", "--die-with-parent", "--chdir", str(folder), "--"]
    if KIND == "sandbox-exec":
        rules = ["(version 1)", "(allow default)", "(deny network*)", "(deny file-write*)",
                 f'(deny file-read* (subpath "{home}"))']
        rules += [f'(allow file-read* (subpath "{p}"))' for p in readable + writable]
        rules += [f'(allow file-write* (subpath "{p}"))' for p in writable] + ['(allow file-write* (subpath "/dev"))']
        return ["sandbox-exec", "-p", " ".join(rules)]
    return []


def scrubbed_env(scratch, report):
    env = {name: os.environ[name] for name in KEEP if name in os.environ}
    home = Path(scratch) / "home"
    (home / "tmp").mkdir(parents=True)
    env.update(HOME=str(home), TMPDIR=str(home / "tmp"), PYTHONUSERBASE=site.getuserbase(),
               PYTHONDONTWRITEBYTECODE="1", FACTORY_PYTEST_REPORT=str(report), PYTHONPATH=str(HERE))
    return env


def run(folder, args=(), timeout=None):
    """Return (exit code, {test id: record}, [collection error ids], output text). Raises TestTimeout."""
    timeout = timeout or float(os.environ.get("FACTORY_TEST_TIMEOUT", "1200"))
    with tempfile.TemporaryDirectory(prefix="factory-pytest-") as scratch:
        report = Path(scratch) / "report.jsonl"
        command = [*fence(folder, scratch), sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                   "-p", "factory_pytest_plugin", "--tb=short", *args]
        process = subprocess.Popen(command, cwd=folder, env=scrubbed_env(scratch, report), text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)  # the whole group: pytest and anything it started
            except ProcessLookupError:
                pass
            process.communicate()
            raise TestTimeout(f"the test run passed its limit of {int(timeout)} seconds and was stopped") from error
        records, collect_errors = {}, []
        for record in read_jsonl(report):
            if record["when"] == "collect":
                collect_errors.append(record["id"])
            elif record["id"] not in records or record["outcome"] == "failed":
                records[record["id"]] = record
    return process.returncode, records, collect_errors, output


def failed(records):
    return sorted(name for name, record in records.items() if record["outcome"] == "failed")


def base_id(test_id):
    """A parametrized id test_x[1] belongs to the named test test_x."""
    return test_id.split("[", 1)[0]
