"""Move every queued unit one step per tick, up to N lanes at the same moment.

States: cut -> red -> built -> checked -> reviewed -> landed (or reviewed -> pr_open -> landed when
the landing mode leaves the merge to GitHub). Stops: cut_refused, needs_split, errored. parked is
ignored by the clock.
- Each step writes a start line and an end line to log.jsonl (minutes, verdict, cost).
- Each unit's entry is saved under the queue lock as soon as its step ends, so an enqueue or
  another lane's save is never lost.
- A held unit (tick.py hold) is never run; a hold set during a step voids that step's result.
- Landings (and PR watching) run one at a time, in queue order; other steps run in parallel.
- The unit's fault (a refused check, a REJECT): first time back to build, second time needs_split.
  Model time (build and review) over twice the unit's estimate also sends it to needs_split.
- Machinery's fault (model error, denied tool, gh error, usage limit, fetch failure) never uses an
  attempt: RetryOnce stops the unit after a second failure; Retry waits for the next tick, at most
  max_retries times in a row; UsageLimit pauses every model step until the limit resets.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from common import config, log, now, pause, queue_lock, read_queue, save_entry, stored, write_queue

TRANSITIONS = {
    "cut": ("red", "red"), "red": ("build", "built"), "built": ("check", "checked"),
    "checked": ("review", "reviewed"), "reviewed": ("land", "landed"), "pr_open": ("watch", "landed"),
}
MODEL_STEPS = ("build", "review")
SERIAL_STATES = ("reviewed", "pr_open")


class Retry(Exception):
    """Try this step again next tick without using an attempt; optionally move to another state.
    counts=False for waiting that is normal (a PR waiting for its required checks)."""

    def __init__(self, message, to_state=None, counts=True):
        super().__init__(message)
        self.to_state, self.counts = to_state, counts


class RetryOnce(Exception):
    """A machinery error (model error, no review form, gh error): retried once, then the unit stops."""


class ModelGone(Exception):
    """A pinned model stopped answering: stop the unit and ask the human to approve a re-probe. No fallback."""


class UsageLimit(Exception):
    """The model service refused for a usage or rate limit: pause all model steps, use no attempt."""


def clear_interrupted(root):
    """A step marked running while we hold the tick lock was cut off by a crash: log it, run it again."""
    with queue_lock(root):
        queue = read_queue(root)
        for entry in queue["units"]:
            running = entry.pop("running", None)
            if running:
                log(root, event="end", unit=entry["unit"], step=running["step"], ok=None,
                    outcome="interrupted: the step never finished; it runs again")
        write_queue(root, queue)


def run_step(root, entry, runners, cfg):
    step, next_state = TRANSITIONS[entry["state"]]
    from_state = entry["state"]
    entry["running"] = {"step": step, "since": now()}
    save_entry(root, entry)
    if entry.get("hold"):  # held after this tick read the queue: do not start the step
        entry.pop("running", None)
        save_entry(root, entry)
        return entry["state"]
    log(root, event="start", unit=entry["unit"], step=step, state=from_state, attempts=entry["attempts"])
    started, ok, extra = time.monotonic(), None, {}
    try:
        ok, outcome, extra = runners[step](entry)
    except UsageLimit as limit:
        outcome = f"paused until {pause(root, cfg['usage_pause_minutes']).isoformat()}: {limit}"
    except ModelGone as gone:
        entry["state"], outcome = "errored", f"pinned model stopped answering: {gone}"
        from asks import decide
        day = now()[:10]
        decide(root, f"roles-{day}", "A pinned model stopped answering. Approve a new roles file?",
               "Run `factory probe`, read factory.toml.proposed, then `factory roles accept`. The factory never "
               "switches models by itself.")
    except Retry as retry:
        entry["retries"] = entry.get("retries", 0) + retry.counts
        outcome = f"retry: {retry}"
        if entry["retries"] > cfg["max_retries"]:
            entry["state"], outcome = "errored", f"retried {entry['retries'] - 1} times: {retry}"
        else:
            entry["state"] = retry.to_state or entry["state"]
    except RetryOnce as error:
        retried = entry.setdefault("retried", [])
        if step in retried:
            entry["state"], outcome = "errored", f"error twice: {error}"
        else:
            retried.append(step)
            outcome = f"retry once: {error}"
    except Exception as error:  # any crash stops the unit with a card, never the clock
        entry["state"], outcome = "errored", f"error: {type(error).__name__}: {error}"
    extra = dict(extra or {})
    now_stored = stored(root, entry)
    if now_stored and now_stored.get("hold"):  # held during this step: the step's result does not count
        entry.update(hold=now_stored["hold"], state=from_state)
        ok, outcome = None, f"held while running: {now_stored['hold']['reason']}"
    if ok is True:
        entry["state"] = extra.pop("to_state", next_state)
        entry["retries"] = 0
    elif ok is False:
        if step == "red" or entry.get("cut_finding"):
            entry["state"] = "cut_refused"
        else:
            entry["attempts"] += 1
            entry["last_reject"] = outcome
            entry["state"] = "red" if entry["attempts"] == 1 else "needs_split"
    if step in MODEL_STEPS and isinstance(extra.get("minutes_model"), (int, float)):
        entry["model_minutes"] = round(entry.get("model_minutes", 0) + extra["minutes_model"], 2)
    budget = 2 * entry.get("estimate_minutes", 0)
    if budget and entry.get("model_minutes", 0) > budget and entry["state"] not in ("landed", "pr_open", "errored"):
        entry["state"] = "needs_split"
        outcome = f"over twice its estimate ({entry['model_minutes']} of {entry['estimate_minutes']} minutes): split it"
    entry.pop("running", None)
    entry["log"].append({"step": step, "outcome": str(outcome)[:4000], "at": now()})
    save_entry(root, entry)
    log(root, event="end", unit=entry["unit"], step=step, state=from_state, to=entry["state"], ok=ok,
        attempts=entry["attempts"], minutes=round((time.monotonic() - started) / 60, 2),
        outcome=str(outcome).splitlines()[0][:300] if outcome else "", **extra)
    return entry["state"]


def tick(root, runners, lanes=None, hold_models=None):
    """Run one step for every moving unit. hold_models (a reason) skips build and review steps.
    Returns {'steps': n, 'landed': n, 'stopped': n, 'held': n}."""
    cfg = config(root)
    lanes = lanes or cfg["lanes"]
    clear_interrupted(root)
    with queue_lock(root):
        entries = [e for e in read_queue(root)["units"] if e["state"] in TRANSITIONS and not e.get("hold")]
    held = [e for e in entries if hold_models and TRANSITIONS[e["state"]][0] in MODEL_STEPS]
    entries = [e for e in entries if e not in held]
    serial = [e for e in entries if e["state"] in SERIAL_STATES]
    others = [e for e in entries if e["state"] not in SERIAL_STATES]
    results = []

    def in_order():
        return [run_step(root, entry, runners, cfg) for entry in serial]

    with ThreadPoolExecutor(max_workers=max(1, lanes)) as pool:
        jobs = [pool.submit(run_step, root, entry, runners, cfg) for entry in others]
        if serial:
            jobs.append(pool.submit(in_order))
        for job in jobs:
            result = job.result()
            results.extend(result if isinstance(result, list) else [result])
    return {"steps": len(results), "landed": results.count("landed"), "held": len(held),
            "stopped": sum(state in ("cut_refused", "needs_split", "errored") for state in results)}
