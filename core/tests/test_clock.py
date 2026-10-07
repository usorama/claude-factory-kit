"""The driver, the clock, ask cards, consistency, the staleness gate and the dry run."""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import asks
import consistency
import drive
import staleness_gate
import tick
from common import read_jsonl, read_queue, write_queue

CORE = Path(__file__).resolve().parents[1]


def queue_of(root, *states, worktree="w"):
    (root / "var/factory").mkdir(parents=True, exist_ok=True)
    write_queue(root, {"units": [{"unit": f".ai/units/R{i}/1.json", "worktree": worktree, "state": s,
                                  "attempts": 0, "log": []} for i, s in enumerate(states)]})


def runners_all(fn):
    return {step: fn for step in ("red", "build", "check", "review", "land", "watch")}


def states(root):
    return [u["state"] for u in read_queue(root)["units"]]


def test_up_to_n_lanes_run_at_the_same_moment_and_an_enqueue_during_a_tick_is_kept(tmp_path):
    queue_of(tmp_path, "red", "red", "red", "red", "red")
    running, peak, lock = [0], [0], threading.Lock()

    def slow(entry):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.3)
        with lock:
            running[0] -= 1
        return True, "built", {}

    worker = threading.Thread(target=drive.tick, args=(tmp_path, runners_all(slow), 4))
    worker.start()
    time.sleep(0.1)
    with drive.queue_lock(tmp_path):  # the orchestrator enqueues while the tick runs
        queue = read_queue(tmp_path)
        queue["units"].append({"unit": ".ai/units/N/1.json", "worktree": "w", "state": "cut", "attempts": 0, "log": []})
        write_queue(tmp_path, queue)
    worker.join()
    assert peak[0] == 4
    assert states(tmp_path) == ["built"] * 5 + ["cut"]
    ends = [e for e in read_jsonl(tmp_path / "var/factory/log.jsonl") if e["event"] == "end"]
    assert len(ends) == 5 and all("minutes" in e for e in ends)


def test_first_refusal_rebuilds_with_the_finding_second_refusal_stops_for_a_split(tmp_path):
    queue_of(tmp_path, "built")
    refuse = runners_all(lambda entry: (False, "tests/test_x.py::test_y still fails", {}))
    drive.tick(tmp_path, refuse)
    entry = read_queue(tmp_path)["units"][0]
    assert entry["state"] == "red" and entry["last_reject"] == "tests/test_x.py::test_y still fails"
    write_queue(tmp_path, {"units": [{**entry, "state": "built"}]})
    drive.tick(tmp_path, refuse)
    assert states(tmp_path) == ["needs_split"]


def test_a_failed_red_check_or_a_cut_finding_stops_the_unit_as_cut_refused(tmp_path):
    queue_of(tmp_path, "cut")
    drive.tick(tmp_path, runners_all(lambda e: (False, "test_a already passes", {})))
    assert states(tmp_path) == ["cut_refused"]

    def cut_finding(entry):
        entry["cut_finding"] = True
        return False, "CUT", {}
    queue_of(tmp_path, "checked")
    drive.tick(tmp_path, runners_all(cut_finding))
    assert states(tmp_path) == ["cut_refused"]


def test_a_review_with_no_form_is_retried_once_then_the_unit_stops(tmp_path):
    queue_of(tmp_path, "checked")

    def no_form(entry):
        raise drive.RetryOnce("no usable review form")
    drive.tick(tmp_path, runners_all(no_form))
    assert states(tmp_path) == ["checked"]
    drive.tick(tmp_path, runners_all(no_form))
    assert states(tmp_path) == ["errored"]


def test_a_retry_uses_no_attempt_and_can_send_the_unit_back_to_review(tmp_path):
    queue_of(tmp_path, "reviewed")

    def moved(entry):
        raise drive.Retry("changed since review", "checked")
    drive.tick(tmp_path, runners_all(moved))
    entry = read_queue(tmp_path)["units"][0]
    assert entry["state"] == "checked" and entry["attempts"] == 0


