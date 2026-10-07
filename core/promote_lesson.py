#!/usr/bin/env python3
"""Promote a proven project lesson into the shared plugin. Used by `factory promote-lesson` and every adapter.

Level 1 (local): lessons, rules and the defect library live in the project and work at once.
Level 2 (shared): a lesson that is applied and has at least two strikes becomes a change on a new
branch of a checkout of the plugin repo:
  - the lesson record is added to core/templates/lessons.shared.jsonl;
  - a rule lesson adds its line under "Promoted rules" in core/templates/defect-library.md (the reviewer
    removes one older line before merging: rules grow only by replacing);
  - a check lesson copies the project's changed factory scripts (--files factory/x.py) into
    core/factory/;
  - the kit's patch version goes up (VERSION and .claude-plugin/plugin.json) and CHANGELOG.md gets an entry.
The project's name stays out of everything by default (branch lesson/<id>, the shared record, the CHANGELOG):
it can be a company or client name. --name-project puts it in, when the person wants that.
It commits on the branch with the person's own git identity and prints the exact text that would leave this machine, and the remote it would go to.
Pushing is a separate step a person types: --push --confirm-remote <that exact URL>; it pushes the branch and opens
a pull request with gh. Lesson text can name a project, so nothing is pushed without that typed URL. After the
merge, users update the kit (Claude Code: /plugin update; others: git pull) and run
`factory init --plan` to take the change.
Usage: promote_lesson.py <lesson id> --plugin-repo DIR [--project DIR] [--files factory/x.py ...] [--name-project]
       promote_lesson.py <lesson id> --plugin-repo DIR --push --confirm-remote <remote URL>
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


class PromoteRefused(ValueError):
    """The lesson is not proven, or the plugin checkout is not ready."""


def run(cwd, *command):
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def branch_name(project, ident, name_project=False):
    return "lesson/" + re.sub(r"[^a-z0-9-]+", "-", (f"{project.name}-{ident}" if name_project else ident).lower())


def remote_url(repo):
    return subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=repo, capture_output=True,
                          text=True).stdout.strip()


def promote(project, repo, ident, files=(), name_project=False):
    lessons = [json.loads(line) for line in (project / ".ai/lessons.jsonl").read_text().splitlines() if line.strip()]
    lesson = next((item for item in lessons if item.get("id") == ident), None)
    if lesson is None:
        raise PromoteRefused(f"no lesson {ident} in {project}/.ai/lessons.jsonl")
    if lesson.get("status") != "applied" or len(lesson.get("strikes", [])) < 2:
        raise PromoteRefused(f"{ident} is not proven: it needs status applied and two strikes "
                             f"(it is {lesson.get('status', 'open')} with {len(lesson.get('strikes', []))})")
    core, manifest, version_file = repo / "core", repo / ".claude-plugin/plugin.json", repo / "VERSION"
    if not manifest.is_file() or not version_file.is_file() or not (core / "factory").is_dir():
        raise PromoteRefused(f"{repo} is not a checkout of the plugin repo")
    if run(repo, "git", "status", "--porcelain"):
        raise PromoteRefused(f"{repo} has uncommitted changes")
    if lesson["shape"] == "check" and not files:
        raise PromoteRefused("a check lesson needs --files: the project's factory scripts that carry the check")
    branch = branch_name(project, ident, name_project)
    run(repo, "git", "checkout", "-q", "-b", branch)
    shared = core / "templates/lessons.shared.jsonl"
    with shared.open("a") as stream:
        stream.write(json.dumps({**lesson, **({"from_project": project.name} if name_project else {})}) + "\n")
    if lesson["shape"] == "rule":
        library = core / "templates/defect-library.md"
        text = library.read_text()
        if "## Promoted rules" not in text:
            text += "\n## Promoted rules\n"
        library.write_text(text + f"- **{lesson['title']}.** {lesson['lesson']}\n")
    for name in files:
        if not name.startswith("factory/") or not (project / name).is_file():
            raise PromoteRefused(f"{name} is not a file under the project's factory/")
        shutil.copy2(project / name, core / name)
    data = json.loads(manifest.read_text())
    major, minor, patch = map(int, data["version"].split("."))
    data["version"] = f"{major}.{minor}.{patch + 1}"
    manifest.write_text(json.dumps(data, indent=2) + "\n")
    version_file.write_text(data["version"] + "\n")
    changelog = repo / "CHANGELOG.md"
    source = f" from {project.name}" if name_project else ""
    entry = (f"## {data['version']} - {date.today().isoformat()}\n- Promoted lesson {ident}{source} "
             f"({lesson['shape']}): {lesson['title']}. {lesson['lesson']}\n\n")
    old = changelog.read_text()
    changelog.write_text(old.replace("\n## ", "\n" + entry + "## ", 1) if "\n## " in old else old + "\n" + entry)
    run(repo, "git", "add", "-A")
    run(repo, "git", "commit", "-q", "-m", f"Promote lesson {ident}: {lesson['title']} (factory {data['version']})")
    return {"branch": branch, "version": data["version"], "pushed": False, "remote": remote_url(repo) or "(none)",
            "text": run(repo, "git", "show", "--format=%B", "HEAD"),
            "next": "Read the text above: it leaves this machine on push. To push, the person types: factory promote-lesson "
                    f"{ident} --plugin-repo {repo} --push --confirm-remote <the remote URL above>"}


def push(project, repo, ident, confirm_remote):
    """Push an existing lesson branch and open its pull request, only when the person typed the remote URL."""
    url = remote_url(repo)
    names = [branch_name(project, ident), branch_name(project, ident, True)]
    branch = next((b for b in names if not subprocess.run(["git", "rev-parse", "--verify", "-q", b], cwd=repo,
                                                         capture_output=True).returncode), names[0])
    if subprocess.run(["git", "rev-parse", "--verify", "-q", branch], cwd=repo, capture_output=True).returncode:
        raise PromoteRefused(f"no branch {branch} in {repo}; run promote-lesson without --push first and read its text")
    text = run(repo, "git", "show", "--format=%B", branch)
    if not url or confirm_remote != url:
        raise PromoteRefused(f"pushing sends this text to {url or '(no remote)'}; nothing was pushed. Read it, then type "
                             f"--confirm-remote {url or '<url>'} exactly:\n{text}")
    run(repo, "git", "push", "-q", "-u", "origin", branch)
    pr = run(repo, "gh", "pr", "create", "--head", branch, "--title", text.splitlines()[0], "--body",
             f"{text}\n\nRules grow only by replacing: remove one older line before merging a rule.")
    return {"branch": branch, "pushed": True, "remote": url, "pr": pr}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ident")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--plugin-repo", type=Path, required=True)
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--push", action="store_true", help="push the branch made earlier; needs --confirm-remote")
    parser.add_argument("--name-project", action="store_true",
                        help="put the project's name in the branch, the shared record and the CHANGELOG (off by default)")
    parser.add_argument("--confirm-remote", default="", help="the exact remote URL, typed by the person")
    args = parser.parse_args(argv)
    try:
        if args.push:
            result = push(args.project.resolve(), args.plugin_repo.resolve(), args.ident, args.confirm_remote)
        else:
            result = promote(args.project.resolve(), args.plugin_repo.resolve(), args.ident, args.files, args.name_project)
    except (PromoteRefused, OSError, subprocess.CalledProcessError) as error:
        print(f"promote refused: {getattr(error, 'stderr', '') or error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
