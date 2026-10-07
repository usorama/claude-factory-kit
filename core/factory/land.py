"""Landing: catch up with main, run the suite on the merged result, open the PR, merge.

- catch_up: when main moved, replay only the unit's own commits onto the newest main
  (rebase --onto), refuse a cut with a merge commit, refuse on conflict. Used before the red
  check, the build check and landing, so a unit is always judged against today's main.
- merged-result suite: join the unit with the fetched main in a temporary worktree and
  run the whole suite there. Two changes can each pass alone and fail together.
- the merge names the exact head commit, and is refused when main moved since the check.
- landing modes (factory.toml "landing"): direct pushes the tested commit with plain git (any host:
  GitHub, GitHub Enterprise, GitLab, a bare repo; no gh); pr_merge opens a GitHub PR and merges it
  now; auto asks GitHub to merge once branch rules pass; pr_only leaves the merge to people.
  auto and pr_only end in state pr_open; watch() sees the merge later.
- a failing gh call is machinery (GhFailed), never the unit's fault; its stderr goes on the card.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from common import LANDINGS, git
from testrun import base_id, failed, run


class LandRefused(ValueError):
    """The unit cannot land; counts as a failed attempt."""


class GhFailed(RuntimeError):
    """A gh call failed (branch protection, permissions, network); the message carries gh's stderr."""


class MainMoved(RuntimeError):
    """Main moved during landing; try again next tick, no attempt is used."""


def restore_caches(worktree):
    """Undo changes to byte-code caches a repo tracks (a test run rewrites them), so they never block a rebase
    or count as the unit's change. Returns the restored paths."""
    tracked = [p for p in git(worktree, "ls-files", "-m").stdout.split()
               if "__pycache__" in Path(p).parts or p.endswith((".pyc", ".pyo"))]
    if tracked:
        git(worktree, "checkout", "--", *tracked)
    return tracked


