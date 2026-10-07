#!/usr/bin/env python3
"""Deterministic stand-in for claude -p and codex exec, for the dry run and the tests.
Answers in the shapes of real runs (core/tests/fixtures/*-real*, *-unknown-model*). Only models in
$FAKE_MODELS answer; any other model gets the tool's real unknown-model answer (exit 1).
Role from $FACTORY_ROLE: builder (copies $FAKE_SOLUTIONS), reviewer (runs tests, writes the review form,
leaves a sabotage edit for the factory to undo), crew:<name> (writes that agent's form), none (a probe)."""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

tool, args = sys.argv[1], sys.argv[2:]
flag = "--model" if tool == "claude" else "-m"
model = args[args.index(flag) + 1] if flag in args else ""
prompt = sys.stdin.read()
known = [m for m in os.environ.get("FAKE_MODELS", "").split(",") if m]


def answer(text, ok=True):
    if tool == "claude":
        print(json.dumps({"type": "result", "subtype": "success", "is_error": not ok, "result": text, "num_turns": 1,
                          "total_cost_usd": 0.0, "api_error_status": None if ok else 404,
                          "usage": {"input_tokens": 0, "output_tokens": 0}, "permission_denials": []}))
    else:
        if ok:
            print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}))
            print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}}))
        else:
            print(json.dumps({"type": "turn.failed", "error": {"message": text}}))
    sys.exit(0 if ok else 1)


if model not in known:
    if tool == "claude":
        print(f"[claude-code:unrecognized_model] {json.dumps({'model': model})}", file=sys.stderr)
        answer(f"There's an issue with the selected model ({model}). It may not exist or you may not have access to it.", False)
    answer(f"The '{model}' model is not supported when using Codex with a ChatGPT account.", False)

role = os.environ.get("FACTORY_ROLE", "")
unit_match = re.search(r'([^\s"\']*\.ai/units/[^\s"\']+?\.json)', prompt)
unit = json.loads(Path(unit_match.group(1)).read_text()) if unit_match else {}
code = [f for f in unit.get("files", []) if not Path(f).name.startswith("test_")]
if role == "builder":
    for name in code:
        source = Path(os.environ["FAKE_SOLUTIONS"]) / name
        if source.exists():
            Path(name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, name)
    answer("Named tests passed. Whole suite passed. Files changed: " + " ".join(code))
if role == "reviewer":
    named = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *unit["tests"]], capture_output=True)
    with open(code[0], "a") as stream:
        stream.write("\n# sabotage left behind by the fake reviewer\n")
    Path(os.environ["FACTORY_REVIEW_FORM"]).write_text(json.dumps({
        "verdict": "PASS" if named.returncode == 0 else "REJECT", "high": [], "suite_result_seen": True,
        "notes": [f"fake reviewer {model}: named tests exit {named.returncode}"]}))
    answer("reviewed")
if role.startswith("crew:"):
    name, out = role[5:], Path(os.environ["FACTORY_CREW_OUTPUT"])
    row = (re.search(r'"row": "([^"]+)"', prompt) or re.search(r"(W\d+)", prompt) or [None, "W1"])[1]
    forms = {
        "sorter-sam": {"row": row, "still_real": True, "evidence": "textkit/ has no words module", "size": "S",
                       "risk_class": "none", "files": ["textkit/words.py"], "done_property": "words are counted", "founder_gated": False},
        "sweeper-sid": {"row": row, "verdict": "not_done", "criterion": "NONE", "evidence": "no module", "evidence_command": ""},
        "plan-coverage-auditor": {"row": row, "items": [{"item": "count words", "source": "plan/backlog.md:5", "unit": "U1", "status": "COVERED"}],
                                  "dropped": [], "orphaned": []},
        "spec-conformance-auditor": {"row": row, "findings": [{"requirement": "count and title-case", "source": "plan/backlog.md:5",
                                                               "code": "textkit/words.py:1", "classification": "MET", "evidence": "tests", "fix": ""}]},
        "claim-verifier": {"source": "dry run", "claims": [{"claim": "units landed", "command": "git log", "actual": "landed", "verdict": "MATCH", "rewrite": ""}]},
        "the-bookie": {"lines": {"inspector-grumble": "both reviews held"}, "most_expensive": "none today"},
        "lockjaw": {"verdict": "PASS", "high": [], "notes": [], "suite_result_seen": True},
        "thomasina": {"verdict": "PASS", "high": [], "notes": [], "suite_result_seen": True},
    }
    if name == "quill":
        brief = Path(re.search(r"Write the one file you may write: (\S+?),? with", prompt).group(1))
        test = unit["tests"][0]
        brief.write_text("# Brief by Quill\n\n" + "".join(f"## {n}. Part {n}\n- See the unit file.\n\n" for n in (1, 2, 3, 4, 6, 7, 8))
                         + f"## 5. How to prove it\n- Named test: {test}\n- Named sabotage: remove the refusal; that test goes red.\n")
        forms["quill"] = {"brief": str(brief), "named_test": test}
    out.write_text(json.dumps({**forms[name], "memory_line": f"{name} saw nothing new"}))
    answer("written")
answer("ok")
