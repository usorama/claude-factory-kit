"""Fallback candidates must terminate before use, and only passed choices unblock work."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_matrix import compute_path_schedule, load_json, validate


class ConditionalTests(unittest.TestCase):
    def setUp(self):
        self.matrix = load_json(ROOT / "examples/conditional-store.json")

    def test_runs_if_and_blocked_by_conflict_rejected(self):
        self.assertEqual(validate(self.matrix), [])
        self.matrix["slices"][1]["blocked_by"] = ["S1"]
        # No other rule should substitute for this specific conflict check.
        self.assertEqual(validate(self.matrix), [
            "R10: S2: blocked_by and runs_if.failed overlap: S1"
        ])

    def test_conditional_slice_not_counted_as_passed_blocker(self):
        waves, states = compute_path_schedule(self.matrix["slices"])
        self.assertNotIn("S2", waves)
        self.assertEqual(states["S2"], "skipped")
        consumer = self.matrix["slices"][2]
        consumer.pop("blocked_by_any")
        consumer["blocked_by"] = ["S2"]
        self.assertTrue(any(error.startswith("R10:") for error in validate(self.matrix)))
        waves, states = compute_path_schedule(self.matrix["slices"])
        self.assertNotIn("S3", waves)
        self.assertEqual(states["S3"], "blocked")
        # Adding an OR field cannot cancel a mandatory AND blocker.
        consumer["blocked_by_any"] = [["S1"], ["S2"]]
        self.assertTrue(any(error.startswith("R10:") for error in validate(self.matrix)))

    def test_blocked_by_any_waves(self):
        self.assertEqual(validate(self.matrix), [])
        self.assertEqual(compute_path_schedule(self.matrix["slices"])[0], {"S1": 0, "S3": 1})
        worst, states = compute_path_schedule(self.matrix["slices"], worst=True)
        self.assertEqual(worst, {"S1": 0, "S2": 1, "S3": 2})
        self.assertEqual(states, {"S1": "failed", "S2": "passed", "S3": "passed"})
        # Each group is AND. Groups are OR. Mandatory blockers still apply.
        rows = self.matrix["slices"]
        rows[1].pop("runs_if")
        rows[1]["blocked_by"] = ["S1"]
        rows[2]["blocked_by_any"] = [["S1"], ["S1", "S2"]]
        self.assertEqual(compute_path_schedule(rows)[0]["S3"], 1)
        self.assertEqual(compute_path_schedule(rows, worst=True)[0]["S3"], 2)
        rows[2]["blocked_by"] = ["S2"]
        self.assertEqual(compute_path_schedule(rows)[0]["S3"], 2)
        rows.reverse()
        self.assertEqual(compute_path_schedule(rows, worst=True)[0]["S3"], 2)

    def test_success_and_worst_path_reported(self):
        path = ROOT / "examples/conditional-store.json"
        for script in ("validate_matrix.py", "render_matrix.py"):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / script), str(path)],
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("success path: first working at wave 1, complete at wave 1", result.stdout)
                self.assertIn("worst path: first working at wave 2, complete at wave 2", result.stdout)
                if script == "render_matrix.py":
                    self.assertIn("Conditional: all failed or not selected: S1", result.stdout)
                    self.assertIn("S1 (failed)", result.stdout)
                    self.assertIn("S2: skipped", result.stdout)

    def test_unknown_references_and_mixed_cycles_rejected(self):
        for field, value in (("runs_if", {"failed": ["UNKNOWN"]}),
                             ("blocked_by_any", [["UNKNOWN"]])):
            matrix = copy.deepcopy(self.matrix)
            matrix["slices"][1][field] = value
            self.assertTrue(any(error.startswith("R10:") and "UNKNOWN" in error for error in validate(matrix)))
        for field, value in (("blocked_by", ["S3"]),
                             ("runs_if", {"failed": ["S2"]}),
                             ("blocked_by_any", [["S2"]])):
            matrix = copy.deepcopy(self.matrix)
            matrix["slices"][0][field] = value
            self.assertTrue(any(error.startswith("R4:") for error in validate(matrix)))
        self.matrix["slices"][1]["runs_if"] = {"failed": ["S2"]}
        self.assertTrue(any(error.startswith("R4:") for error in validate(self.matrix)))

    def test_malformed_conditional_fields_rejected(self):
        fields = {
            "runs_if": [None, [], True, {}, {"failed": []}, {"failed": "S1"},
                        {"failed": ["S1", "S1"]}, {"failed": [None]},
                        {"failed": ["S1"], "extra": True}],
            "blocked_by_any": [None, True, "S1", [], [[]], ["S1"], [[None]],
                               [["S1", "S1"]], [["S1"], ["S1"]]],
        }
        for field, values in fields.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    matrix = copy.deepcopy(self.matrix)
                    matrix["slices"][1][field] = value
                    rules = {error.split(":")[0] for error in validate(matrix)}
                    self.assertTrue({"R8", "R10"}.issubset(rules))

    def test_alternatives_must_be_possible_on_success_path(self):
        self.matrix["slices"][2]["blocked_by_any"] = [["S2"]]
        self.assertEqual(validate(self.matrix), ["R10: S3: no passing alternative on the success path"])
        self.matrix["slices"][1]["blocked_by_any"] = [["S1"]]
        self.assertTrue(any("requires a runs_if.failed slice to pass" in error for error in validate(self.matrix)))

    def test_all_failed_conditions_wait_and_fallback_chains(self):
        rows = self.matrix["slices"]
        third = copy.deepcopy(rows[1])
        third.update(id="S4", runs_if={"failed": ["S1", "S2"]})
        rows.append(third)
        rows[2]["blocked_by_any"].append(["S4"])
        self.assertEqual(validate(self.matrix), [])
        waves, states = compute_path_schedule(rows, worst=True)
        self.assertEqual(waves, {"S1": 0, "S2": 1, "S4": 2, "S3": 3})
        self.assertEqual(states["S2"], "failed")
        self.assertEqual(states["S4"], "passed")

    def test_failed_candidate_cannot_unblock_required_work(self):
        rows = self.matrix["slices"]
        rows[2].pop("blocked_by_any")
        rows[2]["blocked_by"] = ["S1"]
        waves, states = compute_path_schedule(rows, worst=True)
        self.assertNotIn("S3", waves)
        self.assertEqual(states["S3"], "blocked")
        from validate_matrix import outcome_completion_report
        report = "\n".join(outcome_completion_report(self.matrix))
        self.assertIn("worst path: first working at unavailable (S3 blocked), complete at unavailable (blocked slice)", report)

    def test_stored_wave_uses_worst_path(self):
        for row, wave in zip(self.matrix["slices"], (0, 1, 2)):
            row["wave"] = wave
        self.assertEqual(validate(self.matrix), [])
        self.matrix["slices"][2]["wave"] = 1
        self.assertTrue(any(error.startswith("R6:") for error in validate(self.matrix)))
        self.matrix["slices"][2]["blocked_by"] = ["S1"]
        self.assertIn("R6: S3: stored wave has no computable worst-path wave", validate(self.matrix))

    def test_failed_or_skipped_first_proof_is_unavailable(self):
        from validate_matrix import outcome_completion_report
        self.matrix["source"]["outcomes"][0]["first_proof"] = "S2"
        report = "\n".join(outcome_completion_report(self.matrix))
        self.assertIn("success path: first working at unavailable (S2 skipped)", report)
        self.matrix["source"]["outcomes"][0]["first_proof"] = "S1"
        report = "\n".join(outcome_completion_report(self.matrix))
        self.assertIn("worst path: first working at unavailable (S1 failed)", report)

    def test_invalid_condition_cli_has_no_grid(self):
        self.matrix["slices"][1]["blocked_by"] = ["S1"]
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            path = Path(folder) / "conflict.json"
            path.write_text(json.dumps(self.matrix))
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/render_matrix.py"), str(path)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("R10:", result.stderr)


if __name__ == "__main__":
    unittest.main()
