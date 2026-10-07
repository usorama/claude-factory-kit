"""Run one role or crew command: fill its placeholders, give it the prompt on stdin, and read its
output. Shapes were copied from real runs (tests/fixtures/*-real*, *-unknown-model*).
classify() decides whose fault a failed run is: a usage limit pauses model steps (UsageLimit), a
pinned model that no longer answers stops the unit and asks the human (ModelGone, never a silent
fallback), any other model error is machinery (RetryOnce). None of them uses the unit's attempt.
"""
import json
import os
import re
from pathlib import Path

from drive import ModelGone, RetryOnce, UsageLimit

MODEL_GONE = re.compile(r"issue with the selected model|unrecognized_model|model is not supported|"
                        r"model[^.]{0,60}(not found|does not exist|not available)", re.I)

NO_NETWORK = json.dumps({"sandbox": {"enabled": True, "network": {"allowedDomains": []}}})
# Only the service's own limit answers: status 429, or the claude tool's limit phrases. Words like "quota" in a failed
# run's text may be about the unit's own subject and must not pause every model step.
LIMIT_WORDS = re.compile(r"API Error: 429|\busage limit reached\b|limit will reset at|Claude AI usage limit|"
                         r"\brate_limit_error\b", re.I)
TOKEN_FILE = Path(os.environ.get("FACTORY_CLAUDE_TOKEN_FILE", "~/.config/factory/claude-token")).expanduser()
FORM_NAME = ".factory-review.json"
RUN_TESTS = Path(__file__).resolve().parent / "run_tests.py"
RUN_TESTS_RULE = f"Bash(python3 {RUN_TESTS} *)"  # the only way a role runs tests (scrubbed and fenced)


def claude_usage(stdout):
    """Pick text, cost, tokens and denials from claude -p --output-format json; raw text when not JSON."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return stdout, {}
    usage = data.get("usage") or {}
    denials = data.get("permission_denials") or []
    extra = {"cost_usd": data.get("total_cost_usd"), "input_tokens": usage.get("input_tokens"),
             "output_tokens": usage.get("output_tokens"), "turns": data.get("num_turns"),
             "subtype": data.get("subtype"), "is_error": data.get("is_error"),
             "api_error_status": data.get("api_error_status"), "denials": len(denials) or None,
             "first_denial": json.dumps(denials[0])[:200] if denials else None}
    return str(data.get("result", "")), {k: v for k, v in extra.items() if v is not None}


def codex_usage(stdout):
    """Text and tokens from codex exec --json events; a turn.failed or error event marks an error."""
    text, extra = "", {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            text = event["item"].get("text", "")
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
            extra.update(input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))
        elif kind in ("turn.failed", "error"):
            extra.update(is_error=True, subtype="error")
            text = json.dumps(event.get("error") or event.get("message") or event)[:300]
    return text, {k: v for k, v in extra.items() if v is not None}


def classify(returncode, stdout, stderr, output="claude-json"):
    """Return (text, extra), or raise UsageLimit / RetryOnce when the run failed for a reason that is
    not the unit's."""
    text, extra = (claude_usage(stdout) if output == "claude-json" else
                   codex_usage(stdout) if output == "codex-jsonl" else (stdout, {}))
    failed = returncode or extra.get("is_error")
    if failed and (extra.get("api_error_status") == 404 or MODEL_GONE.search(f"{text} {stderr}")):
        raise ModelGone(f"{text or stderr}".strip()[:300])
    if extra.get("api_error_status") == 429 or (failed and LIMIT_WORDS.search(f"{text} {stderr}")):
        raise UsageLimit(f"{text or stderr}".strip()[:300])
    if failed or extra.get("subtype", "success") != "success":
        raise RetryOnce(f"model run failed (exit {returncode}, {extra.get('subtype', output)}): "
                        f"{(text or stderr).strip()[:300]}")
    return text, extra


def fill(text, values):
    """Replace {name} only for known names; JSON examples and other braces stay as written."""
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def role_command(role, values):
    """The role's command with placeholders filled; {tools} and {deny} expand into several arguments."""
    command = []
    for part in role["command"]:
        if part in ("{tools}", "{deny}"):
            command += [str(item) for item in role.get(part.strip("{}"), [])]
        else:
            command.append(fill(str(part), values))
    return command


ENV_KEEP = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "TMPDIR", "SHELL",
            "CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE")
ENV_KEEP_PREFIXES = ("FACTORY_", "ANTHROPIC_", "CLAUDE_CODE_", "OPENAI_")
# Files a role must never read: tokens and credentials of gh, git, cloud tools, containers, the factory and the
# agent tools themselves. Put on every claude command line; a project settings file does not apply in a new work
# folder (tests/fixtures/claude-read-deny-2.1.290.json shows a command-line Read(~/...) deny works there).
DENY_READ = ["Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(~/.config/gh/**)", "Read(~/.netrc)", "Read(~/.git-credentials)",
             "Read(~/.config/git/credentials)", "Read(~/.config/factory/**)", "Read(~/.factory-env.sh)", "Read(~/.kube/**)",
             "Read(~/.docker/config.json)", "Read(~/.config/gcloud/**)", "Read(~/.azure/**)", "Read(~/.npmrc)",
             "Read(~/.pypirc)", "Read(~/.claude/.credentials.json)", "Read(~/.codex/auth.json)", "Read(**/.env)",
             "Read(**/.env.*)"]


def claude_env(role):
    """The environment a role or crew process gets: an allow list, never the clock's whole environment (cloud keys,
    GitHub and package tokens stay out). The Claude token comes from its file and goes only to this process."""
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith(ENV_KEEP_PREFIXES)}
    env.update(FACTORY_ROLE=role, DISABLE_AUTOUPDATER="1")
    if TOKEN_FILE.is_file():
        env["CLAUDE_CODE_OAUTH_TOKEN"] = TOKEN_FILE.read_text().strip()
    return env


def with_read_denies(command):
    """Append the secret-file Read denies to a claude command (its --disallowedTools list is last)."""
    if not command or Path(command[0]).name != "claude":
        return command
    if "--disallowedTools" not in command:
        command = command + ["--disallowedTools"]
    return command + DENY_READ


def run_tracked(command, cwd, input, env, timeout, pidfile):
    """Run a role or crew process in its own process group and record its pid, so `tick.py hold` can end it."""
    import signal
    import subprocess
    pidfile = Path(pidfile)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    pidfile.write_text(str(process.pid))
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    finally:
        pidfile.unlink(missing_ok=True)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
