"""Write var/factory/dashboard/data.json: every number the dashboard shows, from the records.

Each section carries as_of (when it was computed) and sources (the files it was computed from).
The staleness gate refuses to publish a section whose sources changed after its as_of.
Every number carries a plain explanation. The page never contains a typed number.
Usage: metrics.py
"""
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from asks import collect, folder
from common import ACTIVE, STOPPED, config, parse_time, review_independence, unit_row, label, load_unit, paused_until, read_jsonl, read_queue, var
from consistency import check
from daily_report import _first, days
from land import effective_landing
from tick import backlog

SOURCES = {
    "now": ["var/factory/queue.json", "var/factory/ticks.log"],
    "daily": ["var/factory/log.jsonl", "var/factory/spend.jsonl", "var/factory/ticks.log", "var/factory/asks", ".ai/lessons.jsonl"],
    "metrics": ["var/factory/log.jsonl", "var/factory/spend.jsonl", "var/factory/ticks.log", "var/factory/queue.json"],
    "decisions": ["var/factory/asks"],
    "lessons": [".ai/lessons.jsonl"],
    "consistency": ["var/factory/queue.json", "var/factory/ticks.log", "var/factory/asks", "state.md",
                    "plan/backlog.md", "var/factory/log.jsonl"],
}


def number(name, value, unit, explain):
    return {"name": name, "value": value, "unit": unit, "explain": explain}


def factory_numbers(root):
    events = read_jsonl(var(root) / "log.jsonl")
    ticks = read_jsonl(var(root) / "ticks.log")
    units = read_queue(root)["units"]
    checks = _first(events, "check")
    reviews = {u: e for u, e in _first(events, "review").items() if e.get("verdict")}
    hand = [e for e in events if e.get("event") == "hand"]
    review_errors = [e for e in events if e.get("event") == "end" and e.get("step") == "review"
                     and str(e.get("outcome", "")).startswith(("retry once", "error"))]
    landed = [e for e in events if e.get("to") == "landed"]
    costs = [e["cost_usd"] for e in read_jsonl(var(root) / "spend.jsonl") if isinstance(e.get("cost_usd"), (int, float))]
    steps = {}
    for event in events:
        if event.get("event") == "end" and isinstance(event.get("minutes"), (int, float)):
            steps.setdefault(event["step"], []).append(event["minutes"])
    idle = Counter(t["idle_reason"].split(";")[0] for t in ticks if t.get("idle_reason"))
    numbers = [
        number("Units landed", len(landed), "units", "Built, checked, reviewed and merged into main."),
        number("First-try green", f"{sum(e['ok'] for e in checks.values())} of {len(checks)}", "units",
               "Units whose first build passed the build check with no rebuild. Higher is better."),
        number("First review pass", f"{sum(e['verdict'] == 'PASS' for e in reviews.values())} of {len(reviews)}",
               "units", "Units whose first review verdict was PASS. Review errors are not verdicts."),
        number("Sent to split", sum(e.get("to") == "needs_split" for e in events), "units",
               "Units that failed twice. The chief of staff cuts them smaller."),
        number("Stopped now", sum(u["state"] in STOPPED for u in units), "units",
               "Units waiting for the chief of staff. Their cards are the chief of staff's, never the human's."),
        number("Hand corrections", len(hand), "corrections",
               "Times the chief of staff changed the queue by hand. Each one has a reason below. Goal: zero."),
        number("Review errors", len(review_errors), "reviews",
               "Reviews that ended with no usable form. The machinery failed, not the builder."),
        number("Idle ticks", sum(idle.values()), "ticks", "Clock ticks with nothing to move. Reasons below."),
        number("Escaped defects", sum(e.get("event") == "defect" for e in events), "defects",
               "Faults found on main in a unit that had landed (tick.py defect). Target: zero from day one."),
        number("Model cost recorded", round(sum(costs), 2), "US dollars",
               "Sum of total_cost_usd for every model run (builds, reviews and crew), from the spend ledger."),
    ]
    receipts = [{k: e.get(k) for k in ("at", "unit", "role", "tool", "model", "effort", "prompt", "prompt_sha",
                                        "independence", "cost_usd")}
                for e in events if e.get("event") == "end" and e.get("role")][-20:]
    enqueued = {e["unit"]: e["at"] for e in events if e.get("event") == "enqueue"}
    landed_at = {e["unit"]: e["at"] for e in landed}
    sizing = []
    for unit in units:
        if unit.get("estimate_minutes") and unit["unit"] in landed_at:
            wall = (parse_time(landed_at[unit["unit"]]) - parse_time(enqueued.get(unit["unit"], landed_at[unit["unit"]]))).total_seconds() / 60
            model = unit.get("model_minutes", 0)
            sizing.append({"unit": label(unit["unit"]), "row": unit_row(unit["unit"])[0], "estimate": unit["estimate_minutes"],
                           "model_minutes": model, "wall_minutes": round(wall), "ratio": round(model / unit["estimate_minutes"], 2)})
    rows = {}
    for item in sizing:
        row = rows.setdefault(item["row"], {"row": item["row"], "estimate": 0, "model_minutes": 0, "units": 0})
        row.update(estimate=row["estimate"] + item["estimate"], model_minutes=round(row["model_minutes"] + item["model_minutes"], 1),
                   units=row["units"] + 1)
    numbers.append(number("Estimate against actual", statistics.median([i["ratio"] for i in sizing]) if sizing else "no landed unit yet",
                          "times the estimate", "Median of model minutes divided by the estimate, over landed units. One is a "
                          "perfect estimate; above two the unit should have been split. The retro uses it to size better."))
    backlog_rows = backlog(root)
    numbers.append(number("Ready queue width", sum(u["state"] in ACTIVE for u in units) + sum(s == "todo" for s in backlog_rows.values()),
                          "units and rows", "Units the clock can move now plus backlog rows ready to cut. Below the number "
                          "of lanes, builders wait: the plan does not feed every lane."))
    import crew
    return {"numbers": numbers, "receipts": receipts[::-1], "crew": crew.scorecard(root), "sizing": sizing, "sizing_rows": list(rows.values()),
            "step_minutes_median": {s: round(statistics.median(v), 1) for s, v in sorted(steps.items())},
            "hand_corrections": [{k: e[k] for k in ("at", "unit", "reason", "note")} for e in hand],
            "idle_reasons": dict(idle)}


