"""Output-format checks: the JSON Schema, YAML/JSON equality, and one small
comparison of the valid corpus's parsed output.

To regenerate tests/corpus/expected/valid.yaml after an intended change, run

    LABDATA_REGENERATE_EXPECTED=1 uv run pytest tests/conformance/test_output_format.py

and review the diff (git diff tests/corpus/expected/valid.yaml) before committing.
"""

import json
import os

import jsonschema
import pytest
import yaml

from .support import (
    EXPECTED, REPO_ROOT, SCHEMA_PATH, VALID, covers, export, item, xfailed_strings,
)

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


# --- The snapshot ------------------------------------------------------------
# One small comparison of parsed output. It covers only cases whose values no
# open issue is expected to change: everything an active xfail owns is left
# out on purpose, and test_snapshot_avoids_xfailed_cases enforces that. So
# fixing #18, #20, #23, #24 or #28 turns those xfails green without anyone
# having to re-record this file, and the dedicated xfail tests in
# test_valid_corpus.py stay the only place that behavior is stated.

SNAPSHOT = {
    "publications": [
        "str-repeat",         # an expanded @string macro
        "type-article",       # journal, volume and number in the venue
        "type-phdthesis",     # a thesis venue
        "link-doi-bare",      # a DOI link
        "link-youtube",       # a video link
        "present",            # a PDF that exists
        "proj-multiple",      # two project tags, and a TeX-accented author
        "id-external-2023",   # a resolved author beside an unresolved one
    ],
    "people": ["ccote", "eevans", "vvandenberg"],
    "projects": ["homebot"],
    "collaborators": ["Q. Quinn", "R. Ross"],
}
KEYS = {"publications": "bib_id", "people": "id", "projects": "id", "collaborators": "name"}


def select(data):
    """The part of the output the snapshot owns, in the order SNAPSHOT lists."""
    chosen = {"schema_version": data["schema_version"], "lab": data["lab"]}
    for section, wanted in SNAPSHOT.items():
        chosen[section] = [item(data, section, KEYS[section], value) for value in wanted]
    return chosen


def test_snapshot_avoids_xfailed_cases(valid_output):
    """Nothing in the snapshot is owned by an open issue's xfail.

    A publication named by an xfailed case, and anything whose value is
    derived from one, stays out: otherwise a fix would break the snapshot and
    the tempting way out would be to re-record the behavior the xfail rejects.
    """
    bib_ids = {p["bib_id"] for p in valid_output["publications"]}
    excluded = bib_ids & set(xfailed_strings())
    assert excluded, "expected some xfailed entries to exclude"

    chosen = select(valid_output)
    assert [p["bib_id"] for p in chosen["publications"] if p["bib_id"] in excluded] == []
    for section in ("people", "projects"):
        for entry in chosen[section]:
            overlap = sorted(set(entry.get("publication_ids", [])) & excluded)
            assert overlap == [], f"{section} {entry['id']} depends on {overlap}"
    for collaborator in chosen["collaborators"]:
        from_pubs = {p["bib_id"] for p in valid_output["publications"]
                     if any(a["name"] == collaborator["name"] for a in p["authors"])}
        assert sorted(from_pubs & excluded) == [], collaborator["name"]


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
    """The snapshot, compared as parsed data rather than byte for byte."""
    chosen = select(valid_output)
    if os.environ.get("LABDATA_REGENERATE_EXPECTED"):
        with open(EXPECTED_VALID, "w", encoding="utf-8") as f:
            f.write("# Part of the output of tests/corpus/valid/, compared as parsed data by\n"
                    "# tests/conformance/test_output_format.py::test_full_output. The entries\n"
                    "# here are the ones no open issue is expected to change; SNAPSHOT in that\n"
                    "# file says which they are and why the rest is left out. Regenerate with\n"
                    "#   LABDATA_REGENERATE_EXPECTED=1 uv run pytest "
                    "tests/conformance/test_output_format.py\n"
                    "# and review the diff before committing.\n")
            yaml.safe_dump(chosen, f, allow_unicode=True, sort_keys=False, width=100)
        pytest.skip(f"regenerated {EXPECTED_VALID.name}; review the diff")
    with open(EXPECTED_VALID, encoding="utf-8") as f:
        expected = yaml.safe_load(f)
    differences = diff_paths(expected, chosen)
    assert not differences, "\n".join(differences[:40])
