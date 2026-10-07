"""Shared paths, settings, locks, the queue file and the step log.

Runtime files live in <repo>/var/factory/ (never committed):
Settings: <repo>/factory.toml (roles = the commands that build and review; see core/presets/).
  queue.json  every unit and its state       log.jsonl  one line per step start and end
  ticks.log   one line per clock tick        asks/      stop cards and decision cards
"""
import json
import os
import re
import subprocess
import tempfile
import time
import tomllib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACTIVE = ("cut", "red", "built", "checked", "reviewed")
STOPPED = ("cut_refused", "needs_split", "errored")
UNIT_PATH = re.compile(r"\.ai/units/([A-Za-z0-9][A-Za-z0-9_-]*)/(\d+)\.json")
PRESETS = Path(__file__).resolve().parent / "presets"
DEFAULTS = {
    "base": "main", "lanes": 2,
    "build_timeout_minutes": 40, "review_timeout_minutes": 30,
    "clock_stale_minutes": 15, "queue_floor": 2,
    "landing": "", "merge_method": "merge",
    "max_turns_build": 60, "max_turns_review": 40,
    "max_budget_build_usd": 3.0, "max_budget_review_usd": 3.0, "daily_budget_usd": 40.0,
    "max_retries": 3, "usage_pause_minutes": 60, "clock_host": "", "same_tool_review": "", "retro_time": "21:00",
    "crew_max_turns": 20, "max_budget_crew_usd": 0.75, "planning": "required",
    "require_clone_marker": True, "forbidden_paths": [], "footprint": "personal", "dashboard_publish": "local",
    "test_timeout_minutes": 20, "sandbox_allow_paths": [],
    "chief_session": "factory-chief", "harness_update_command": "", "handoff_max_minutes": 30, "restart_wait_seconds": 60,
}
OUTPUTS = ("claude-json", "codex-jsonl", "text")
ROLE_FORMS = {"chief-of-staff": ("position", "consistency"), "builder": ("diff", "build_check"),
              "reviewer": ("review-json", "review_form"), "researcher": ("research-md", "research_check"),
              "summarizer": ("summary-md", "summary_check")}
ALIASES = {"sonnet", "opus", "haiku", "fable", "default", "latest", "best", "auto"}
SESSION_REUSE = {"claude": {"-c", "--continue", "-r", "--resume", "--session-id", "--fork-session"},
                 "codex": {"resume", "fork", "--last"},
                 "other": {"--continue", "--resume", "--session-id", "resume", "fork", "--last"}}
FRESH_FLAG = {"claude": "--no-session-persistence", "codex": "--ephemeral"}
LANDINGS = ("direct", "pr_merge", "auto", "pr_only")
MERGE_METHODS = ("merge", "squash", "rebase")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def config(root):
    """Settings from factory.toml (or the older factory.json) over the defaults. Roles come from the
    project's file, else from the claude-only preset (the zero-config default)."""
    toml_path, json_path = Path(root) / "factory.toml", Path(root) / "factory.json"
    if toml_path.exists():
        found = tomllib.loads(toml_path.read_text())
    else:
        found = json.loads(json_path.read_text()) if json_path.exists() else {}
    preset = tomllib.loads((PRESETS / "claude-only.toml").read_text())
    return {**DEFAULTS, "preset": "claude-only", **found, "roles": found.get("roles") or preset["roles"]}


def review_independence(cfg):
    """('different-model' | 'fresh-session', plain text). A fresh session with the same model is weaker."""
    builder, reviewer = cfg["roles"]["builder"], cfg["roles"]["reviewer"]
    one, two = f"{builder['tool']}:{builder['model']}", f"{reviewer['tool']}:{reviewer['model']}"
    if one != two:
        return "different-model", f"different model: {one} builds, {two} reviews"
    return "fresh-session", f"fresh session only, same model {one} (weaker): a different review prompt"


