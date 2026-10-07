"""Landing: catch up with main, run the suite on the merged result, open the PR, merge.

- catch_up: when main moved, replay only the unit's own commits onto the newest main
  (rebase --onto), refuse a cut with a merge commit, refuse on conflict. Used before the red
  check, the build check and landing, so a unit is always judged against today's main.
- merged-result suite: join the unit with the fetched main in a temporary worktree and
  run the whole suite there. Two changes can each pass alone and fail together.
- the merge names the exact head commit, and is refused when main moved since the check.
- landing modes (factory.toml "landing"): direct merges now; auto asks GitHub to merge once the
  branch protection rules are met (required reviews, status checks); pr_only opens the PR and
  leaves the merge to people. auto and pr_only end in state pr_open; watch() sees the merge later.
- a failing gh call is machinery (GhFailed), never the unit's fault; its stderr goes on the card.
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

from common import git
from testrun import base_id, failed, run


class LandRefused(ValueError):
    """The unit cannot land; counts as a failed attempt."""


class GhFailed(RuntimeError):
    """A gh call failed (branch protection, permissions, network); the message carries gh's stderr."""


class MainMoved(RuntimeError):
    """Main moved during landing; try again next tick, no attempt is used."""


def catch_up(worktree, base, check_base):
    """Return (refusal or None, the cut commit to compare against after the replay).
    Uses origin/<base> as last fetched: the tick fetches once, landing fetches again (one at a time)."""
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


def merged_suite(worktree, fetched, tolerated):
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="factory-land-") as folder:
        merged = Path(folder) / "merged"
        git(worktree, "worktree", "add", "-q", "--detach", str(merged), fetched)
        try:
            joined = git(merged, "-c", "user.name=factory", "-c", "user.email=factory@localhost",
                         "merge", "-q", "--no-edit", head, check=False)
            if joined.returncode != 0:
                raise LandRefused("the unit does not merge cleanly with main")
            code, records, collect_errors, _ = run(merged)
            if code == 5:
                raise LandRefused("the merged result selects no tests")
            bad = collect_errors + [t for t in failed(records) if base_id(t) not in set(tolerated)]
            if bad:
                raise LandRefused(f"{bad[0]} fails on the merged result with main")
        finally:
            git(worktree, "worktree", "remove", "--force", str(merged), check=False)


def gh_call(gh, worktree, *args):
    try:
        return subprocess.run([gh, *args], cwd=worktree, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise GhFailed(f"gh {' '.join(args[:2])} failed: {detail.strip()[-400:]}") from error


def land(worktree, unit, base, tolerated, review_text, gh="gh", pr=None, mode="direct", method="merge"):
    """Return (PR address, merged now?). The caller already caught up and checked the unit."""
    fetched = git(worktree, "rev-parse", f"origin/{base}").stdout.strip()
    merged_suite(worktree, fetched, tolerated)
    branch = git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "push", "-q", "-u", "--force-with-lease", "origin", branch)
    if not pr:
        body = "\n".join([unit["paragraph"], "", "Tests:", *unit["tests"], "", "Files:", *unit["files"],
                          "", f"Estimate: {unit.get('estimate_minutes', '?')} minutes"])
        pr = gh_call(gh, worktree, "pr", "create", "--base", base, "--head", branch,
                     "--title", unit.get("title") or unit["paragraph"].split(".")[0], "--body", body)
    number = pr_number(pr)
    gh_call(gh, worktree, "pr", "comment", number, "--body", "Factory review form:\n" + review_text)
    if mode == "pr_only":
        return pr, False
    if mode == "direct":
        remote_now = git(worktree, "ls-remote", "origin", f"refs/heads/{base}").stdout.split()
        if not remote_now or remote_now[0] != fetched:
            raise MainMoved(f"{base} moved since the check; landing tries again next tick")
    auto = ["--auto"] if mode == "auto" else []
    gh_call(gh, worktree, "pr", "merge", number, *auto, f"--{method}", "--match-head-commit", head)
    return pr, mode == "direct"


def pr_number(pr):
    return re.sub(r".*/", "", pr.rstrip("/"))


def pr_state(worktree, pr, gh="gh"):
    """OPEN, MERGED or CLOSED, as GitHub reports it."""
    return json.loads(gh_call(gh, worktree, "pr", "view", pr_number(pr), "--json", "state"))["state"]
