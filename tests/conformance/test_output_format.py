"""Output-format checks: the JSON Schema, YAML/JSON equality, and one small
comparison of the valid corpus's parsed output.

To regenerate tests/corpus/expected/valid.yaml after an intended change, run

    LABDATA_REGENERATE_EXPECTED=1 uv run pytest tests/conformance/test_output_format.py

and review the diff (git diff tests/corpus/expected/valid.yaml) before committing.
"""

import hashlib
import json
import os
import re

import jsonschema
import pytest
import yaml

from .support import (
    EXPECTED, PREVIOUS_SCHEMA_PATH, REPO_ROOT, SCHEMA_PATH, VALID, covers,
    corpus_entry_keys, export, item, xfail_owned_entries,
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
    works = {w["bib_id"] for w in data["works"]}
    keys = {c["key"] for c in data["collaborators"]}
    for work in data["works"]:
        for author in work["authors"]:
            assert author["person_id"] in people | {None}, (work["bib_id"], author)
            assert author["collaborator_key"] in keys | {None}, (work["bib_id"], author)
            # Exactly one contributor, which is the `oneOf` the schema states
            # and which is checked here too so it holds of the document even
            # where nothing validates it.
            assert (author["person_id"] is None) != (author["collaborator_key"] is None), \
                (work["bib_id"], author)
        for editor in work["editors"]:
            assert editor["person_id"] in people | {None}, (work["bib_id"], editor)
    for person in data["people"]:
        assert set(person["work_ids"]) <= works, person["id"]
        assert person["work_count"] == len(person["work_ids"])
    for project in data["projects"]:
        assert set(project["work_ids"]) <= works, project["id"]
        assert set(project["people_ids"]) <= people, project["id"]
    positions = {(w["bib_id"], a["position"]) for w in data["works"]
                 for a in w["authors"]}
    for collaborator in data["collaborators"]:
        grouped = [(a["work_id"], a["position"]) for a in collaborator["authorships"]]
        assert set(grouped) <= positions, collaborator["key"]
        assert collaborator["authorship_count"] == len(grouped)
        assert collaborator["work_count"] == len(set(w for w, _ in grouped))
        assert collaborator["work_ids"] == sorted(
            {w for w, _ in grouped}, key=[w for w, _ in grouped].index)
    # Every unresolved authorship is grouped, and every grouping is used.
    referenced = {a["collaborator_key"] for w in data["works"] for a in w["authors"]
                  if a["collaborator_key"]}
    assert referenced == keys


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
    data["works"][0]["surprise"] = True
    assert schema_errors(validator, data)


@covers("output.schema")
def test_schema_rejects_an_authorship_with_two_references_or_none(validator,
                                                                  valid_output):
    """The `oneOf` on the contributor reference is enforced, both ways."""
    for change in ({"person_id": "aadams", "collaborator_key": "k-00000000"},
                   {"person_id": None, "collaborator_key": None}):
        data = json.loads(json.dumps(valid_output))
        data["works"][0]["authors"][0].update(change)
        assert schema_errors(validator, data), change


# The v3 schema as it stood at `78570e6`, the last commit before v4, digested
# byte for byte. "Unchanged" is a claim about bytes, and only bytes can make
# it: a check that v3 still parses and still says `3` stays green while its
# title, its descriptions or any of its constraints are rewritten under a
# consumer that pinned it.
PREVIOUS_SCHEMA_SHA256 = (
    "97f85113822cffb47d36b415716563b50bfe4bf2bc30e892e4cc45b9e377aa92")

# The v4 `$id`, stated here as the literal a consumer would resolve. It is
# served from a tag created when this version ships and never moved (SPEC.md
# section 6), so changing this string is a contract change and has to be a
# deliberate edit in two places.
SCHEMA_ID = ("https://raw.githubusercontent.com/siddhss5/labdata/schema-v4"
             "/schema/v4/output.schema.json")


@covers("output.versioned_schema")
def test_the_previous_schema_stays_reachable_unchanged(validator):
    """v3 is still at its own path, byte for byte, and v4 is a second one.

    A consumer pinned to v3 keeps a stable target only if nothing in the file
    moves, so the assertion is on the digest rather than on any property of
    the parsed document.
    """
    raw = PREVIOUS_SCHEMA_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PREVIOUS_SCHEMA_SHA256

    previous = json.loads(raw.decode("utf-8"))
    jsonschema.Draft202012Validator.check_schema(previous)
    assert previous["properties"]["schema_version"]["const"] == 3
    assert validator.schema["properties"]["schema_version"]["const"] == 4
    # The two are different documents at different paths, not one file read
    # twice.
    assert PREVIOUS_SCHEMA_PATH != SCHEMA_PATH
    assert previous["$id"] != validator.schema["$id"]


@covers("output.versioned_schema")
def test_the_published_id_is_the_string_consumers_resolve(validator):
    """The `$id` is the contract's address, so it is pinned as a literal.

    It names a dedicated tag rather than a branch: a branch URL moves under
    the consumers that resolved it, and `blob/main` serves an HTML page
    rather than the schema at all.
    """
    schema_id = validator.schema["$id"]
    assert schema_id == SCHEMA_ID
    assert "/schema-v4/" in schema_id, schema_id
    assert "/main/" not in schema_id and "/blob/" not in schema_id, schema_id


# --- The two properties the document must have as a whole -------------------

# Markdown emphasis, and an HTML tag. The emphasis pattern is deliberately
# narrow: a lone `*` is not emphasis, which matters because `Informed RRT*`
# and `BIT*` are real paper titles and `Davis*` is a real corpus name.
MARKDOWN_EMPHASIS = re.compile(r"\*[^*\s][^*]*\*")
HTML_TAG = re.compile(r"</?[A-Za-z][^<>]*>")

# The properties whose value the input supplies verbatim. Markdown
# punctuation in one of these is text an author wrote, which SPEC.md section
# 2 says labdata neither escapes nor strips -- the corpus carries `not
# *emphasis*` in a title on purpose. Anywhere else it would be markup labdata
# generated, which is what composing `venue` used to do and what #56 removed.
INPUT_TEXT = {"title", "abstract", "note", "name", "given", "von", "family",
              "suffix", "literal", "name_variants", "description",
              "thesis_title", "current_position", "role", "status",
              "category", "key", "url"}


def markup_paths(data):
    """Every path outside the re-serialized export whose string carries markup.

    The export is skipped because it is the entry re-typeset and still holds
    LaTeX by design (SPEC.md section 5). Everything else is walked to any
    depth, and the path is returned rather than a count, so a failure says
    where the markup is.
    """
    found = []

    def walk(value, path):
        if isinstance(value, dict):
            for name, inner in value.items():
                if name != "bibtex":
                    walk(inner, path + "/" + str(name))
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                walk(inner, path + "/" + str(index))
        elif isinstance(value, str):
            if MARKDOWN_EMPHASIS.search(value) or HTML_TAG.search(value):
                found.append("%s = %r" % (path, value))

    walk(data, "")
    return sorted(found)


def leaf_property(path):
    """The property name a path ends at, skipping list indices."""
    parts = [part for part in path.split("/") if part and not part.isdigit()]
    return parts[-1] if parts else ""


@covers("output.no_markup")
def test_the_demo_document_carries_no_markup(demo_exports):
    """Nothing labdata emits for the demo is Markdown or HTML.

    The demo's input is plain, so any markup in its output would be markup
    labdata generated. Under `schema_version` 3 `venue` was exactly that:
    `*Transactions on Robot Learning*, 4(2), 2025`.
    """
    for data in demo_exports:
        assert markup_paths(data) == []
    # An empty list has to mean "looked and found none": the venue string v3
    # composed must be rejected by the same scan.
    composed = {"works": [{"venue": "*Transactions on Robot Learning*, 4(2), 2025"}]}
    assert markup_paths(composed) != []
    assert markup_paths({"lab": {"name": "<b>Lab</b>"}}) != []


@covers("output.no_markup")
def test_markup_in_the_corpus_is_only_text_the_input_wrote(valid_output):
    """Where the corpus does carry Markdown punctuation, it is input text.

    The corpus writes `[a link](x)`, `# heading` and `*emphasis*` into a
    title on purpose, and SPEC.md section 2 says those are text rather than
    markup. What must never happen is markup in a property labdata composes,
    and that is what this pins.
    """
    found = markup_paths(valid_output)
    assert found != [], "the corpus is supposed to exercise this"
    offenders = [path for path in found
                 if leaf_property(path.split(" = ")[0]) not in INPUT_TEXT]
    assert offenders == []


@covers("output.derived_is_empty")
def test_every_derived_bag_is_empty(valid_output, demo_exports):
    """`derived` is labdata-owned and labdata puts nothing in it yet.

    Asserted so the region cannot quietly fill: a key appearing there is a
    change a reader of this test has to make on purpose.
    """
    def bags(data):
        found = []

        def walk(value, path):
            if isinstance(value, dict):
                if "derived" in value:
                    found.append((path + "/derived", value["derived"]))
                for name, inner in value.items():
                    walk(inner, path + "/" + str(name))
            elif isinstance(value, list):
                for index, inner in enumerate(value):
                    walk(inner, path + "/" + str(index))

        walk(data, "")
        return found

    for data in [valid_output] + list(demo_exports):
        filled = [path for path, bag in bags(data) if bag != {}]
        assert filled == [], filled
    # The walk has to have found the bags it is reporting on.
    assert len(bags(valid_output)) > 100, len(bags(valid_output))


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
    "works": [
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
    "collaborators": ["Quentin Quinn", "Rachel Ross"],
}
KEYS = {"works": "bib_id", "people": "id", "projects": "id", "collaborators": "name"}


def select(data):
    """The part of the output the snapshot owns, in the order SNAPSHOT lists."""
    chosen = {"schema_version": data["schema_version"],
              "generator": data["generator"], "lab": data["lab"]}
    for section, wanted in SNAPSHOT.items():
        chosen[section] = [item(data, section, KEYS[section], value) for value in wanted]
    return chosen


def test_snapshot_avoids_xfailed_cases(valid_output):
    """Nothing in the snapshot is owned by an open issue's xfail.

    Ownership is declared by the xfailed case() and covers() calls themselves
    (support.XFAIL_OWNERSHIP). A publication an open issue owns, and anything
    whose value is derived from one, stays out: otherwise a fix would break
    the snapshot and the tempting way out would be to re-record the behavior
    the xfail rejects.
    """
    bib_ids = {w["bib_id"] for w in valid_output["works"]}
    excluded = bib_ids & xfail_owned_entries()
    assert excluded, "expected some xfailed entries to exclude"

    chosen = select(valid_output)
    assert [w["bib_id"] for w in chosen["works"] if w["bib_id"] in excluded] == []
    for section in ("people", "projects"):
        for entry in chosen[section]:
            overlap = sorted(set(entry["work_ids"]) & excluded)
            assert overlap == [], f"{section} {entry['id']} depends on {overlap}"
    for collaborator in chosen["collaborators"]:
        grouped = {a["work_id"] for a in collaborator["authorships"]}
        assert sorted(grouped & excluded) == [], collaborator["name"]


def test_xfail_ownership_names_real_entries():
    """A typo in owns= would quietly exclude nothing, so reject it here."""
    unknown = sorted(xfail_owned_entries() - corpus_entry_keys())
    assert unknown == [], f"owns= names entries that are in no .bib: {unknown}"


def test_xfail_without_declared_ownership_is_an_error():
    """An xfailed covers() that forgets owns= fails loudly, not silently."""
    # Called through a local name: this exercises the decorator's contract and
    # is not a claim to cover a case, which is what a literal covers(...) call
    # would mean to tests/COVERAGE.md.
    declare = covers
    with pytest.raises(TypeError):
        declare("example.not_a_real_case", xfail="#23")
    # Declaring no ownership is fine; only leaving it out is an error.
    assert declare("example.not_a_real_case", xfail="#23", owns=()) is not None


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