def now_section(root):
    def title(entry):
        try:
            return load_unit(entry["worktree"], entry["unit"], root).get("title", "")
        except (OSError, ValueError):
            return ""

    units = [{"unit": label(u["unit"]), "title": title(u), "state": u["state"] + (" (held)" if u.get("hold") else ""),
              "attempts": u["attempts"],
              "step": (u.get("running") or {}).get("step"),
              "since": (u.get("running") or {}).get("since") or (u["log"][-1]["at"] if u["log"] else u.get("enqueued_at")),
              "last_outcome": str(u["log"][-1]["outcome"]).splitlines()[0][:200] if u["log"] else ""}
             for u in read_queue(root)["units"] if u["state"] != "landed"]
    ticks = read_jsonl(var(root) / "ticks.log")
    return {"units": units, "last_tick": ticks[-1]["at"] if ticks else None,
            "last_idle_reason": ticks[-1].get("idle_reason") if ticks else None,
            "roles": [{"role": name, **{k: role.get(k, "") for k in ("tool", "model", "effort", "prompt", "form", "check")}}
                      for name, role in config(root)["roles"].items()],
            "review_independence": dict(zip(("kind", "text"), review_independence(config(root)))),
            "landing": dict(zip(("mode", "why"), effective_landing(root, config(root)))),
            "lanes": config(root)["lanes"], "paused_until": (paused_until(root) or "") and paused_until(root).isoformat(), "moving": sum(u["state"] in ACTIVE for u in units),
            "clock_stale_minutes": config(root)["clock_stale_minutes"]}


def build(root):
    root = Path(root)
    folder(root)  # create the cards folders before the stamp, so creating them is not a change
    stamp = datetime.now(timezone.utc).isoformat()
    content = {
        "now": now_section(root),
        "daily": {"days": days(root)},
        "metrics": factory_numbers(root),
        "decisions": {"cards": [c for c in collect(root, "human") if not c["answered"]]},
        "lessons": {"lessons": read_jsonl(root / ".ai/lessons.jsonl")},
        "consistency": check(root),
    }
    sections = {name: {"as_of": stamp, "sources": SOURCES[name], **body} for name, body in content.items()}
    data = {"generated_at": stamp, "sections": sections}
    out = var(root) / "dashboard"
    out.mkdir(exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, indent=1))
    return data


if __name__ == "__main__":
    result = build(Path.cwd())
    print(f"wrote var/factory/dashboard/data.json; {len(result['sections']['consistency']['findings'])} finding(s)")
    sys.exit(0)
