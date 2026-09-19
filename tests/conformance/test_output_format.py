"""Output-format checks: the JSON Schema, YAML/JSON equality, and one full
comparison of the valid corpus's output.

To regenerate tests/corpus/expected/valid.yaml after an intended change, run

    LABDATA_REGENERATE_EXPECTED=1 uv run pytest tests/conformance/test_output_format.py

and review the diff (git diff tests/corpus/expected/valid.yaml) before committing.
"""

import json
import os

import jsonschema
import pytest
import yaml

from .support import EXPECTED, REPO_ROOT, SCHEMA_PATH, VALID, covers, export

DEMO_CONFIG = "examples/demo/lab.yaml"
EXPECTED_VALID = EXPECTED / "valid.yaml"


@pytest.fixture(scope="module")
def validator():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


@pytest.fixture(scope="module")
def demo_exports(tmp_path_factory):
    """The demo's output as (YAML, JSON), exported from the repo root."""
    out = tmp_path_factory.mktemp("demo")
    results = []
    for fmt in ("yaml", "json"):
        run, data = export(REPO_ROOT, out, DEMO_CONFIG, fmt)
        assert run.code == 0 and run.crash is None, run.output
        results.append(data)
    return results


def schema_errors(validator, data):
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in validator.iter_errors(data)]


def check_references(data):
    """Every ID the output refers to exists in the output."""
    people = {p["id"] for p in data["people"]}
    publications = {p["bib_id"] for p in data["publications"]}
    for pub in data["publications"]:
        for author in pub["authors"]:
            assert author["person_id"] in people | {None}, (pub["bib_id"], author)
    for person in data["people"]:
        assert set(person.get("publication_ids", [])) <= publications, person["id"]
        assert person["publication_count"] == len(person.get("publication_ids", []))
    for project in data["projects"]:
        assert set(project["publication_ids"]) <= publications, project["id"]
        assert set(project["people_ids"]) <= people, project["id"]
    collaborator_names = {c["name"] for c in data["collaborators"]}
    unresolved = {a["name"] for p in data["publications"] for a in p["authors"]
                  if a["person_id"] is None}
    assert collaborator_names == unresolved


@covers("output.schema")
def test_valid_corpus_matches_schema(validator, valid_output):
    assert schema_errors(validator, valid_output) == []
    check_references(valid_output)


@covers("output.demo_schema")
def test_demo_matches_schema(validator, demo_exports):
    for data in demo_exports:
        assert schema_errors(validator, data) == []
        check_references(data)


@covers("output.schema")
def test_schema_rejects_unknown_fields(validator, valid_output):
    """The schema is closed, so a new output field must be added to it."""
    data = json.loads(json.dumps(valid_output))
    data["publications"][0]["surprise"] = True
    assert schema_errors(validator, data)


@covers("output.yaml_json_same")
def test_yaml_and_json_hold_the_same_data(tmp_path, valid_output, demo_exports):
    run, yaml_data = export(VALID, tmp_path, fmt="yaml")
    assert run.code == 0 and run.crash is None, run.output
    assert yaml_data == valid_output
    demo_yaml, demo_json = demo_exports
    assert demo_yaml == demo_json


def diff_paths(expected, actual, path=""):
    """List the paths where two parsed outputs differ."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key in sorted(set(expected) | set(actual), key=str):
            if key not in expected or key not in actual:
                out.append(f"{path}/{key}: only in {'actual' if key in actual else 'expected'}")
            else:
                out += diff_paths(expected[key], actual[key], f"{path}/{key}")
        return out
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        out = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            label = e.get("bib_id") or e.get("id") or e.get("name") if isinstance(e, dict) else i
            out += diff_paths(e, a, f"{path}/{label}")
        return out
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


@covers("output.full")
def test_full_output(valid_output):
    """The whole valid-corpus output, compared as parsed data (not byte for byte)."""
    if os.environ.get("LABDATA_REGENERATE_EXPECTED"):
        with open(EXPECTED_VALID, "w", encoding="utf-8") as f:
            f.write("# Expected output of tests/corpus/valid/, compared as parsed data by\n"
                    "# tests/conformance/test_output_format.py. Regenerate with\n"
                    "#   LABDATA_REGENERATE_EXPECTED=1 uv run pytest "
                    "tests/conformance/test_output_format.py\n"
                    "# and review the diff before committing.\n")
            yaml.safe_dump(valid_output, f, allow_unicode=True, sort_keys=False, width=100)
        pytest.skip(f"regenerated {EXPECTED_VALID.name}; review the diff")
    with open(EXPECTED_VALID, encoding="utf-8") as f:
        expected = yaml.safe_load(f)
    differences = diff_paths(expected, valid_output)
    assert not differences, "\n".join(differences[:40])
