"""Start crew agents on their triggers (factory/crew.toml), check their answers by code, keep records.

  crew.py before-cut <row>        Sweeper Sid, then the plan coverage auditor (the chief of staff asks code)
  crew.py handoff <file>          the claim verifier on a handoff or any status text
  crew.py research <file>         the claim verifier on a research file; on MATCH code adds "Reviewed-by: <model> PASS"
  crew.py retro <daily report>    the claim verifier on the report, the scorecard, the Bookie's words
Other triggers fire inside the clock and the commands: an untriaged backlog row (tick), a unit with no
brief (red step), a passed build check (review step), a landed row (tick.py close-row), the daily report
and the retro (factory retro). An agent's answer is a JSON form; code accepts or refuses it. Records:
var/factory/crew/<agent>.jsonl. Memory: crew/<agent>/memory.md in the project, appended by code.
"""
import fnmatch
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from brief_check import BriefRefused, check_brief
from common import config, log, now, read_jsonl, var
from modelrun import NO_NETWORK, claude_env, classify, fill, role_command, run_tracked

HERE = Path(__file__).resolve().parent
OUTPUT = ".factory-crew-{name}.json"
TRIAGE_SIZES, SWEEP_CRITERIA = ("S", "M", "L"), ("C1", "C2", "C3", "C4", "C5", "NONE")
COVERAGE = ("COVERED", "FOLDED", "DEFERRED", "DROPPED", "ORPHANED")
CONFORMANCE = ("MET", "PARTIAL", "DEVIATION", "MISSING", "DEFERRED-DISCLOSED", "SPEC_SKIP")
BLOCKING_CONFORMANCE = ("DEVIATION", "MISSING", "SPEC_SKIP")
CLAIMS = ("MATCH", "PARTIAL", "MISMATCH", "UNVERIFIABLE")


class CrewRefused(ValueError):
    """An agent's answer broke its form, or its verdict blocks the step."""


def load(root=None):
    return tomllib.loads((HERE / "crew.toml").read_text())


def matches(files, patterns):
    return any(fnmatch.fnmatch(f, p) or fnmatch.fnmatch(Path(f).name, p) for f in files for p in patterns)


def triggered(event, context, crew=None):
    """The agents a trigger starts, in table order. context: files, risk_class."""
    crew = crew or load()
    rules, files = crew["rules"], context.get("files", [])
    when = {"always": True,
            "risk": context.get("risk_class") in rules["risk_classes"] or matches(files, rules["risk_paths"]),
            "surface": matches(files, rules["surface_paths"])}
    return [t["agent"] for t in crew["triggers"] if t["event"] == event and when[t["when"]]]


def need(data, key, kind):
    if not isinstance(data.get(key), kind):
        raise CrewRefused(f"the answer needs {key} ({kind.__name__})")
    return data[key]


def check_form(form, data, context):
    """Return the verdict word for the record, or raise CrewRefused when the form is broken."""
    if form == "triage":
        need(data, "row", str), need(data, "evidence", str), need(data, "files", list), need(data, "done_property", str)
        if type(data.get("still_real")) is not bool or data.get("size") not in TRIAGE_SIZES:
            raise CrewRefused("triage needs still_real (true or false) and size S, M or L")
        return "real" if data["still_real"] else "not real"
    if form == "sweep":
        if data.get("verdict") not in ("done", "not_done") or data.get("criterion") not in SWEEP_CRITERIA:
            raise CrewRefused("a sweep needs verdict done or not_done and a criterion C1 to C5 or NONE")
        if data["verdict"] == "done" and (data["criterion"] == "NONE" or not data.get("evidence_command")):
            raise CrewRefused("a done verdict needs a criterion and an evidence_command code can re-run")
        return data["verdict"]
    if form == "coverage":
        items = need(data, "items", list)
        if any(item.get("status") not in COVERAGE for item in items):
            raise CrewRefused(f"each coverage item needs a status from {', '.join(COVERAGE)}")
        dropped = need(data, "dropped", list) + [i for i in items if i.get("status") == "DROPPED"]
        need(data, "orphaned", list)
        return "dropped" if dropped else "covered"
    if form == "brief":
        try:
            check_brief(Path(context["brief"]).read_text(), context["unit_data"])
        except (OSError, BriefRefused) as error:
            raise CrewRefused(f"the brief was refused: {error}") from error
        return "brief ok"
    if form == "review":
        from review import parse
        try:
            context["parsed"] = parse(data, context.get("unit_files", []))
        except ValueError as error:
            raise CrewRefused(str(error)) from error
        return context["parsed"]["verdict"]
    if form == "conformance":
        findings = need(data, "findings", list)
        if not findings or any(f.get("classification") not in CONFORMANCE for f in findings):
            raise CrewRefused(f"each finding needs a classification from {', '.join(CONFORMANCE)}")
        return "deviates" if any(f["classification"] in BLOCKING_CONFORMANCE for f in findings) else "conforms"
    if form == "claims":
        claims = need(data, "claims", list)
        if not claims or any(c.get("verdict") not in CLAIMS for c in claims):
            raise CrewRefused(f"each claim needs a verdict from {', '.join(CLAIMS)}")
        return "mismatch" if any(c["verdict"] == "MISMATCH" for c in claims) else "match"
    if form == "scorecard":
        need(data, "lines", dict), need(data, "most_expensive", str)
        return "ok"
    raise CrewRefused(f"unknown form {form}")