def roles_problem(cfg, root=None):
    """The roles file pins every role; refuse anything unpinned, mismatched or not independent."""
    roles = cfg["roles"]
    for name, (form, check) in ROLE_FORMS.items():
        role = roles.get(name)
        if not role:
            return f"roles.{name} is missing from factory.toml"
        missing = [k for k in ("tool", "model", "effort", "prompt", "form", "check") if not role.get(k)]
        if missing:
            return f"roles.{name} needs {', '.join(missing)}"
        if str(role["model"]).startswith("<") or role["model"] in ALIASES or str(role["model"]).endswith("-latest"):
            return (f"roles.{name}.model must be an exact model ID that answered the probe, never a moving alias "
                    "or the tool's default (run: factory probe)")
        if (role["form"], role["check"]) != (form, check):
            return f"roles.{name} must produce form {form} checked by {check}"
        if not re.search(r"\.v\d+\.md$", role["prompt"]):
            return f"roles.{name}.prompt must be a versioned file such as {name}.v1.md"
        if root is not None and not (Path(root) / role["prompt"]).is_file():
            return f"roles.{name}.prompt {role['prompt']} does not exist"
    for name in ("builder", "reviewer"):
        role, command = roles[name], [str(part) for part in roles[name].get("command") or []]
        if not command or any(part.startswith("<") for part in command):
            return f"roles.{name}.command is not set; put the command in factory.toml (see the presets)"
        if not any("{model}" in part for part in command):
            return f"roles.{name}.command must pass {{model}}; no role runs on the tool's default model"
        if role.get("output") not in OUTPUTS:
            return f"roles.{name}.output must be one of {', '.join(OUTPUTS)}"
    builder, reviewer = roles["builder"], roles["reviewer"]
    command = [str(part) for part in reviewer["command"]]
    reused = SESSION_REUSE.get(reviewer["tool"], SESSION_REUSE["other"]).intersection(command)
    if reused:
        return f"the reviewer command reuses a session ({', '.join(sorted(reused))}); a review needs a fresh session"
    fresh = FRESH_FLAG.get(reviewer["tool"])
    if (fresh and fresh not in command) or (not fresh and reviewer.get("fresh_session") is not True):
        return (f"the reviewer must start a fresh session ({fresh} in its command)" if fresh else
                "the reviewer command must start a fresh session; say so with fresh_session = true")
    if review_independence(cfg)[0] == "fresh-session":
        if cfg["same_tool_review"] != "fresh-session":
            return ("the builder and the reviewer are the same model; use a different model, or set "
                    'same_tool_review = "fresh-session" with a different review prompt')
        same_text = root is not None and (Path(root) / builder["prompt"]).read_bytes() == (Path(root) / reviewer["prompt"]).read_bytes()
        if builder["prompt"] == reviewer["prompt"] or same_text:
            return "a same-model review needs a different review prompt from the builder's"
    return None


CLONE_MARKER = ".factory-clone"


def folder_problem(cfg, root):
    """Optional guards on the folder the factory runs in (both off by default):
    require_clone_marker = true: run only where a .factory-clone file exists, so the factory never runs in the folder
    a person works in; forbidden_paths = [...]: files that must not exist here (a real database, a credentials file)."""
    root = Path(root)
    if cfg.get("require_clone_marker") and not (root / CLONE_MARKER).is_file():
        return f"require_clone_marker is set and {root / CLONE_MARKER} is missing: this is not the factory's clone"
    for name in cfg.get("forbidden_paths") or []:
        if (root / name).exists():
            return f"forbidden path {name} exists in {root}: nothing runs here"
    return None


def config_problem(cfg, root=None):
    """A setting the factory refuses to run with, or None."""
    problem = (folder_problem(cfg, root) if root is not None else None) or roles_problem(cfg, root)
    if problem:
        return problem
    if cfg["landing"] and cfg["landing"] not in LANDINGS:
        return f"landing must be one of {', '.join(LANDINGS)}"
    if cfg["merge_method"] not in MERGE_METHODS:
        return f"merge_method must be one of {', '.join(MERGE_METHODS)}"
    return None


def paused_until(root):
    """The time model steps may start again after a usage limit, or None."""
    path = var(root) / "paused-until"
    if not path.exists():
        return None
    until = parse_time(path.read_text().strip())
    return until if until > datetime.now(timezone.utc) else None


