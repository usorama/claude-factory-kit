#!/usr/bin/env python3
"""PreToolUse hook for the Agent (sub-agent) tool: only code starts a factory role, always with its
pinned model. A session may not pass a model (it would override the agent file's pinned model) and may
not start the builder, the reviewer, the summarizer or a crew agent itself. Exit 2 blocks the call."""
import json
import sys
from pathlib import Path

CODE_ONLY = {"builder", "reviewer", "summarizer", "chief-of-staff", "sorter-sam", "sweeper-sid", "plan-coverage-auditor",
             "quill", "inspector-grumble", "lockjaw", "thomasina", "spec-conformance-auditor", "claim-verifier", "the-bookie"}

call = json.loads(sys.stdin.read() or "{}")
tool_input = call.get("tool_input") or {}
project = Path(call.get("cwd") or ".")
if not (project / "factory.toml").exists():
    sys.exit(0)  # not a factory project
agent = str(tool_input.get("subagent_type", "")).split(":")[-1]
if tool_input.get("model"):
    print("The factory pins every model in factory.toml; do not pass a model to a sub-agent.", file=sys.stderr)
    sys.exit(2)
if agent in CODE_ONLY:
    print(f"{agent} is started only by code on its trigger (factory/crew.toml, the clock). "
          "Ask code instead: factory crew <event>, or a queue entry.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