def catch_up(worktree, base, check_base):
    """Return (refusal or None, the cut commit to compare against after the replay).
    Uses origin/<base> as last fetched: the tick fetches once, landing fetches again (one at a time)."""
    restore_caches(worktree)
    remote = f"origin/{base}"
    if git(worktree, "merge-base", "--is-ancestor", remote, "HEAD", check=False).returncode == 0:
        return None, check_base
    fork = git(worktree, "merge-base", check_base, remote).stdout.strip()
    if git(worktree, "rev-list", "--merges", f"{fork}..HEAD").stdout.strip():
        return "the unit branch contains a merge commit; re-cut the unit from main", None
    cut_commits = int(git(worktree, "rev-list", "--count", f"{fork}..{check_base}").stdout)
    rebase = git(worktree, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "rebase", "--empty=keep", "--onto", remote, fork, check=False)
    if rebase.returncode != 0:
        files = git(worktree, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
        git(worktree, "rebase", "--abort", check=False)
        return f"rebase onto {base} conflicts: {' '.join(files) or rebase.stderr.strip()[-200:]}", None
    if cut_commits == 0:
        return None, git(worktree, "rev-parse", remote).stdout.strip()
    replayed = git(worktree, "rev-list", "--reverse", f"{remote}..HEAD").stdout.split()
    return None, replayed[cut_commits - 1]


def patch_id(worktree, base):
    diff = git(worktree, "diff", "-U0", f"{base}..HEAD").stdout  # -U0: a moved context line is no change
    out = subprocess.run(["git", "patch-id", "--stable"], input=diff, cwd=worktree,
                         capture_output=True, text=True, check=True).stdout
    return out.split()[0] if out.strip() else ""


def merged_suite(worktree, fetched, tolerated, method="merge", message="factory: land unit"):
    """Build the exact commit that will land (the unit joined with the fetched base) and run the whole
    suite on it. Returns that commit: what is tested is what is pushed."""
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    ident = ["-c", "user.name=factory", "-c", "user.email=factory@localhost", "-c", "core.hooksPath=/dev/null"]
    with tempfile.TemporaryDirectory(prefix="factory-land-") as folder:
        merged = Path(folder) / "merged"
        git(worktree, "worktree", "add", "-q", "--detach", str(merged), fetched)
        try:
            if method == "squash":
                joined = git(merged, *ident, "merge", "-q", "--squash", head, check=False)
                if joined.returncode == 0:
                    joined = git(merged, *ident, "commit", "-q", "-m", message, check=False)
            else:
                how = ["--ff-only"] if method == "rebase" else ["--no-ff", "-m", message]
                joined = git(merged, *ident, "merge", "-q", *how, head, check=False)
            if joined.returncode != 0:
                raise LandRefused(f"the unit does not join main by {method}: {joined.stderr.strip()[-200:]}")
            code, records, collect_errors, _ = run(merged)
            if code == 5:
                raise LandRefused("the merged result selects no tests")
            bad = collect_errors + [t for t in failed(records) if base_id(t) not in set(tolerated)]
            if bad:
                raise LandRefused(f"{bad[0]} fails on the merged result with main")
            return git(merged, "rev-parse", "HEAD").stdout.strip()
        finally:
            git(worktree, "worktree", "remove", "--force", str(merged), check=False)


def push_direct(worktree, commit, base, fetched):
    """Land without any forge: push the tested commit to origin/<base>, only if <base> is still what was
    fetched (--force-with-lease names the expected value, so a moved main is refused, never overwritten)."""
    pushed = git(worktree, "push", "-q", f"--force-with-lease=refs/heads/{base}:{fetched}", "origin",
                 f"{commit}:refs/heads/{base}", check=False)
    if pushed.returncode != 0:
        raise MainMoved(f"{base} moved since the check (push refused); landing tries again next tick")
    git(worktree, "fetch", "-q", "origin", base, check=False)


def origin(root):
    """(origin URL as configured, host). host is "local" for a path or file URL, "" when there is no origin.
    The configured URL is read before any insteadOf rewrite: it names the host the team uses."""
    url = git(root, "config", "--get", "remote.origin.url", check=False).stdout.strip()
    if not url:
        return "", ""
    match = re.match(r"^(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|[^@/]+@)([^/:]+)", url)
    return url, (match.group(1) if match and not url.startswith(("/", ".", "file:")) else "local")


def is_github(host, gh="gh"):
    """github.com, or a GitHub Enterprise host gh is signed in to."""
    if host in ("", "local"):
        return False
    if host == "github.com":
        return True
    return bool(shutil.which(gh)) and subprocess.run([gh, "auth", "status", "--hostname", host], capture_output=True,
                                                     text=True, check=False).returncode == 0


def protection(url, base, gh="gh"):
    """'protected', 'open' or 'unknown', read through gh api (needs read access to the branch settings)."""
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    if not match or not shutil.which(gh):
        return "unknown"
    seen = subprocess.run([gh, "api", f"repos/{match.group(1)}/{match.group(2)}/branches/{base}/protection"],
                          capture_output=True, text=True, check=False)
    if seen.returncode == 0:
        try:
            rules = json.loads(seen.stdout)
        except ValueError:
            return "unknown"
        return "protected" if rules.get("required_pull_request_reviews") or rules.get("required_status_checks") else "open"
    return "open" if "Branch not protected" in seen.stdout + seen.stderr else "unknown"


def landing_plan(root, base="main", gh="gh"):
    """The landing mode init picks, and why. On GitHub the factory never pushes to the base itself: it opens a
    pull request per unit and merges it (pr_merge), or lets GitHub merge it when the base is protected (auto).
    Plain git (direct) is the default only when the origin is not a GitHub host."""
    url, host = origin(root)
    if not host:
        return {"host": "none (no origin yet)", "github": False, "landing": "direct",
                "why": "no origin yet: direct (plain git); run factory init --plan again after adding a GitHub origin"}
    if not is_github(host, gh):
        return {"host": host, "github": False, "landing": "direct",
                "why": f"origin {host} is not a GitHub host gh can reach: direct (plain git push of the tested commit)"}
    state = protection(url, base, gh)
    if state == "protected":
        return {"host": host, "github": True, "landing": "auto",
                "why": f"origin is GitHub ({host}) and {base} is protected: auto (a PR per unit; GitHub merges it when "
                       "its required reviews and checks pass; the repo must allow auto-merge)"}
    unknown = "" if state == "open" else f" (the protection of {base} could not be read; set landing = \"auto\" if it needs reviews)"
    return {"host": host, "github": True, "landing": "pr_merge",
            "why": f"origin is GitHub ({host}): pr_merge (a PR per unit with the review verdict, merged by the factory "
                   f"after its checks; never a direct push to {base}){unknown}"}


def host_modes(root):
    """(host, landing modes that work): plain git works everywhere; pull request modes need gh for a GitHub host."""
    plan = landing_plan(root)
    return plan["host"], list(LANDINGS) if plan["github"] else ["direct"]


def effective_landing(root, cfg):
    """The mode in use: the one factory.toml names, else the host's default (pr_merge on GitHub, direct elsewhere).
    Never asks gh api at landing time."""
    if cfg.get("landing"):
        return cfg["landing"], "set in factory.toml"
    _, host = origin(root)
    if is_github(host):
        return "pr_merge", f"default for a GitHub origin ({host})"
    return "direct", f"default for a non-GitHub origin ({host or 'none'})"


class DirectToGitHubRefused(RuntimeError):
    """direct would push to the base of a GitHub origin, but factory.toml does not say landing = "direct"."""


def gh_call(gh, worktree, *args):
    try:
        return subprocess.run([gh, *args], cwd=worktree, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise GhFailed(f"gh {' '.join(args[:2])} failed: {detail.strip()[-400:]}") from error


def land(worktree, unit, base, tolerated, review_text, gh="gh", pr=None, mode="direct", method="merge",
         direct_explicit=False):
    """Return (PR address or the landed commit, merged now?). The caller already caught up and checked the unit.
    direct: plain git, no forge (GitHub, GitHub Enterprise, GitLab, a bare repo). pr_merge, auto, pr_only: GitHub."""
    if mode == "direct" and not direct_explicit and is_github(origin(worktree)[1], gh):
        raise DirectToGitHubRefused(f"the origin is GitHub: the factory never pushes to {base} unless factory.toml says "
                                    'landing = "direct"; use pr_merge (the default) or auto')
    fetched = git(worktree, "rev-parse", f"origin/{base}").stdout.strip()
    title = unit.get("title") or unit["paragraph"].split(".")[0]
    tested = merged_suite(worktree, fetched, tolerated, method, f"{title}\n\nFactory review form:\n{review_text}")
    if mode == "direct":
        push_direct(worktree, tested, base, fetched)
        return tested, True
    branch = git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "push", "-q", "-u", "--force-with-lease", "origin", branch)
    if not pr:
        body = "\n".join([unit["paragraph"], "", "Factory review verdict:", review_text or "(none)", "",
                          "Tests:", *unit["tests"], "", "Files:", *unit["files"], "",
                          f"Estimate: {unit.get('estimate_minutes', '?')} minutes"])
        pr = gh_call(gh, worktree, "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body)
    number = pr_number(pr)
    gh_call(gh, worktree, "pr", "comment", number, "--body", "Factory review form:\n" + review_text)
    if mode == "pr_only":
        return pr, False
    if mode == "pr_merge":
        remote_now = git(worktree, "ls-remote", "origin", f"refs/heads/{base}").stdout.split()
        if not remote_now or remote_now[0] != fetched:
            raise MainMoved(f"{base} moved since the check; landing tries again next tick")
    auto = ["--auto"] if mode == "auto" else []
    gh_call(gh, worktree, "pr", "merge", number, *auto, f"--{method}", "--match-head-commit", head)
    return pr, mode == "pr_merge"


def pr_number(pr):
    return re.sub(r".*/", "", pr.rstrip("/"))


def pr_state(worktree, pr, gh="gh"):
    """OPEN, MERGED or CLOSED, as GitHub reports it."""
    return json.loads(gh_call(gh, worktree, "pr", "view", pr_number(pr), "--json", "state"))["state"]