def test_a_stop_writes_one_card_for_the_orchestrator_and_set_closes_it_with_a_logged_reason(clock_repo):
    tmp_path = clock_repo
    queue_of(tmp_path, "cut")
    boom = runners_all(lambda e: (_ for _ in ()).throw(RuntimeError("crash")))
    assert tick.tick_once(tmp_path, boom)["cards_written"] == 1
    assert tick.tick_once(tmp_path, boom)["cards_written"] == 0
    card = asks.collect(tmp_path)[0]
    assert card["for"] == "orchestrator" and card["state"] == "errored"
    assert asks.notify_text(tmp_path) == ""  # a unit stop never reaches the human
    with pytest.raises(tick.Refused, match="a reason"):
        tick.set_state(tmp_path, ".ai/units/R0/1.json", "cut", "because", "x")
    tick.set_state(tmp_path, ".ai/units/R0/1.json", "cut", "machinery", "fixed PATH for cron")
    assert [c["answered"] for c in asks.collect(tmp_path)] == [True]
    hand = [e for e in read_jsonl(tmp_path / "var/factory/log.jsonl") if e["event"] == "hand"]
    assert hand[0]["reason"] == "machinery"
    asks.decide(tmp_path, "budget", "Spend on a bigger CI runner?", "No; measure first")
    assert asks.notify_text(tmp_path).startswith("1 decision(s) wait for you: Spend on a bigger CI runner?")


def test_consistency_finds_a_stale_clock_a_stale_card_and_a_wrong_position_time(tmp_path):
    queue_of(tmp_path, "red")
    (tmp_path / "var/factory/ticks.log").write_text(json.dumps({"at": "2026-10-07T00:00:00+00:00"}) + "\n")
    (tmp_path / "var/factory/asks").mkdir()
    (tmp_path / "var/factory/asks/R0-U1.md").write_text("# R0-U1 stopped\n\nFor: orchestrator\nKind: unit-stop\n")
    (tmp_path / "state.md").write_text("## Position\nUpdated 7 Oct, morning.\n")
    report = consistency.check(tmp_path, consistency.parse_time("2026-10-07T00:30:00+00:00"))
    codes = {f["code"] for f in report["findings"]}
    assert {"clock_stale", "stale_card", "row_not_building", "position_unreadable"} <= codes


def test_the_gate_refuses_stale_data_and_typed_numbers(tmp_path):
    (tmp_path / "src.jsonl").write_text("x")
    data = {"sections": {"metrics": {"as_of": "2000-01-01T00:00:00+00:00", "sources": ["src.jsonl"]}}}
    assert staleness_gate.data_findings(tmp_path, data) == [
        "data section 'metrics' is older than src.jsonl; run factory/metrics.py"]
    html = ('<section data-static data-title="W" data-asof="2000-01-01" data-sources="src.jsonl">'
            '<p>Seven units</p></section><section data-static data-title="N" data-asof="2999-01-01" '
            'data-sources="src.jsonl"><p>We landed 12 units</p></section>')
    found = staleness_gate.static_findings(tmp_path, html)
    assert len(found) == 2 and "older than src.jsonl" in found[0] and "typed number '12'" in found[1]


def test_the_shipped_dashboard_page_passes_its_own_static_gate():
    html = (CORE / "templates/dashboard/index.html").read_text()
    assert staleness_gate.PLACEHOLDER in html
    assert [f for f in staleness_gate.static_findings(CORE.parent, html) if "typed number" in f] == []


@pytest.mark.parametrize("args", [["--preset", "claude-only"], ["--preset", "codex-only"], ["--preset", "claude-codex"],
                                  ["--preset", "generic"], ["--landing", "pr_merge"], ["--landing", "auto"],
                                  ["--landing", "pr_only"]])
def test_the_dry_run_lands_both_units_end_to_end(tmp_path, args):
    result = subprocess.run([sys.executable, str(CORE / "sample/dry_run.py"), str(tmp_path / "run"), *args],
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert "DRY RUN PASSED" in result.stdout
    # it follows SETUP-CHECKLIST items 8 and 9: a separate factory clone, marked by init, with the marker required
    assert '"clone_marker_required": true' in result.stdout and '"clone_marker_present": true' in result.stdout