def record(root, name, event, subject, verdict, receipt, ok=True, note=""):
    path = var(root) / "crew"
    path.mkdir(exist_ok=True)
    line = {"at": now(), "agent": name, "event": event, "subject": subject, "verdict": verdict, "ok": ok,
            "note": note[:300], **{k: receipt.get(k) for k in ("model", "tool", "prompt_sha", "cost_usd")}}
    with (path / f"{name}.jsonl").open("a") as stream:
        stream.write(json.dumps(line) + "\n")
    log(Path(root), event="crew", agent=name, trigger=event, subject=subject, verdict=verdict, ok=ok)


def remember(root, name, line):
    if line and str(line).strip():
        memory = Path(root) / "crew" / name / "memory.md"
        memory.parent.mkdir(parents=True, exist_ok=True)
        with memory.open("a") as stream:
            stream.write(f"- {now()[:10]}: {' '.join(str(line).split())[:200]}\n")


def run_agent(root, name, event, subject, context, workdir=None, run=subprocess.run):
    """Run one crew agent with the model pinned for its role; return (data, verdict). Never falls back."""
    root, crew, cfg = Path(root), load(), config(root)
    agent = crew["agents"][name]
    role = cfg["roles"][agent["uses_role"]]
    workdir = Path(workdir or root)
    output = workdir / OUTPUT.format(name=name)
    output.unlink(missing_ok=True)
    prompt_path = root / agent["prompt"]
    from review import KINDS
    prompt = fill(prompt_path.read_text(), {
        "name": name, "output": output, "context": json.dumps({k: v for k, v in context.items() if k != "unit_data"})[:6000],
        "kinds": ", ".join(KINDS), "brief": context.get("brief", ""), "unit": context.get("unit", ""),
        "base": context.get("base", ""), "tests": " ".join(context.get("tests", [])), "form": output})
    tool = role["tool"]
    command = crew["commands"].get(tool) or role.get("command") or cfg["roles"]["reviewer"]["command"]
    template = {"command": command,
                "tools": agent["sandbox"] if tool == "codex" else agent["tools"], "deny": []}
    if tool == "codex":
        template["tools"] = [agent["sandbox"]]
    command = role_command(template, {"model": role["model"], "effort": agent["effort"], "no_network": NO_NETWORK,
                                      "max_turns": 40, "max_budget": cfg["max_budget_review_usd"]})
    env = claude_env(f"crew:{name}")
    env["FACTORY_CREW_OUTPUT"] = str(output)
    receipt = {"model": role["model"], "tool": tool, "prompt_sha": hashlib.sha256(prompt_path.read_bytes()).hexdigest()[:12]}
    started = time.monotonic()
    if run is subprocess.run:
        result = run_tracked(command, workdir, prompt, env, cfg["review_timeout_minutes"] * 60,
                             var(root) / "pids" / f"{subject}.pid")
    else:
        result = run(command, cwd=workdir, input=prompt, env=env, capture_output=True, text=True,
                     timeout=cfg["review_timeout_minutes"] * 60, check=False)
    _, extra = classify(result.returncode, result.stdout, result.stderr, role.get("output", "claude-json"))
    receipt.update(cost_usd=extra.get("cost_usd"), minutes=round((time.monotonic() - started) / 60, 2))
    try:
        data = json.loads(output.read_text()) if agent["form"] != "brief" or output.exists() else {}
        verdict = check_form(agent["form"], data, context)
    except (OSError, ValueError, CrewRefused) as error:
        record(root, name, event, subject, "refused", receipt, ok=False, note=str(error))
        raise CrewRefused(f"{name}: {error}") from error
    finally:
        output.unlink(missing_ok=True)
    record(root, name, event, subject, verdict, receipt)
    remember(root, name, data.get("memory_line"))
    return data, verdict


def load_files(root, entry):
    from common import load_unit
    try:
        return load_unit(entry["worktree"], entry["unit"], root)["files"]
    except (OSError, ValueError):
        return []


def latest(root, name, subject):
    found = [r for r in read_jsonl(var(root) / "crew" / f"{name}.jsonl") if r.get("subject") == subject and r.get("ok")]
    return found[-1] if found else None


def plan_hash(root):
    digest = hashlib.sha256()
    for name in ("plan/backlog.md", "plan/slice-matrix.json"):
        path = Path(root) / name
        digest.update(path.read_bytes() if path.exists() else b"-")
    return digest.hexdigest()[:16]


