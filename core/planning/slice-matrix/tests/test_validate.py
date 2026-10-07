"""Rule controls, malformed inputs, graph checks, and real CLI/render tests."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_matrix import (  # noqa: E402
    SCHEMA_PATH, audit_schema, compute_waves, load_json, validate,
)
from render_matrix import render  # noqa: E402


FIXTURES = {
    "R1": "bad-r1-hours.json", "R2": "bad-r2-engine.json",
    "R3": "bad-r3-builder.json", "R4": "bad-cycle.json",
    "R5": "bad-r5-coverage.json", "R6": "bad-r6-wave.json",
    "R7": "bad-r7-enabling.json", "R8": "bad-r8-schema.json",
}


def rule_ids(errors):
    return {error.split(":", 1)[0] for error in errors}


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.toy = load_json(ROOT / "examples/toy.json")

    def cli(self, script, path):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / script), str(path)],
            cwd=ROOT, text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def assert_rule(self, matrix, rule):
        self.assertIn(rule, rule_ids(validate(matrix)))

    def test_every_rule_has_passing_and_failing_fixture(self):
        for rule, filename in FIXTURES.items():
            with self.subTest(rule=rule):
                self.assertEqual(validate(self.toy), [], f"positive control for {rule}")
                bad = load_json(ROOT / "examples" / filename)
                self.assert_rule(bad, rule)
                result = self.cli("validate_matrix.py", ROOT / "examples" / filename)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(rule + ":", result.stdout)

    def test_bad_cycle(self):
        """Named sabotage target: fails when the R4 cycle call is commented out."""
        bad = load_json(ROOT / "examples/bad-cycle.json")
        self.assertEqual(rule_ids(validate(bad)), {"R4"})
        result = self.cli("validate_matrix.py", ROOT / "examples/bad-cycle.json")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_optional_decision_and_scope_fields(self):
        matrix = copy.deepcopy(self.toy)
        matrix["slices"][0]["blocked_by_decisions"] = ["D3"]
        matrix["slices"][0]["scope"] = "product-setting"
        self.assertEqual(validate(matrix), [])
        matrix["slices"][0]["scope"] = "somewhere-else"
        self.assert_rule(matrix, "R8")

    def test_r1_required_fields(self):
        for field in ("id", "title", "behavior", "layers_touched", "acceptance", "blocked_by", "size", "est_hours"):
            with self.subTest(field=field):
                matrix = copy.deepcopy(self.toy)
                del matrix["slices"][0][field]
                self.assert_rule(matrix, "R1")

    def test_r1_invalid_values(self):
        changes = [("id", ""), ("title", "  "), ("behavior", None),
                   ("layers_touched", []), ("layers_touched", ["storage", "storage"]),
                   ("acceptance", []), ("acceptance", [{"check": "Works", "type": "yes_no"}]),
                   ("acceptance", [{"check": "Works", "type": "score", "command": "test"}]),
                   ("acceptance", [{"check": "Works", "type": "yes_no", "observable": " "}]),
                   ("blocked_by", "S2"), ("size", "XL"), ("est_hours", 8.1),
                   ("est_hours", True), ("est_hours", 0), ("est_hours", -1)]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                matrix = copy.deepcopy(self.toy)
                matrix["slices"][0][field] = value
                self.assert_rule(matrix, "R1")

    def test_r1_eight_hours_and_command_check_pass(self):
        row = self.toy["slices"][0]
        row["est_hours"] = 8
        row["acceptance"] = [{"check": "Photo test exits 0", "type": "yes_no", "command": "python3 -m unittest test_photo"}]
        self.assertEqual(validate(self.toy), [])

    def test_r2_zero_and_one_participant(self):
        for count in (0, 1):
            with self.subTest(count=count):
                matrix = copy.deepcopy(self.toy)
                for row in matrix["slices"][count:]:
                    row["engines"] = {}
                self.assert_rule(matrix, "R2")
        for row in self.toy["slices"][2:]:
            row["engines"] = {}
        self.assertEqual(validate(self.toy), [])

    def test_r3_zero_and_multiple_builders(self):
        for modes in (("uses", "uses"), ("builds", "builds")):
            with self.subTest(modes=modes):
                matrix = copy.deepcopy(self.toy)
                for row, mode in zip(matrix["slices"], modes):
                    row["engines"]["E1"] = mode
                self.assert_rule(matrix, "R3")

    def test_r3_direct_dependency_required(self):
        self.toy["slices"][4]["blocked_by"] = ["S4"]
        self.assert_rule(self.toy, "R3")

    def test_r3_enabling_builder_rejected(self):
        self.toy["slices"][0].update(kind="enabling", reason="Prepare storage", layers_touched=["storage"])
        self.assert_rule(self.toy, "R3")

    def test_existing_engine_one_unblocked_user_and_example_cli(self):
        path = ROOT / "examples/existing-engine.json"
        matrix = load_json(path)
        self.assertEqual(validate(matrix), [])
        self.assertEqual(len(matrix["slices"]), 1)
        self.assertEqual(matrix["slices"][0]["blocked_by"], [])
        result = self.cli("validate_matrix.py", path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.cli("render_matrix.py", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| uses |", result.stdout)
        self.assertIn("- Wave 0: S1", result.stdout)

    def test_existing_engine_requires_users_and_forbids_builders(self):
        for modes, expected in (([None], {"R2", "R3"}),
                                (["builds"], {"R2", "R3"}),
                                (["builds", "uses"], {"R3"}),
                                (["uses", "uses"], set())):
            with self.subTest(modes=modes):
                matrix = load_json(ROOT / "examples/existing-engine.json")
                row = matrix["slices"][0]
                matrix["slices"] = []
                for index, mode in enumerate(modes):
                    item = copy.deepcopy(row)
                    item.update(id=f"S{index + 1}", engines={"E1": mode} if mode else {})
                    matrix["slices"].append(item)
                self.assertEqual(rule_ids(validate(matrix)), expected)

    def test_existing_flag_is_optional_boolean_and_false_keeps_new_engine_rules(self):
        self.toy["engines"][0]["existing"] = False
        self.assertEqual(validate(self.toy), [])
        for value in ("true", 1, 0, None, [], {}):
            with self.subTest(value=value):
                self.toy["engines"][0]["existing"] = value
                self.assert_rule(self.toy, "R8")
        for existing in (False, None):
            matrix = load_json(ROOT / "examples/existing-engine.json")
            if existing is None:
                del matrix["engines"][0]["existing"]
            else:
                matrix["engines"][0]["existing"] = existing
            self.assertEqual(rule_ids(validate(matrix)), {"R2", "R3"})

    def test_existing_and_new_engines_keep_separate_rules(self):
        self.toy["engines"].append({"id": "E2", "title": "Existing profile", "existing": True})
        self.toy["slices"][0]["engines"]["E2"] = "uses"
        self.assertEqual(validate(self.toy), [])
        self.toy["slices"][1]["blocked_by"] = []
        self.assert_rule(self.toy, "R3")  # E1 still needs its builder dependency.

    def stop_file(self):
        return {"stop": True, "reason": "The acceptance target is missing.",
                "questions": ["Which observable result counts as success?"],
                "rule": "vague_acceptance"}

    def test_valid_stop_file_exits_three_with_reason_and_no_grid(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "stop.json"
            for rule in ("vague_acceptance", "contradictory_order", "missing_source"):
                with self.subTest(rule=rule):
                    stop = self.stop_file()
                    stop["rule"] = rule
                    self.assertEqual(validate(stop), [])
                    path.write_text(json.dumps(stop))
                    result = self.cli("validate_matrix.py", path)
                    self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                    self.assertEqual(result.stdout, f"STOP: {stop['reason']}\n")
                    result = self.cli("render_matrix.py", path)
                    self.assertEqual(result.returncode, 3, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(stop["reason"], result.stderr)

    def test_stop_without_questions_rejected(self):
        """Sabotage target: accepting an empty questions list must fail this test."""
        stop = self.stop_file()
        stop["questions"] = []
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "stop.json"
            path.write_text(json.dumps(stop))
            result = self.cli("validate_matrix.py", path)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("R8:", result.stdout)
        self.assert_rule(stop, "R8")

    def test_malformed_stop_file_rejected_by_schema_and_cli(self):
        malformed = []
        for field in self.stop_file():
            stop = self.stop_file()
            del stop[field]
            malformed.append(stop)
        for field, value in (("stop", False), ("stop", 1), ("stop", "true"),
                             ("reason", " "), ("reason", None),
                             ("questions", "Which result?"), ("questions", [""]),
                             ("questions", [" "]), ("questions", [None]),
                             ("questions", ["Valid question?", 1]),
                             ("rule", "unknown"), ("rule", None),
                             ("extra", "text"), ("slices", []), ("engines", [])):
            stop = self.stop_file()
            stop[field] = value
            malformed.append(stop)
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "stop.json"
            for stop in malformed:
                with self.subTest(stop=stop):
                    self.assert_rule(stop, "R8")
                    path.write_text(json.dumps(stop))
                    result = self.cli("validate_matrix.py", path)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_r4_unknown_reference_and_self_cycle(self):
        for blocker in ("MISSING", "S1"):
            with self.subTest(blocker=blocker):
                matrix = copy.deepcopy(self.toy)
                matrix["slices"][0]["blocked_by"] = [blocker]
                self.assert_rule(matrix, "R4")

    def test_r4_disconnected_cycle_is_detected(self):
        self.toy["slices"][2]["blocked_by"].append("S5")
        self.toy["slices"][4]["blocked_by"].append("S3")
        self.assert_rule(self.toy, "R4")

    def test_r5_all_requirements_and_unknown_coverage(self):
        self.toy["source"]["requirements"] += ["REQ6", "REQ7"]
        self.toy["slices"][0]["covers"].append("TYPO")
        errors = validate(self.toy)
        for identifier in ("REQ6", "REQ7", "TYPO"):
            self.assertTrue(any(error.startswith("R5:") and identifier in error for error in errors))

    def test_outcomes_required(self):
        schema = load_json(SCHEMA_PATH)
        from validate_matrix import schema_errors
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "missing-outcomes.json"
            for missing in (True, False):
                matrix = copy.deepcopy(self.toy)
                if missing:
                    del matrix["source"]["outcomes"]
                else:
                    matrix["source"]["outcomes"] = []
                with self.subTest(missing=missing):
                    self.assertTrue(schema_errors(matrix, schema, schema))
                    self.assert_rule(matrix, "R9")
                    path.write_text(json.dumps(matrix))
                    result = self.cli("validate_matrix.py", path)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("R9:", result.stdout)

    def test_orphan_requirement_rejected(self):
        """Named sabotage target: disabling only the orphan check must fail."""
        self.assertEqual(validate(self.toy), [])
        # These requirements remain covered by rows, so only R9 can catch this.
        self.toy["source"]["outcomes"][1]["requirements"] = ["REQ4"]
        for row in (self.toy["slices"][2], self.toy["slices"][4]):
            row["covers"].append("REQ4")
        expected = "R9: requirements that lead to no outcome: REQ3, REQ5"
        self.assertEqual(validate(self.toy), [expected])
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "orphan.json"
            path.write_text(json.dumps(self.toy))
            result = self.cli("validate_matrix.py", path)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
            result = self.cli("render_matrix.py", path)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn(expected, result.stderr)

    def test_unknown_outcome_requirement_rejected(self):
        self.toy["source"]["outcomes"][0]["requirements"].append("UNKNOWN")
        self.assertEqual(validate(self.toy), ["R9: O1: unknown requirement UNKNOWN"])
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "unknown.json"
            path.write_text(json.dumps(self.toy))
            result = self.cli("validate_matrix.py", path)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("R9: O1: unknown requirement UNKNOWN", result.stdout)

    def test_outcome_ids_unique_and_requirements_nonempty(self):
        for change in ("duplicate", "empty"):
            matrix = copy.deepcopy(self.toy)
            if change == "duplicate":
                matrix["source"]["outcomes"][1]["id"] = "O1"
                self.assertIn("R9: duplicate outcome ID O1", validate(matrix))
            else:
                matrix["source"]["outcomes"].append({"id": "O3", "text": "No work", "requirements": []})
                self.assert_rule(matrix, "R8")
                self.assertIn("R9: O3: outcome needs at least one requirement ID", validate(matrix))

    def test_malformed_outcomes_do_not_crash(self):
        for value in (None, True, 4, "text", {}, [None], [[]]):
            with self.subTest(outcomes=value):
                matrix = copy.deepcopy(self.toy)
                matrix["source"]["outcomes"] = value
                self.assert_rule(matrix, "R8")
                self.assert_rule(matrix, "R9")
        for field in ("id", "text", "requirements", "first_proof"):
            for value in (None, True, 4, "", " ", [], {}, [None]):
                with self.subTest(field=field, value=value):
                    matrix = copy.deepcopy(self.toy)
                    matrix["source"]["outcomes"][0][field] = value
                    self.assert_rule(matrix, "R8")

    def test_slice_outcomes_required(self):
        from validate_matrix import schema_errors
        schema = load_json(SCHEMA_PATH)
        for value in (None, [], "O1", {}, [None], ["O1", 1]):
            with self.subTest(value=value):
                matrix = copy.deepcopy(self.toy)
                matrix["slices"][0]["outcomes"] = value
                self.assertTrue(schema_errors(matrix, schema, schema))
                self.assert_rule(matrix, "R9")
        del self.toy["slices"][0]["outcomes"]
        self.assertTrue(schema_errors(self.toy, schema, schema))
        self.assert_rule(self.toy, "R9")

    def test_slice_unknown_outcome_rejected(self):
        self.toy["slices"][1]["outcomes"].append("UNKNOWN")
        self.assertEqual(validate(self.toy), ["R9: S2: unknown outcome UNKNOWN"])

    def test_slice_outcome_must_share_requirement(self):
        """Sabotage target: only the shared-requirement check rejects this link."""
        self.assertEqual(validate(self.toy), [])
        # O1 remains a valid link. O2 exists, but S2 covers none of its work.
        self.toy["slices"][1]["outcomes"].append("O2")
        expected = "R9: S2: covers must share a requirement with outcome O2"
        self.assertEqual(validate(self.toy), [expected])
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "unrelated-outcome.json"
            path.write_text(json.dumps(self.toy))
            for script in ("validate_matrix.py", "render_matrix.py"):
                result = self.cli(script, path)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout + result.stderr)
                if script == "render_matrix.py":
                    self.assertEqual(result.stdout, "")
        self.toy["slices"][1]["covers"].append("REQ3")
        self.assertEqual(validate(self.toy), [])

    def test_first_proof_required_and_must_exist(self):
        for value in (None, [], {}, 1, "", "UNKNOWN"):
            with self.subTest(value=value):
                matrix = copy.deepcopy(self.toy)
                matrix["source"]["outcomes"][0]["first_proof"] = value
                self.assert_rule(matrix, "R9")
        del self.toy["source"]["outcomes"][0]["first_proof"]
        self.assert_rule(self.toy, "R8")
        self.assert_rule(self.toy, "R9")

    def test_first_proof_must_name_outcome(self):
        self.assertEqual(validate(self.toy), [])
        # The proof shares O1's requirement, but does not declare O1.
        self.toy["slices"][2]["covers"].append("REQ1")
        self.toy["source"]["outcomes"][0]["first_proof"] = "S3"
        expected = "R9: O1: first_proof slice S3 must name outcome O1"
        self.assertEqual(validate(self.toy), [expected])
        self.toy["slices"][2]["outcomes"].append("O1")
        self.assertEqual(validate(self.toy), [])

    def test_first_working_wave_reported(self):
        # A shared requirement does not count towards O1 completion unless
        # explicitly named. First working uses first_proof, not the earliest row.
        self.toy["slices"][3]["covers"].append("REQ1")
        self.toy["source"]["outcomes"].append(
            {"id": "O3", "text": "Profile visible in gallery", "requirements": ["REQ1"],
             "first_proof": "S4"})
        for row in (self.toy["slices"][0], self.toy["slices"][3]):
            row["outcomes"].append("O3")
        self.toy["slices"].reverse()
        self.assertEqual(validate(self.toy), [])
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "completion.json"
            path.write_text(json.dumps(self.toy))
            for script in ("validate_matrix.py", "render_matrix.py"):
                result = self.cli(script, path)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for outcome, first, complete in zip(self.toy["source"]["outcomes"], (0, 1, 2), (1, 3, 2)):
                    self.assertIn(f"{outcome['id']}: {outcome['text']}: first working at wave {first}, complete at wave {complete}",
                                  result.stdout)
                self.assertIn("Median first-working wave across outcomes: 1\n", result.stdout)
                self.assertIn("Waves start at 0; final wave is 3", result.stdout)
                result = self.cli(script, ROOT / "examples/existing-engine.json")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("first working at wave 0, complete at wave 0", result.stdout)
                self.assertIn("Median first-working wave across outcomes: 0\n", result.stdout)
                result = self.cli(script, ROOT / "examples/toy.json")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Median first-working wave across outcomes: 0.5\n", result.stdout)

    def test_r6_longest_path_not_shortest_or_row_order(self):
        expected = {"S1": 0, "S2": 1, "S3": 1, "S4": 2, "S5": 3}
        self.toy["slices"].reverse()
        graph = {row["id"]: row["blocked_by"] for row in self.toy["slices"]}
        self.assertEqual(compute_waves(graph), expected)
        for row in self.toy["slices"]:
            row["wave"] = expected[row["id"]]
        self.assertEqual(validate(self.toy), [])
        self.toy["slices"][0]["wave"] = 1
        self.assert_rule(self.toy, "R6")

    def test_r6_invalid_wave_types(self):
        for wave in (-1, 0.5, True, "0", None):
            with self.subTest(wave=wave):
                self.toy["slices"][0]["wave"] = wave
                self.assert_rule(self.toy, "R6")

    def test_r7_exception_exactly_twenty_percent(self):
        row = self.toy["slices"][-1]
        row.update(kind="enabling", reason="Prepare fixture images for the download check.", layers_touched=["test data"], engines={})
        self.assertEqual(validate(self.toy), [])
        self.toy["slices"][3].update(kind="enabling", reason="Prepare gallery fixtures", engines={})
        self.assert_rule(self.toy, "R7")

    def test_r7_layer_and_reason_exceptions(self):
        for kind, reason in (("vertical", None), ("enabling", None), ("enabling", "  ")):
            with self.subTest(kind=kind, reason=reason):
                matrix = copy.deepcopy(self.toy)
                matrix["slices"][-1].update(kind=kind, layers_touched=["storage"], engines={})
                if reason is not None:
                    matrix["slices"][-1]["reason"] = reason
                self.assert_rule(matrix, "R7")

    def test_r8_duplicate_ids_in_each_collection_and_across_collections(self):
        for target in ("slice", "engine", "requirement", "cross"):
            with self.subTest(target=target):
                matrix = copy.deepcopy(self.toy)
                if target == "slice":
                    matrix["slices"].append(copy.deepcopy(matrix["slices"][-1]))
                elif target == "engine":
                    matrix["engines"].append(copy.deepcopy(matrix["engines"][0]))
                elif target == "requirement":
                    matrix["source"]["requirements"].append("REQ1")
                else:
                    matrix["engines"][0]["id"] = "S1"
                self.assert_rule(matrix, "R8")

    def test_r8_unknown_cells_and_requirement_shape(self):
        self.toy["slices"][0]["engines"]["UNKNOWN"] = "uses"
        self.assert_rule(self.toy, "R8")
        self.toy["source"]["requirements"] = []
        self.assert_rule(self.toy, "R8")

    def test_malformed_shapes_do_not_crash(self):
        values = [None, True, 4, "text", [], {}, ["nested"]]
        for value in values:
            with self.subTest(root=value):
                self.assert_rule(value, "R8")
            for field in ("source", "engines", "slices"):
                with self.subTest(field=field, value=value):
                    matrix = copy.deepcopy(self.toy)
                    matrix[field] = value
                    errors = validate(matrix)
                    if field == "engines" and value == []:
                        self.assertTrue(errors)  # Existing cells now refer to unknown engines.
                    else:
                        self.assertIn("R8", rule_ids(errors))
            for field in self.toy["slices"][0]:
                with self.subTest(row_field=field, value=value):
                    matrix = copy.deepcopy(self.toy)
                    matrix["slices"][0][field] = value
                    errors = validate(matrix)
                    self.assertIsInstance(errors, list)
                    if value is None:
                        self.assertIn("R8", rule_ids(errors))

    def test_all_detected_rules_reported_together(self):
        matrix = load_json(ROOT / "examples/bad-cycle.json")
        matrix["slices"][0]["est_hours"] = 9
        matrix["slices"][-1]["covers"] = []
        matrix["slices"][-1]["kind"] = "enabling"
        matrix["slices"][-1]["wave"] = -1
        errors = rule_ids(validate(matrix))
        self.assertTrue({"R1", "R4", "R5", "R6", "R7", "R8"}.issubset(errors), errors)

    def test_schema_is_draft_2020_12_and_audited(self):
        schema = load_json(SCHEMA_PATH)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        audit_schema(schema, schema)
        schema["$defs"]["text"]["maxLength"] = 8
        with self.assertRaisesRegex(ValueError, "unsupported schema keywords"):
            audit_schema(schema, schema)

    def test_cli_valid_missing_malformed_duplicate_keys_and_nonfinite(self):
        result = self.cli("validate_matrix.py", ROOT / "examples/toy.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.cli("validate_matrix.py", ROOT / "absent.json").returncode, 1)
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "input.json"
            for raw in ('{', '{"source": {}, "source": {}}', '{"n": NaN}', '{"n": Infinity}'):
                with self.subTest(raw=raw):
                    path.write_text(raw)
                    result = self.cli("validate_matrix.py", path)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("R8:", result.stdout)
                    self.assertNotIn("Traceback", result.stderr)

    def test_renderer_grid_and_computed_waves(self):
        result = self.cli("render_matrix.py", ROOT / "examples/toy.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| E1: Shared image storage |", result.stdout)
        self.assertEqual(result.stdout.count("| builds |"), 1)
        self.assertEqual(result.stdout.count("| uses |"), 4)
        self.assertIn("- Wave 0: S1", result.stdout)
        self.assertIn("- Wave 1: S2, S3", result.stdout)
        self.assertIn("- Wave 2: S4", result.stdout)
        self.assertIn("- Wave 3: S5", result.stdout)

    def test_renderer_refuses_invalid_input_without_grid(self):
        result = self.cli("render_matrix.py", ROOT / "examples/bad-r6-wave.json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("R6:", result.stderr)

    def test_renderer_escapes_table_and_markup_characters(self):
        self.toy["slices"][0]["title"] = "A|B\n<script>*x* [link](url)"
        output = render(self.toy)
        self.assertIn("A&#124;B<br>&lt;script&gt;&#42;x&#42; &#91;link&#93;(url)", output)

    def test_empty_engine_list_is_valid(self):
        self.toy["engines"] = []
        for row in self.toy["slices"]:
            row["engines"] = {}
        self.assertEqual(validate(self.toy), [])
        self.assertIn("| Slice | Behavior | Wave | Blocked by |", render(self.toy))

    def test_deep_graph_does_not_depend_on_python_recursion(self):
        graph = {"0": []}
        for index in range(1, 1200):
            graph[str(index)] = [str(index - 1)]
        from validate_matrix import check_cycles
        errors = []
        check_cycles(graph, errors)
        self.assertEqual(errors, [])
        self.assertEqual(compute_waves(graph)["1199"], 1199)
        graph["0"] = ["1199"]
        check_cycles(graph, errors)
        self.assertEqual(rule_ids(errors), {"R4"})


if __name__ == "__main__":
    unittest.main()


def test_source_capacity_accepted_and_bounded(tmp_path):
    """Founder decision 2026-09-30: plans carry their builder capacity; zero or more than 24 hours a day is refused."""
    import copy, json, subprocess, sys
    here = Path(__file__).resolve().parents[1]
    base = json.loads((here / "examples" / "toy.json").read_text())
    for cap, want in [({"builders": 4, "hours_per_day": 23}, 0), ({"builders": 0, "hours_per_day": 23}, 1),
                      ({"builders": 4, "hours_per_day": 25}, 1), ({"builders": 4}, 1)]:
        m = copy.deepcopy(base); m["source"]["capacity"] = cap
        f = tmp_path / "m.json"; f.write_text(json.dumps(m))
        r = subprocess.run([sys.executable, str(here / "scripts" / "validate_matrix.py"), str(f)], capture_output=True, text=True)
        assert r.returncode == want, (cap, r.stdout)
