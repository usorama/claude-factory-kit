"""Positive and negative controls for every deterministic property type."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scorer", HERE / "run_evals.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def good():
    return {
        "source": {"description": "R1 uploads a profile. R2 uploads a cover.",
                   "outcomes": [{"id": "O1", "text": "Users retain their profile and cover photos.",
                                 "requirements": ["R1", "R2"], "first_proof": "S1"}],
                   "requirements": ["R1", "R2"], "features": ["Upload profile", "Upload cover"]},
        "engines": [{"id": "E1", "title": "Media storage"}],
        "slices": [
            {"id": "S1", "title": "Upload profile", "behavior": "Saved profile survives reload.",
             "layers_touched": ["view", "storage"],
             "acceptance": [{"type": "yes_no", "check": "Upload succeeds and profile survives reload.",
                             "observable": "Upload profile, reload and see the same photo."}],
             "blocked_by": [], "size": "S", "est_hours": 2, "covers": ["R1"], "outcomes": ["O1"], "engines": {"E1": "builds"}},
            {"id": "S2", "title": "Upload cover", "behavior": "Saved cover survives reload.",
             "layers_touched": ["view", "storage"],
             "acceptance": [{"type": "yes_no", "check": "Cover survives reload.",
                             "observable": "Upload cover, reload and see the same photo."}],
             "blocked_by": ["S1"], "size": "S", "est_hours": 2, "covers": ["R2"], "outcomes": ["O1"], "engines": {"E1": "uses"}},
        ],
    }


def mutate(obj, path, value):
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value


# Each negative changes exactly the evidence that the property reads.
CONTROLS = [
    ({"type":"slice_count","min":2,"max":2}, ["slices"], []),
    ({"type":"engine_count","min":1,"max":1}, ["engines"], []),
    ({"type":"required_engine","aliases":["media storage","image storage"]}, ["engines",0,"title"], "Payments"),
    ({"type":"forbidden_engine","aliases":["invoice"]}, ["engines",0,"title"], "Invoice formatter"),
    ({"type":"first_covers","ids":["R1"]}, ["slices",0,"covers"], ["R2"]),
    ({"type":"first_unblocked"}, ["slices",0,"blocked_by"], ["S2"]),
    ({"type":"first_vertical"}, ["slices",0,"kind"], "enabling"),
    ({"type":"first_terms","groups":[["reload","refresh"],["profile"]]}, ["slices",0,"acceptance"], []),
    ({"type":"covers","ids":["R1","R2"]}, ["slices",1,"covers"], []),
    ({"type":"acyclic"}, ["slices",0,"blocked_by"], ["S2"]),
    ({"type":"layers","groups":[["view"],["storage"]]}, ["slices"], []),
    ({"type":"forbidden_layer","aliases":["database"]}, ["slices",0,"layers_touched"], ["database"]),
    ({"type":"required_check","groups":[["upload"],["reload"]]}, ["slices"], []),
    ({"type":"dependency","before":"R1","after":"R2"}, ["slices",1,"blocked_by"], []),
    ({"type":"max_hours","value":8}, ["slices",1,"est_hours"], 9),
    ({"type":"enabling_max","value":.2}, ["slices",1,"kind"], "enabling"),
    ({"type":"requirement_terms","requirement":"R1","groups":[["reload"]]}, ["slices",0,"acceptance"], []),
    ({"type":"history_probe","requirement":"R1","groups":[["profile"]]}, ["slices",0,"acceptance"], []),
]


@pytest.mark.parametrize("prop,path,value", CONTROLS, ids=[x[0]["type"] for x in CONTROLS])
def test_property_good_and_bad(prop, path, value, tmp_path):
    prop = dict(prop, id=prop["type"])
    expected = {"must_stop":False, "properties":[prop]}
    output = tmp_path / "output.json"
    matrix = good()
    output.write_text(json.dumps(matrix))
    result = scorer.score(expected, output)
    assert result["S1"] is True
    assert result["properties"][1]["pass"] is True
    mutate(matrix, path, value)
    output.write_text(json.dumps(matrix))
    assert scorer.score(expected, output)["properties"][1]["pass"] is False


def test_existing_engine_good_and_bad(tmp_path):
    matrix = good()
    matrix["engines"][0]["existing"] = True
    matrix["slices"][0]["engines"]["E1"] = "uses"
    prop = {"id":"existing", "type":"existing_engine", "aliases":["media storage"]}
    expected = {"must_stop":False, "properties":[prop]}
    output = tmp_path / "output.json"
    output.write_text(json.dumps(matrix))
    result = scorer.score(expected, output)
    assert result["properties"][1]["pass"] is True
    assert result["S1"] is True
    matrix["slices"][0]["engines"]["E1"] = "builds"
    output.write_text(json.dumps(matrix))
    assert scorer.score(expected, output)["properties"][1]["pass"] is False


def test_existing_engine_single_user_and_missing_flag(tmp_path):
    output = HERE.parent / "examples/existing-engine.json"
    matrix = scorer.read(output)
    prop = {"id":"existing", "type":"existing_engine", "aliases":["MediaStore"]}
    expected = {"must_stop":False, "properties":[prop]}
    result = scorer.score(expected, output)
    assert result["S1"] and result["S2_passed"] == result["S2_total"]
    for value in (False, "true", 1, None):
        matrix["engines"][0]["existing"] = value
        assert not scorer.property_holds(prop, matrix)
    del matrix["engines"][0]["existing"]
    assert not scorer.property_holds(prop, matrix)
    matrix["engines"][0]["existing"] = True
    matrix["slices"][0]["engines"] = {}
    assert not scorer.property_holds(prop, matrix)


def test_all_property_types_have_controls():
    assert {x[0]["type"] for x in CONTROLS} | {"existing_engine"} == scorer.TYPES
    used = {p["type"] for path in (HERE / "cases").glob("*/expected.json")
            for p in scorer.read(path)["properties"]}
    assert used <= scorer.TYPES


@pytest.mark.parametrize("case,rule", [("05-hidden-cycle", "contradictory_order"),
                                       ("06-vague", "vague_acceptance")])
def test_case_must_stop(tmp_path, case, rule):
    """The required sabotage target: a valid invented plan is still wrong here."""
    expected = scorer.read(HERE / "cases" / case / "expected.json")
    output = tmp_path / "out.json"
    output.write_text(json.dumps({"stop":True, "rule":rule, "reason":"Owner clarification is required.",
                                  "questions":["Which outcome and pass threshold should improve?"]}))
    result = scorer.score(expected, output)
    assert result["S1"] is True
    assert result["properties"][0]["pass"] is True
    assert result["S2_passed"] == result["S2_total"]
    output.write_text(json.dumps(good()))
    result = scorer.score(expected, output)
    assert result["S1"] is False
    assert result["properties"][0]["pass"] is False


@pytest.mark.parametrize("raw", [
    '{"status":"stop"}',
    '{"status":"stop","reason":"x","questions":[]}',
    '{"status":"stop","reason":"x","questions":["not a question"]}',
    '{"status":"stop","reason":"x","questions":["Which?"],"slices":[{}]}',
    '{"stop":true,"reason":"x","rule":"vague_acceptance"}',
    '{"stop":true,"reason":"x","rule":"vague_acceptance","questions":[]}',
    '{"stop":true,"reason":"x","rule":"vague_acceptance","questions":[" "]}',
    '{"stop":true,"reason":"x","rule":"unknown","questions":["Which?"]}',
    '{"stop":true,"reason":"x","rule":"missing_source","questions":["Which?"],"slices":[]}',
    '{"stop":false,"stop":true,"reason":"x","rule":"missing_source","questions":["Which?"]}',
    '{"stop":1,"reason":"x","rule":"missing_source","questions":["Which?"]}',
    'The word stop appears in a question? But no decision is recorded.',
    '', '[]', 'null', '{broken',
])
def test_false_stops_rejected(raw, tmp_path):
    assert not scorer.stopped(raw)
    output = tmp_path / "out.json"
    output.write_text(raw)
    result = scorer.score({"must_stop":True, "properties":[]}, output)
    assert not result["S1"] and not result["properties"][0]["pass"]


def test_plain_stop_rejected_and_structured_stop_unexpected(tmp_path):
    raw = 'Stop: the plan has no definition of success, so acceptance would be invented. Which user outcome should improve?'
    assert not scorer.stopped(raw)
    output = tmp_path / "stop.txt"
    output.write_text(raw)
    expected = scorer.read(HERE / "cases/06-vague/expected.json")
    assert not scorer.score(expected, output)["S1"]
    output.write_text(json.dumps({"stop":True, "rule":"missing_source",
                                  "reason":"The required plan file is missing.",
                                  "questions":["Where is the plan?"]}))
    assert scorer.stopped(output.read_text())
    assert scorer.score(expected, output)["S1"]
    assert not scorer.score({"must_stop":False,"properties":[]}, output)["S1"]


def test_format_bad_output_and_unknown_property(tmp_path):
    output = tmp_path / "out.json"
    output.write_text('{"slices": []}')
    assert not scorer.score({"must_stop":False,"properties":[]}, output)["S1"]
    with pytest.raises(ValueError, match="Unknown property"):
        scorer.score({"must_stop":False,"properties":[{"id":"x","type":"typo"}]}, output)


def test_coverage_requires_source_declaration():
    matrix = good()
    matrix["source"]["requirements"] = ["R1"]
    assert not scorer.property_holds({"type":"covers","ids":["R2"]}, matrix)


def test_required_check_does_not_read_unrelated_description():
    matrix = good()
    matrix["source"]["description"] = "test_cross_family_report_denied sabotage restore"
    assert not scorer.property_holds({"type":"required_check","groups":[["sabotage"]]}, matrix)


def test_history_probe_is_bound_to_requirement():
    matrix = good()
    assert not scorer.property_holds({"type":"history_probe","requirement":"R1","groups":[["cover"]]}, matrix)


def test_dependency_transitive_and_not_self():
    matrix = good()
    middle = copy.deepcopy(matrix["slices"][1])
    middle.update(id="MID", covers=[])
    matrix["slices"][1]["blocked_by"] = ["MID"]
    matrix["slices"].append(middle)
    assert scorer.property_holds({"type":"dependency","before":"R1","after":"R2"}, matrix)
    matrix = good()
    matrix["slices"][1]["covers"] = ["R2","R1"]
    matrix["slices"][0]["covers"] = []
    assert not scorer.property_holds({"type":"dependency","before":"R1","after":"R2"}, matrix)


def test_acyclic_rejects_missing_blocker_and_duplicate_id():
    matrix = good()
    matrix["slices"][1]["blocked_by"] = ["MISSING"]
    assert not scorer.property_holds({"type":"acyclic"}, matrix)
    matrix = good()
    matrix["slices"][1]["id"] = "S1"
    assert not scorer.property_holds({"type":"acyclic"}, matrix)


def test_synonyms_and_word_boundaries():
    assert scorer.mentions("Shared media-storage", ["media storage"])
    assert not scorer.mentions("database", ["data"])


def test_judge_polarity_and_malformed_answers(tmp_path):
    output = tmp_path / "judge.json"
    answers = [{"question":q,"yes":i < 4,"reason":"Specific evidence."} for i,q in enumerate(scorer.QUESTIONS)]
    output.write_text(json.dumps({"answers":answers}))
    result = scorer.judge_score(output)
    assert result["yes_count"] == 4 and result["favorable_count"] == 5
    answers[-1]["yes"] = True
    output.write_text(json.dumps({"answers":answers}))
    result = scorer.judge_score(output)
    assert result["yes_count"] == 5 and result["favorable_count"] == 4
    answers[-1]["yes"] = "yes"
    output.write_text(json.dumps({"answers":answers}))
    with pytest.raises(ValueError):
        scorer.judge_score(output)


def test_missing_runs_are_unavailable_not_failures(tmp_path, monkeypatch):
    monkeypatch.setitem(scorer.CONFIG, "slicers", {"model-a": [], "model-b": []})
    scorer.summarize([HERE / "cases/03-tiny"], tmp_path)
    records = scorer.read(tmp_path / "scores.json")
    assert len(records) == 2
    assert all(r["status"] == "unavailable" and "S1" not in r and r["S3"] is None for r in records)
    assert "N/A" in (tmp_path / "summary.md").read_text()


def test_cli_scoring_real_files(tmp_path):
    case = HERE / "cases/03-tiny"
    folder = tmp_path / "gpt-6-luna" / case.name
    folder.mkdir(parents=True)
    matrix = good()
    matrix["source"]["requirements"] = ["R1"]
    matrix["source"]["outcomes"] = [{"id": "O1", "text": "Users can save their address with a correctly labelled button.",
                                     "requirements": ["R1"], "first_proof": "S1"}]
    matrix["engines"] = []
    matrix["slices"] = matrix["slices"][:1]
    matrix["slices"][0]["engines"] = {}
    matrix["slices"][0]["acceptance"][0]["check"] = 'The label is Save address and the saved address survives reload.'
    (folder / "out.json").write_text(json.dumps(matrix))
    result = subprocess.run([sys.executable, str(HERE / "run_evals.py"), "score", "--results", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    records = scorer.read(tmp_path / "scores.json")
    scored = [r for r in records if r["status"] == "scored"]
    assert len(scored) == 1
    assert scored[0]["S1"] and scored[0]["S2_passed"] == scored[0]["S2_total"]
