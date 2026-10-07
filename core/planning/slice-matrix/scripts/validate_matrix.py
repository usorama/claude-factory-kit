#!/usr/bin/env python3
"""Validate the bundled slice-matrix format with Python's standard library."""

import json
import math
from pathlib import Path
import re
from statistics import median
import sys


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema/slice-matrix.schema.json"
KEYWORDS = {
    "$schema", "$defs", "$ref", "title", "type", "required", "properties",
    "additionalProperties", "propertyNames", "items", "minItems", "uniqueItems",
    "minLength", "pattern", "enum", "const", "minimum", "maximum",
    "exclusiveMinimum", "anyOf", "allOf", "if", "then", "else",
}


def json_equal(left, right):
    """JSON booleans are not numbers, including inside arrays and objects."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(map(lambda pair: json_equal(*pair), zip(left, right)))
    return left == right


def is_number(value):
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def matches_type(value, name):
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "boolean": lambda: type(value) is bool,
        "number": lambda: is_number(value),
        "integer": lambda: is_number(value) and value % 1 == 0,
    }[name]()


def audit_schema(schema, root):
    """Reject unsupported schema changes instead of silently skipping them."""
    if isinstance(schema, bool):
        return
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError(f"unsupported schema keywords: {sorted(unknown)}")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/") or ref[8:] not in root["$defs"]:
            raise ValueError(f"unsupported schema reference: {ref}")
    if "type" in schema and schema["type"] not in {"object", "array", "string", "boolean", "number", "integer"}:
        raise ValueError(f"unsupported schema type: {schema['type']}")
    for key in ("$defs", "properties"):
        for child in schema.get(key, {}).values():
            audit_schema(child, root)
    for key in ("additionalProperties", "propertyNames", "items", "if", "then", "else"):
        if key in schema:
            audit_schema(schema[key], root)
    for key in ("anyOf", "allOf"):
        for child in schema.get(key, []):
            audit_schema(child, root)


def schema_errors(value, schema, root, path="$"):
    """Implement precisely the draft 2020-12 keywords in the bundled schema."""
    if isinstance(schema, bool):
        return [] if schema else [f"{path}: forbidden value"]
    errors = []
    if "$ref" in schema:
        errors.extend(schema_errors(value, root["$defs"][schema["$ref"][8:]], root, path))
    if "type" in schema and not matches_type(value, schema["type"]):
        return errors + [f"{path}: expected {schema['type']}"]
    if "enum" in schema and not any(json_equal(value, choice) for choice in schema["enum"]):
        errors.append(f"{path}: expected one of {schema['enum']}")
    if "const" in schema and not json_equal(value, schema["const"]):
        errors.append(f"{path}: expected {schema['const']!r}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if "propertyNames" in schema:
                errors.extend(schema_errors(key, schema["propertyNames"], root, f"{path} key {key!r}"))
            if key in properties:
                errors.extend(schema_errors(item, properties[key], root, f"{path}.{key}"))
            elif "additionalProperties" in schema:
                errors.extend(schema_errors(item, schema["additionalProperties"], root, f"{path}.{key}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} items")
        if schema.get("uniqueItems") and any(
            json_equal(item, previous) for index, item in enumerate(value) for previous in value[:index]
        ):
            errors.append(f"{path}: items must be unique")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], root, f"{path}[{index}]"))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: text is too short")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: text does not match {schema['pattern']!r}")
    if is_number(value):
        for key, invalid in (("minimum", lambda n: value < n),
                             ("maximum", lambda n: value > n),
                             ("exclusiveMinimum", lambda n: value <= n)):
            if key in schema and invalid(schema[key]):
                errors.append(f"{path}: violates {key} {schema[key]}")
    for child in schema.get("allOf", []):
        errors.extend(schema_errors(value, child, root, path))
    if "anyOf" in schema and all(schema_errors(value, child, root, path) for child in schema["anyOf"]):
        errors.append(f"{path}: must match at least one alternative {schema['anyOf']}")
    if "if" in schema:
        branch = "else" if schema_errors(value, schema["if"], root, path) else "then"
        if branch in schema:
            errors.extend(schema_errors(value, schema[branch], root, path))
    return errors


def string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def compute_waves(graph):
    """Longest blocker path, starting at zero. Cycles and their dependents stay absent."""
    waves = {}
    pending = dict(graph)
    while pending:
        ready = [sid for sid, blockers in pending.items() if all(b in waves for b in blockers)]
        if not ready:
            break
        for sid in ready:
            waves[sid] = max((waves[b] + 1 for b in pending.pop(sid)), default=0)
    return waves


def dependency_graph(rows):
    """All edges constrain ordering, including every alternative and condition."""
    graph = {}
    for row in rows:
        if not isinstance(row.get("id"), str):
            continue
        refs = []
        blockers = row.get("blocked_by", [])
        if string_list(blockers):
            refs.extend(blockers)
        condition = row.get("runs_if", {})
        if isinstance(condition, dict) and string_list(condition.get("failed", [])):
            refs.extend(condition.get("failed", []))
        groups = row.get("blocked_by_any", [])
        if isinstance(groups, list):
            for group in groups:
                if string_list(group):
                    refs.extend(group)
        graph[row["id"]] = list(dict.fromkeys(refs))
    return graph


def compute_path_schedule(rows, worst=False):
    """Plan terminal states separately from finish waves. Input must be valid."""
    order = compute_waves(dependency_graph(rows))
    by_id = {row["id"]: row for row in rows}
    failed = {sid for row in rows for sid in row.get("runs_if", {}).get("failed", [])} if worst else set()
    waves, states = {}, {}
    for sid in sorted(order, key=order.get):
        row = by_id[sid]
        conditions = row.get("runs_if", {}).get("failed", [])
        if conditions and not worst:
            states[sid] = "skipped"
            continue
        blockers = row["blocked_by"]
        if (any(states.get(b) != "passed" for b in blockers)
                or any(states.get(b) not in ("failed", "skipped") for b in conditions)):
            states[sid] = "blocked"
            continue
        groups = row.get("blocked_by_any", [])
        group_waves = [max(waves[b] + 1 for b in group) for group in groups
                       if all(states.get(b) == "passed" for b in group)]
        if groups and not group_waves:
            states[sid] = "blocked"
            continue
        wave = max((waves[b] + 1 for b in blockers + conditions if b in waves), default=0)
        if group_waves:
            wave = max(wave, (max if worst else min)(group_waves))
        waves[sid] = wave
        states[sid] = "failed" if sid in failed else "passed"
    return waves, states


def check_conditions(rows, schema, errors):
    """R10 keeps failed/skipped candidates separate from passing prerequisites."""
    by_id = {row["id"]: row for row in rows if isinstance(row.get("id"), str)}
    for row in rows:
        sid = row.get("id")
        malformed = False
        for field in ("runs_if", "blocked_by_any"):
            if field in row:
                failures = schema_errors(row[field], schema["$defs"]["slice"]["properties"][field], schema, f"{sid}.{field}")
                errors.extend(f"R10: {failure}" for failure in failures)
                malformed |= bool(failures)
        if malformed or not string_list(row.get("blocked_by")):
            continue
        failed = row.get("runs_if", {}).get("failed", [])
        groups = row.get("blocked_by_any", [])
        conflict = set(row["blocked_by"]).intersection(failed)
        if conflict:  # R10 conflict check; sabotage this condition only.
            errors.append(f"R10: {sid}: blocked_by and runs_if.failed overlap: {', '.join(sorted(conflict))}")
        for ref in failed + [ref for group in groups for ref in group]:
            if ref not in by_id:
                errors.append(f"R10: {sid}: unknown conditional/alternative slice {ref}")
        for ref in row["blocked_by"]:
            if ref in by_id and "runs_if" in by_id[ref]:
                errors.append(f"R10: {sid}: conditional blocker {ref} requires blocked_by_any with a passing alternative; remove it from blocked_by")
        for group in groups:
            if set(group).intersection(failed):
                errors.append(f"R10: {sid}: alternative group requires a runs_if.failed slice to pass")


def check_cycles(graph, errors):
    """Iterative DFS reports back edges without recursion-depth limits."""
    state = {}
    for start in graph:
        if state.get(start):
            continue
        state[start] = 1
        stack = [(start, iter(graph[start]))]
        while stack:
            sid, blockers = stack[-1]
            blocker = next(blockers, None)
            if blocker is None:
                state[sid] = 2
                stack.pop()
            elif blocker not in graph:
                continue
            elif state.get(blocker) == 1:
                errors.append(f"R4: cycle found at {sid} -> {blocker}")
            elif not state.get(blocker):
                state[blocker] = 1
                stack.append((blocker, iter(graph[blocker])))


def check_outcomes(source, requirements, errors):
    outcomes = source.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        errors.append("R9: source.outcomes must be a non-empty array")
        outcomes = []
    seen = set()
    assigned = set()
    for index, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict):
            errors.append(f"R9: outcome[{index}] must be an object")
            continue
        oid = outcome.get("id")
        if isinstance(oid, str):
            if oid in seen:
                errors.append(f"R9: duplicate outcome ID {oid}")
            seen.add(oid)
        refs = outcome.get("requirements")
        if not string_list(refs) or not refs:
            errors.append(f"R9: {oid}: outcome needs at least one requirement ID")
            continue
        assigned.update(refs)
        for requirement in refs:
            if requirement not in requirements:
                errors.append(f"R9: {oid}: unknown requirement {requirement}")
    orphans = [requirement for requirement in requirements if requirement not in assigned]
    if orphans:  # R9 orphan check; sabotage this condition only.
        errors.append("R9: requirements that lead to no outcome: " + ", ".join(orphans))


def check_slice_outcomes(source, rows, errors):
    raw_outcomes = source.get("outcomes", [])
    outcomes = {}
    if isinstance(raw_outcomes, list):
        for outcome in raw_outcomes:
            if isinstance(outcome, dict) and isinstance(outcome.get("id"), str):
                outcomes.setdefault(outcome["id"], outcome)
    slices = {row["id"]: row for row in rows if isinstance(row.get("id"), str)}
    for row in rows:
        sid = row.get("id")
        refs = row.get("outcomes")
        if not string_list(refs) or not refs:
            errors.append(f"R9: {sid}: outcomes must be a non-empty array of outcome IDs")
            continue
        covers = row.get("covers")
        for oid in refs:
            if oid not in outcomes:
                errors.append(f"R9: {sid}: unknown outcome {oid}")
                continue
            requirements = outcomes[oid].get("requirements")
            if string_list(covers) and string_list(requirements):
                if not set(covers).intersection(requirements):  # R9 shared-requirement check.
                    errors.append(f"R9: {sid}: covers must share a requirement with outcome {oid}")
    for oid, outcome in outcomes.items():
        proof = outcome.get("first_proof")
        if not isinstance(proof, str) or not proof:
            errors.append(f"R9: {oid}: first_proof must name a slice ID")
        elif proof not in slices:
            errors.append(f"R9: {oid}: unknown first_proof slice {proof}")
        else:
            refs = slices[proof].get("outcomes")
            if not string_list(refs) or oid not in refs:
                errors.append(f"R9: {oid}: first_proof slice {proof} must name outcome {oid}")


def outcome_completion_report(matrix, waves=None):
    """Informational first proof and completion from validated, explicit outcome links."""
    rows = matrix["slices"]
    success, success_states = compute_path_schedule(rows)
    worst, worst_states = compute_path_schedule(rows, worst=True)
    if any("runs_if" in row or "blocked_by_any" in row for row in rows):
        lines = ["Waves start at 0. Outcome timing is planned, not verified."]
        for label, path, states in (("success path", success, success_states), ("worst path", worst, worst_states)):
            first_waves = []
            for outcome in matrix["source"]["outcomes"]:
                proof = outcome["first_proof"]
                first = path.get(proof) if states.get(proof) == "passed" else None
                if first is not None:
                    first_waves.append(first)
                passed = [path[row["id"]] for row in rows
                          if outcome["id"] in row["outcomes"] and states.get(row["id"]) == "passed"]
                complete = f"wave {max(passed)}" if passed else "unavailable (no passing slice)"
                if any(outcome["id"] in row["outcomes"] and states.get(row["id"]) == "blocked" for row in rows):
                    complete = "unavailable (blocked slice)"
                first_text = f"wave {first}" if first is not None else f"unavailable ({proof} {states.get(proof, 'unscheduled')})"
                lines.append(f"{outcome['id']}: {outcome['text']}: {label}: first working at {first_text}, complete at {complete}")
            median_text = f"{median(first_waves):g}" if len(first_waves) == len(matrix["source"]["outcomes"]) else "unavailable (first proof did not pass)"
            lines.append(f"Median first-working wave across outcomes ({label}): {median_text}")
        return lines
    waves = success if waves is None else waves
    final_wave = max(waves.values())
    lines = [f"Waves start at 0; final wave is {final_wave}. Outcome timing is planned, not verified."]
    first_waves = []
    for outcome in matrix["source"]["outcomes"]:
        first = waves[outcome["first_proof"]]
        first_waves.append(first)
        completion = max(waves[row["id"]] for row in matrix["slices"]
                         if outcome["id"] in row["outcomes"])
        lines.append(f"{outcome['id']}: {outcome['text']}: first working at wave {first}, complete at wave {completion}")
        lines.append(f"{outcome['id']}: success path: complete at wave {completion}; worst path: complete at wave {completion}")
    lines.append(f"Median first-working wave across outcomes: {median(first_waves):g}")
    return lines


def validate(matrix):
    schema = load_json(SCHEMA_PATH)
    audit_schema(schema, schema)
    errors = [f"R8: {error}" for error in schema_errors(matrix, schema, schema)]
    if not isinstance(matrix, dict) or "stop" in matrix:
        return errors
    raw_rows = matrix.get("slices", [])
    rows = [r for r in raw_rows if isinstance(r, dict)] if isinstance(raw_rows, list) else []
    source = matrix.get("source", {})
    source = source if isinstance(source, dict) else {}
    requirements = source.get("requirements", [])
    requirements = requirements if string_list(requirements) else []
    check_outcomes(source, requirements, errors)
    check_slice_outcomes(source, rows, errors)
    check_conditions(rows, schema, errors)
    engines = matrix.get("engines", [])
    engines = [e for e in engines if isinstance(e, dict)] if isinstance(engines, list) else []
    engine_ids = {e["id"] for e in engines if isinstance(e.get("id"), str)}
    existing_ids = {e["id"] for e in engines
                    if isinstance(e.get("id"), str) and e.get("existing") is True}
    slice_ids = {r["id"] for r in rows if isinstance(r.get("id"), str)}
    seen = set()
    for label, ids in (("requirement", requirements),
                       ("engine", [e.get("id") for e in engines]),
                       ("slice", [r.get("id") for r in rows])):
        for identifier in ids:
            if not isinstance(identifier, str):
                continue
            if identifier in seen:
                errors.append(f"R8: duplicate {label} ID {identifier}")
            seen.add(identifier)

    required = ("id", "title", "behavior", "layers_touched", "acceptance", "blocked_by", "size", "est_hours")
    covered = set()
    graph = dependency_graph(rows)
    for index, row in enumerate(rows):
        sid = row.get("id", f"row[{index}]")
        for field in required:
            if field not in row:
                errors.append(f"R1: {sid}: missing {field}")
            else:
                for error in schema_errors(row[field], schema["$defs"]["slice"]["properties"][field], schema, str(sid) + "." + field):
                    errors.append(f"R1: {error}")
        layers = row.get("layers_touched")
        enabling = row.get("kind") == "enabling"
        if string_list(layers) and len(set(layers)) < 2 and not enabling:
            errors.append(f"R1: {sid}: needs at least two distinct layers (R7 exception only)")
            errors.append(f"R7: {sid}: horizontal row requires kind enabling and a reason")
        if enabling and (not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            errors.append(f"R7: {sid}: enabling row needs a reason")
        blockers = row.get("blocked_by")
        if string_list(blockers):
            for blocker in blockers:
                if blocker not in slice_ids:
                    errors.append(f"R4: {sid}: unknown blocker {blocker}")
        covers = row.get("covers", [])
        if string_list(covers):
            covered.update(covers)
            for requirement in covers:
                if requirement not in requirements:
                    errors.append(f"R5: {sid}: unknown requirement {requirement}")
        cells = row.get("engines", {})
        if isinstance(cells, dict):
            for engine in cells:
                if engine not in engine_ids:
                    errors.append(f"R8: {sid}: unknown engine {engine}")

    if rows and sum(r.get("kind") == "enabling" for r in rows) * 5 > len(rows):
        errors.append("R7: enabling rows exceed 20% of all slices")
    for requirement in requirements:
        if requirement not in covered:
            errors.append(f"R5: uncovered requirement {requirement}")
    for engine in sorted(engine_ids):
        participants = [r for r in rows if isinstance(r.get("engines"), dict)
                        and r["engines"].get(engine) in ("builds", "uses")]
        participant_ids = {r.get("id") for r in participants if isinstance(r.get("id"), str)}
        builders = [r for r in participants if r["engines"][engine] == "builds"]
        if engine in existing_ids:
            users = [r for r in participants if r["engines"][engine] == "uses"]
            if not users:
                errors.append(f"R2: {engine}: existing engine needs at least one uses row")
                errors.append(f"R3: {engine}: existing engine requires at least one uses cell")
            if builders:
                errors.append(f"R3: {engine}: existing engine requires zero builds cells, got {len(builders)}")
            continue
        if len(participant_ids) < 2:
            errors.append(f"R2: {engine}: needs at least two participating slices")
        if len(builders) != 1:
            errors.append(f"R3: {engine}: expected exactly one builds cell, got {len(builders)}")
            continue
        builder = builders[0]
        builder_id = builder.get("id")
        layers = builder.get("layers_touched")
        if builder.get("kind", "vertical") != "vertical" or not string_list(layers) or len(set(layers)) < 2:
            errors.append(f"R3: {engine}: builder must be a vertical slice")
        for row in participants:
            blockers = row.get("blocked_by")
            if row["engines"][engine] == "uses" and (not string_list(blockers) or builder_id not in blockers):
                errors.append(f"R3: {engine}: {row.get('id')} must be blocked directly by {builder_id}")

    check_cycles(graph, errors)  # R4 cycle check; sabotage this call only.
    waves = compute_waves(graph)
    if not errors:
        waves, _ = compute_path_schedule(rows, worst=True)
        _, success_states = compute_path_schedule(rows)
        for row in rows:
            if "runs_if" not in row and success_states.get(row["id"]) == "blocked":
                errors.append(f"R10: {row['id']}: no passing alternative on the success path")
            if "wave" in row and row["id"] not in waves:
                errors.append(f"R6: {row['id']}: stored wave has no computable worst-path wave")
    for row in rows:
        sid = row.get("id")
        if "wave" in row:
            if not matches_type(row["wave"], "integer") or row["wave"] < 0:
                errors.append(f"R6: {sid}: stored wave must be a nonnegative integer")
            elif isinstance(sid, str) and sid in waves and row["wave"] != waves[sid]:
                errors.append(f"R6: {sid}: stored wave {row['wave']} differs from computed {waves[sid]}")
    return errors


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"non-JSON number {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)


def load_json(path):
    return parse_json(Path(path).read_text(encoding="utf-8"))


def read_and_validate(path):
    try:
        matrix = load_json(path)
        return matrix, validate(matrix)
    except (OSError, ValueError, RecursionError) as exc:
        return None, [f"R8: cannot validate file: {exc}"]


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("R8: usage: validate_matrix.py MATRIX.json")
        return 1
    matrix, errors = read_and_validate(args[0])
    if errors:
        print("\n".join(errors))
        return 1
    if matrix.get("stop") is True:
        print(f"STOP: {matrix['reason']}")
        return 3
    print("Valid: R1-R10 passed")
    print("\n".join(outcome_completion_report(matrix)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