def pause(root, minutes):
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    (var(root) / "paused-until").write_text(until.isoformat(timespec="seconds"))
    return until


def spend(root, who, cost):
    """Record one model run's cost the moment it ends (builds, reviews and every crew run)."""
    if isinstance(cost, (int, float)):
        with (var(root) / "spend.jsonl").open("a") as stream:
            stream.write(json.dumps({"at": now(), "who": who, "cost_usd": cost}) + "\n")


def spent_today(root):
    """US dollars spent on model runs today (UTC): every build, review and crew run, from the spend ledger."""
    today = now()[:10]
    return round(sum(e["cost_usd"] for e in read_jsonl(var(root) / "spend.jsonl")
                     if e.get("at", "")[:10] == today and isinstance(e.get("cost_usd"), (int, float))), 4)


class BudgetReached(Exception):
    """The daily model budget is spent: no model run starts until tomorrow or a person raises it."""


def budget_gate(root, cfg=None):
    """Checked before every model run and after each one: at or over the cap, one card, then nothing runs."""
    cfg = cfg or config(root)
    spent = spent_today(root)
    if spent < cfg["daily_budget_usd"]:
        return spent
    day = now()[:10]
    asks = var(root) / "asks"
    card = asks / f"DEC-budget-{day}.md"
    if not card.exists() and not (asks / "answered" / card.name).exists():
        asks.mkdir(parents=True, exist_ok=True)
        card.write_text(f"# Daily model budget reached ({spent} of {cfg['daily_budget_usd']} US dollars). Raise it for today?\n\n"
                        f"For: human\nKind: decision\nAsked: {now()}\n"
                        "Recommendation: No; model runs continue tomorrow. Checks and landings go on today.\n"
                        f"Reply: approve DEC-budget-{day} or reject DEC-budget-{day}\n")
    raise BudgetReached(f"daily budget reached: {spent} of {cfg['daily_budget_usd']} US dollars")


def var(root):
    folder = Path(root) / "var/factory"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unit_row(unit_path):
    """(row, n) from .ai/units/<row>/<n>.json; ValueError for any other shape."""
    match = UNIT_PATH.fullmatch(str(unit_path))
    if not match:
        raise ValueError(f"unit path {unit_path!r} is not .ai/units/<row>/<n>.json")
    return match.group(1), int(match.group(2))


def label(unit_path):
    row, n = unit_row(unit_path)
    return f"{row}-U{n}"


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


class Lock:
    """A lock file that appears with its owner's pid already inside. A dead owner's lock is removed."""

    def __init__(self, path, wait=300.0):
        self.path, self.wait = Path(path), wait

    def __enter__(self):
        deadline = time.monotonic() + self.wait
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        mine = Path(name)
        try:
            os.write(fd, stamp(os.getpid()).encode())
            os.close(fd)
            while True:
                try:
                    os.link(mine, self.path)
                    return self
                except FileExistsError:
                    pass
                try:
                    seen = self.path.read_text()
                except FileNotFoundError:
                    continue
                if not _alive(seen):
                    _remove_if_same(self.path, seen)
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"{self.path} is held by pid {seen}")
                time.sleep(0.05)
        finally:
            mine.unlink(missing_ok=True)

    def __exit__(self, *exc):
        """Remove the lock only while it is still this process's: after a takeover it belongs to someone else."""
        try:
            if self.path.read_text() == stamp(os.getpid()):
                _remove_if_same(self.path, stamp(os.getpid()))
        except FileNotFoundError:
            pass