def before_cut(root, row, row_text, run=subprocess.run):
    """Sweeper Sid first; a done verdict closes the row only after code re-runs its evidence command."""
    from tick import mark_row
    data, verdict = run_agent(root, "sweeper-sid", "before_cut", row, {"row": row, "text": row_text}, run=run)
    if verdict == "done":
        check = subprocess.run(["bash", "-c", data["evidence_command"]], cwd=root, capture_output=True, text=True, timeout=600)
        if check.returncode == 0:
            mark_row(root, row, f"done (already done: {data['criterion']})")
            record(root, "sweeper-sid", "evidence_rerun", row, "confirmed", {})
            return {"row": row, "already_done": True, "criterion": data["criterion"]}
        record(root, "sweeper-sid", "evidence_rerun", row, "refuted", {}, ok=False,
               note=f"exit {check.returncode}: {check.stdout[-200:]}")
    _, coverage = run_agent(root, "plan-coverage-auditor", "before_cut", row,
                            {"row": row, "text": row_text, "plan_hash": plan_hash(root)}, run=run)
    record(root, "plan-coverage-auditor", "plan_hash", row, plan_hash(root), {})
    return {"row": row, "already_done": False, "coverage": coverage}


def cut_refusal(root, row):
    """Why a unit of this row may not be queued yet, or None."""
    if latest(root, "sweeper-sid", row) is None:
        return f"run `factory crew before-cut {row}` first (Sweeper Sid has not checked the row)"
    coverage = latest(root, "plan-coverage-auditor", row)
    stamp = [r for r in read_jsonl(var(root) / "crew" / "plan-coverage-auditor.jsonl")
             if r.get("subject") == row and r.get("event") == "plan_hash"]
    if coverage is None or not stamp:
        return f"run `factory crew before-cut {row}` first (no plan coverage audit)"
    if coverage["verdict"] == "dropped":
        return f"the plan coverage audit of {row} found a dropped deliverable; fix the plan, then before-cut again"
    if stamp[-1]["verdict"] != plan_hash(root):
        return f"the plan changed since {row} was audited; run `factory crew before-cut {row}` again"
    return None


def scorecard(root):
    """Cookies and slaps per agent, counted by code from the records and the escaped defects."""
    events = read_jsonl(var(root) / "log.jsonl")
    defects = {e["unit"].split("/")[-2] + "-U" + e["unit"].split("/")[-1].split(".")[0]
               for e in events if e.get("event") == "defect"}
    cards = {}
    for path in sorted((var(root) / "crew").glob("*.jsonl")):
        for r in read_jsonl(path):
            card = cards.setdefault(r["agent"], {"agent": r["agent"], "runs": 0, "cookies": 0, "slaps": 0, "verdicts": {},
                                                 "last": None, "triggers": []})
            if r["event"] == "evidence_rerun":
                card["cookies" if r["verdict"] == "confirmed" else "slaps"] += 1
                continue
            if r["event"] == "plan_hash":
                continue
            card["runs"] += 1
            card["last"] = r["at"]
            card["verdicts"][r["verdict"]] = card["verdicts"].get(r["verdict"], 0) + 1
            if r["event"] not in card["triggers"]:
                card["triggers"].append(r["event"])
            if not r["ok"] or (r["verdict"] == "PASS" and r["subject"] in defects):
                card["slaps"] += 1
            else:
                card["cookies"] += 1
    return list(cards.values())


def retro(root, report_path, run=subprocess.run):
    """The daily retro's crew part: the claim verifier on the daily report, then the Bookie's words."""
    text = Path(report_path).read_text()
    _, claims = run_agent(root, "claim-verifier", "daily_report", Path(report_path).name, {"text": text[:5000]}, run=run)
    cards = scorecard(root)
    data, _ = run_agent(root, "the-bookie", "daily_retro", now()[:10], {"scorecard": cards}, run=run)
    for card in cards:
        line = data["lines"].get(card["agent"], "")
        remember(root, card["agent"], f"scorecard cookies {card['cookies']}, slaps {card['slaps']}. {line}")
    return {"daily_report_claims": claims, "scorecard": cards, "most_expensive": data["most_expensive"]}


def main(argv=None, root=None):
    args = sys.argv[1:] if argv is None else argv
    root = Path(root or Path.cwd())
    try:
        if args[:1] == ["before-cut"]:
            from tick import backlog_text
            print(json.dumps(before_cut(root, args[1], backlog_text(root, args[1])), indent=1))
        elif args[:1] == ["retro"]:
            print(json.dumps(retro(root, args[1]), indent=1))
        elif args[:1] == ["research"]:
            from research_check import check_research
            path = Path(args[1])
            check_research(path.read_text())
            data, verdict = run_agent(root, "claim-verifier", "done_claim", args[1], {"text": path.read_text()[:6000]})
            if verdict == "match":
                model = config(root)["roles"]["reviewer"]["model"]
                path.write_text(path.read_text().rstrip("\n") + f"\n\nReviewed-by: {model} PASS\n")
            print(verdict)
            return 0 if verdict == "match" else 1
        elif args[:1] == ["handoff"]:
            text = Path(args[1]).read_text()
            _, verdict = run_agent(root, "claim-verifier", "handoff", args[1], {"text": text[:5000]})
            print(verdict)
            return 1 if verdict == "mismatch" else 0
        else:
            print(__doc__)
            return 2
    except (CrewRefused, IndexError, OSError, ValueError) as error:
        print(f"crew: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
