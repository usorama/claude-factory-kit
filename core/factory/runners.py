"""The step runners. Builder and reviewer are the commands pinned in the roles file (factory.toml).

A role command gets its prompt on stdin, runs in the unit's work folder, and names its model.
Placeholders: {model} {effort} {max_turns} {max_budget} {no_network}, and {tools} / {deny}, which
expand into the role's lists. Environment: FACTORY_ROLE, FACTORY_REVIEW_FORM (the reviewer writes
its JSON form there), DISABLE_AUTOUPDATER=1, and the Claude token from a file if one is kept.
The prompt comes from the role's versioned prompt file (for example .ai/prompts/builder.v1.md).
Output kinds: claude-json (claude -p --output-format json), codex-jsonl (codex exec --json), text.
Shapes were copied from real runs: tests/fixtures/claude-json-real.json, codex-jsonl-real.jsonl.
A model or machinery failure is never the unit's fault (see classify). Each runner returns
(ok, message, extra fields for the log); every model step's extra is its receipt: role, tool,
model, effort, prompt file and hash, caps, and for the reviewer the independence used.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path

import crew
from build_check import build_check
from common import (BudgetReached, budget_gate, config, config_problem, git, label, read_queue, review_independence,
                    spend, var, work_folder_problem)
from drive import Retry, RetryOnce
from modelrun import FORM_NAME, NO_NETWORK, claude_env, claude_usage, classify, fill, role_command, run_tracked
from land import (DirectToGitHubRefused, GhFailed, MainMoved, catch_up, effective_landing, land, patch_id, pr_state,
                  restore_caches)
from red_check import red_check, tolerated_tests
from review import KINDS, file_notes, parse, summary

def make_runners(root, gh="gh"):
    root = Path(root)
    cfg = config(root)
    problem = config_problem(cfg, root)
    if problem:
        raise ValueError(problem)
    base = cfg["base"]

    def context(entry):
        worktree = Path(entry["worktree"])
        problem = work_folder_problem(root, worktree)
        if problem:  # checked before any reset, clean or checkout touches the folder
            raise RuntimeError(f"refusing to touch {worktree}: {problem}")
        unit = json.loads((worktree / entry["unit"]).read_text())
        return worktree, unit, label(entry["unit"])

    def caught_up(entry, worktree):
        start = entry.get("built_from") or git(worktree, "rev-parse", "HEAD").stdout.strip()
        refusal, check_base = catch_up(worktree, base, start)
        if not refusal and "built_from" in entry:
            entry["built_from"] = check_base
        return refusal, check_base

    def label_of(worktree):
        entry = next((e for e in read_queue(root)["units"] if Path(e["worktree"]) == Path(worktree)), None)
        return label(entry["unit"]) if entry else Path(worktree).name

    def run_role(name, values, worktree, form=None, estimate=None):
        role = cfg["roles"][name]
        short = "build" if name == "builder" else "review"
        prompt_path = root / role["prompt"]
        prompt = fill(prompt_path.read_text(), {**values, "kinds": ", ".join(KINDS)})
        command = role_command(role, {"model": role["model"], "effort": role["effort"], "no_network": NO_NETWORK,
                                      "max_turns": cfg[f"max_turns_{short}"],
                                      "max_budget": cfg[f"max_budget_{short}_usd"]})
        env = claude_env(name)
        if form:
            env["FACTORY_REVIEW_FORM"] = str(form)
        minutes = cfg[f"{short}_timeout_minutes"]
        if name == "builder" and estimate:  # time box: twice the estimate, at least 20 minutes
            minutes = min(minutes, max(20, 2 * estimate))
        receipt = {"role": name, "tool": role["tool"], "model": role["model"], "effort": role["effort"],
                   "prompt": role["prompt"], "prompt_sha": hashlib.sha256(prompt_path.read_bytes()).hexdigest()[:12],
                   "settings": {"max_turns": cfg[f"max_turns_{short}"], "max_budget_usd": cfg[f"max_budget_{short}_usd"]}}
        if name == "reviewer":
            receipt["independence"] = review_independence(cfg)[0]
        try:
            budget_gate(root, cfg)
        except BudgetReached as reached:  # nothing starts; the unit waits without using an attempt
            raise Retry(str(reached), counts=False) from reached
        started = time.monotonic()
        try:
            result = run_tracked(command, worktree, prompt, env, minutes * 60, var(root) / "pids" / f"{label_of(worktree)}.pid")
        except subprocess.TimeoutExpired as error:
            if name == "builder" and estimate:  # over the time box is the unit's size, not machinery
                return None, {**receipt, "minutes_model": minutes, "timed_out": True}
            raise RetryOnce(f"{name} timed out after {minutes} minutes") from error
        receipt["minutes_model"] = round((time.monotonic() - started) / 60, 2)
        spend(root, name, claude_usage(result.stdout)[1].get("cost_usd") if role["output"] == "claude-json" else None)
        try:
            budget_gate(root, cfg)  # crossing the cap raises the one card now; the next run will not start
        except BudgetReached:
            pass
        text, extra = classify(result.returncode, result.stdout, result.stderr, role["output"])
        return text, {**extra, **receipt}

    def red(entry):
        worktree, unit, name = context(entry)
        refusal, _ = caught_up(entry, worktree)
        if refusal:
            return False, refusal, {}
        brief = worktree / ".ai/specs" / f"{name}.md"
        if not brief.is_file():  # trigger unit_without_brief: Quill writes it, brief_check judges it
            try:
                for agent in crew.triggered("unit_without_brief", {"files": unit["files"]}):
                    crew.run_agent(root, agent, "unit_without_brief", name,
                                   {"unit": str(worktree / entry["unit"]), "unit_data": unit, "brief": str(brief),
                                    "tests": unit["tests"]}, workdir=worktree)
            except crew.CrewRefused as error:  # a brief that fails its check is a cut problem
                return False, str(error), {}
            git(worktree, "add", "--", str(brief.relative_to(worktree)))
            git(worktree, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "-c", "core.hooksPath=/dev/null",
                "commit", "-q", "-m", f"{name}: brief by quill")
        try:
            return True, json.dumps(red_check(entry["unit"], worktree, tolerated_tests(root, entry))), {}
        except ValueError as error:
            return False, str(error), {}

    def build(entry):
        worktree, unit, name = context(entry)
        if entry["attempts"] > 0 or "built_from" in entry:  # a rebuild or a retry starts from the cut
            git(worktree, "reset", "-q", "--hard", entry.get("built_from", "HEAD"))
            git(worktree, "clean", "-fdq")
        entry["built_from"] = git(worktree, "rev-parse", "HEAD").stdout.strip()
        rebuild = (f"This is a rebuild from the cut. The previous attempt was refused: {entry['last_reject']}"
                   if entry.get("last_reject") else "")
        report, extra = run_role("builder", {
            "brief": worktree / ".ai/specs" / f"{name}.md", "unit": worktree / entry["unit"],
            "tests": " ".join(unit["tests"]), "files": " ".join(unit["files"]), "rebuild": rebuild}, worktree,
            estimate=unit.get("estimate_minutes"))
        if report is None:
            return False, f"the builder passed its time box of twice the estimate ({unit.get('estimate_minutes')} minutes)", extra
        reports = var(root) / "reports"
        reports.mkdir(exist_ok=True)
        (reports / f"{name}.r{entry['attempts'] + 1}.md").write_text(report)
        present = [f for f in unit["files"] if (worktree / f).exists()]
        if present:
            git(worktree, "add", "--", *present)
        if git(worktree, "diff", "--cached", "--quiet", check=False).returncode == 0:
            if extra.get("denials"):  # the builder was stopped by a permission, not by the unit
                raise RetryOnce(f"the builder was denied a tool: {extra['first_denial']}")
            return False, "the builder changed no unit file", extra
        git(worktree, "-c", "user.name=factory", "-c", "user.email=factory@localhost",
            "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", f"{name}: build round {entry['attempts'] + 1}")
        restore_caches(worktree)
        return True, report[-2000:], extra

    def check(entry):
        worktree, _, _ = context(entry)
        refusal, check_base = caught_up(entry, worktree)
        if refusal:
            return False, refusal, {}
        try:
            result = build_check(entry["unit"], worktree, check_base, tolerated_tests(root, entry))
            return True, json.dumps(result), {}
        except ValueError as error:
            return False, str(error), {}

    def review(entry):
        """A fresh session that sees only the brief, the unit and the diff, never the builder's report."""
        worktree, unit, name = context(entry)
        form = worktree / FORM_NAME
        form.unlink(missing_ok=True)
        try:
            _, extra = run_role("reviewer", {
                "brief": worktree / ".ai/specs" / f"{name}.md", "unit": worktree / entry["unit"],
                "base": entry["built_from"], "tests": " ".join(unit["tests"]), "form": form}, worktree, form)
            try:
                data = json.loads(form.read_text())
            except (OSError, ValueError) as error:
                raise RetryOnce(f"no usable review form: {error}") from error
        finally:  # keep the form, then undo the sabotage and anything else the reviewer touched
            forms = var(root) / "reviews"
            forms.mkdir(exist_ok=True)
            if form.exists():
                (forms / f"{name}.r{entry['attempts'] + 1}.json").write_bytes(form.read_bytes())
                form.unlink()
            git(worktree, "checkout", "--", ".")
            git(worktree, "clean", "-fdq")
        try:
            parsed = parse(data, unit["files"])
        except ValueError as error:
            raise RetryOnce(f"no usable review form: {error}") from error
        crew.record(root, "inspector-grumble", "check_passed", name, parsed["verdict"], extra)
        if parsed["verdict"] == "PASS":  # the other check_passed agents: lockjaw on risk, thomasina on a surface
            scope = {"files": unit["files"], "risk_class": unit.get("risk_class")}
            for agent in [a for a in crew.triggered("check_passed", scope) if a != "inspector-grumble"]:
                lens = {"unit": str(worktree / entry["unit"]), "brief": str(worktree / ".ai/specs" / f"{name}.md"),
                        "base": entry["built_from"], "tests": unit["tests"], "unit_files": unit["files"], **scope}
                try:
                    crew.run_agent(root, agent, "check_passed", name, lens, workdir=worktree)
                finally:
                    git(worktree, "checkout", "--", ".")
                    git(worktree, "clean", "-fdq")
                if lens["parsed"]["verdict"] == "REJECT":
                    parsed = {**lens["parsed"], "notes": parsed["notes"] + lens["parsed"]["notes"]}
                    break
        file_notes(root, name, parsed["notes"])
        entry["cut_finding"] = parsed["cut"]
        entry["review_text"] = summary(parsed)
        entry["reviewed_patch"] = patch_id(worktree, entry["built_from"])
        return parsed["verdict"] == "PASS", entry["review_text"], {"verdict": parsed["verdict"], **extra}

    def land_step(entry):
        worktree, unit, _ = context(entry)
        if git(worktree, "fetch", "-q", "origin", base, check=False).returncode != 0:
            raise Retry(f"cannot fetch origin/{base}")
        refusal, check_base = caught_up(entry, worktree)
        if refusal:
            return False, refusal, {}
        if patch_id(worktree, check_base) != entry.get("reviewed_patch"):
            raise Retry("the change differs from the reviewed change; it goes back to review", "checked")
        tolerated = tolerated_tests(root, entry)
        try:  # cheap integrity checks; the full suite runs on the merged result
            build_check(entry["unit"], worktree, check_base, tolerated, guard=False, suite=False)
            mode, _ = effective_landing(root, cfg)
            entry["pr"], merged = land(worktree, unit, base, tolerated, entry.get("review_text", ""), gh,
                                       entry.get("pr"), mode, cfg["merge_method"], cfg["landing"] == "direct")
        except MainMoved as moved:
            raise Retry(str(moved)) from moved
        except (GhFailed, DirectToGitHubRefused) as error:
            raise RetryOnce(str(error)) from error
        except ValueError as error:
            return False, str(error), {}
        landed = {"landed_commit": entry["pr"]} if mode == "direct" else {"pr": entry["pr"]}
        return True, entry["pr"], {**landed, **({} if merged else {"to_state": "pr_open"})}

    def watch(entry):
        """A PR left to GitHub (auto) or to people (pr_only): landed when merged."""
        try:
            state = pr_state(entry["worktree"], entry["pr"], gh)
        except GhFailed as error:
            raise RetryOnce(str(error)) from error
        if state == "MERGED":
            return True, f"merged: {entry['pr']}", {"pr": entry["pr"]}
        if state == "CLOSED":
            raise RuntimeError(f"{entry['pr']} was closed without a merge")
        raise Retry(f"{entry['pr']} waits for required reviews or checks", counts=False)

    return {"red": red, "build": build, "check": check, "review": review, "land": land_step, "watch": watch}