def start_time(pid):
    """When a process started (Linux /proc, else ps), so a reused pid is not mistaken for the owner."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True)
        return "_".join(out.stdout.split()) or None


def stamp(pid):
    return f"{pid} {start_time(pid) or ''}".strip()


def _alive(text):
    """The lock's owner still runs: its pid exists AND started when the lock says. A lock whose owner
    exited (a short-lived process) or whose pid was reused by another process is stale."""
    parts = text.split()
    try:
        pid = int(parts[0])
        os.kill(pid, 0)
    except (ValueError, IndexError, ProcessLookupError):
        return False
    except PermissionError:
        pass
    return len(parts) < 2 or start_time(pid) == parts[1]


def _remove_if_same(lock, seen):
    aside = lock.with_name(f"{lock.name}.stale.{uuid.uuid4().hex}")
    try:
        os.rename(lock, aside)
    except FileNotFoundError:
        return
    if aside.read_text() != seen:
        try:
            os.link(aside, lock)  # someone took it in between: give it back
        except FileExistsError:
            pass
    aside.unlink()


def queue_lock(root, wait=300.0):
    return Lock(var(root) / "queue.lock", wait)


def read_queue(root):
    path = var(root) / "queue.json"
    return json.loads(path.read_text()) if path.exists() else {"units": []}


def write_queue(root, queue):
    path = var(root) / "queue.json"
    tmp = path.with_name(f"queue.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(queue, indent=1))
    os.replace(tmp, path)


def work_folder_problem(root, worktree):
    """Why a folder may not be a unit work folder, or None. The clock resets and cleans work folders
    (git reset --hard, git clean -fdq, git checkout -- .), so it accepts only a git worktree of this repo
    under <repo>-worktrees/, and never the repo itself, where a person's uncommitted work lives."""
    root, folder = Path(root).resolve(), Path(worktree).resolve()
    if folder == root:
        return "the work folder is the repo itself; the clock would wipe its uncommitted work"
    home = root.parent / f"{root.name}-worktrees"
    if home not in folder.parents:
        return f"{folder} is not under {home}; make work folders with tick.py worktree"
    ask = lambda where, *args: git(where, "rev-parse", *args, check=False).stdout.strip()
    if ask(folder, "--show-toplevel") != str(folder):
        return f"{folder} is not the top of a git worktree"
    if Path(ask(folder, "--path-format=absolute", "--git-common-dir")).resolve() != \
            Path(ask(root, "--path-format=absolute", "--git-common-dir")).resolve():
        return f"{folder} is a worktree of another repository"
    return None


class CommitRefused(ValueError):
    """git refused a factory commit: a hook failed, or the person has no git identity set."""


def commit(worktree, message):
    """Commit staged work as the person who runs the factory (their own git identity and signing settings), with
    the repo's hooks on. A refusal carries git's own message."""
    done = git(worktree, "commit", "-q", "-m", message, check=False)
    if done.returncode:
        detail = (done.stderr or done.stdout).strip()[-600:]
        if "tell me who you are" in detail or "auto-detect email" in detail:
            raise CommitRefused("git has no identity for the person running the factory: set git config user.name "
                                "and user.email (the factory commits as you)")
        raise CommitRefused(f"git refused the commit (a hook, or signing): {detail}")
    return git(worktree, "rev-parse", "HEAD").stdout.strip()


def key(entry):
    return entry["unit"], entry["worktree"]


def save_entry(root, entry):
    """Write one entry back under the lock without losing other entries."""
    with queue_lock(root):
        queue = read_queue(root)
        for index, old in enumerate(queue["units"]):
            if key(old) == key(entry):
                if old.get("hold"):  # a hold set while this step ran survives the step's own save
                    entry["hold"] = old["hold"]
                queue["units"][index] = entry
                break
        else:
            raise KeyError(f"{entry['unit']} vanished from the queue")
        write_queue(root, queue)


def stored(root, entry):
    """The entry as it is on disk now (a hold may have been set while a step ran)."""
    with queue_lock(root):
        return next((e for e in read_queue(root)["units"] if key(e) == key(entry)), None)


def log(root, **fields):
    """Append one line to log.jsonl. A single short append is atomic on POSIX."""
    line = json.dumps({"at": now(), **fields}) + "\n"
    with (var(root) / "log.jsonl").open("a") as stream:
        stream.write(line)


def read_jsonl(path):
    """Every readable line; a malformed line is skipped, never the whole file (defect type 6)."""
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def load_unit(worktree, unit_path, root=None):
    """Read a unit from its worktree, or from the main checkout when the worktree is gone."""
    for base in (worktree, root):
        if base and (Path(base) / unit_path).is_file():
            return json.loads((Path(base) / unit_path).read_text())
    raise FileNotFoundError(f"{unit_path} not found in {worktree}")
