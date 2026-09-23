"""Diagnostics for the invalid corpus (tests/corpus/invalid/<dir>/).

Each case in tests/corpus/expected/diagnostics.yaml is run in its own folder,
so one broken input cannot hide another. Checks look at the exit status and
at tokens (file, entry key, field, value) in sslabdata's output, never at exact
wording or at parser-library messages.
"""

import json

import pytest
import yaml

from .support import (
    EXPECTED, EXPECTED_FAILURE, INVALID, case, covers, export, run_sslabdata,
)

with open(EXPECTED / "diagnostics.yaml", encoding="utf-8") as f:
    DIAGNOSTICS = yaml.safe_load(f)

CHECKS = ("exit", "reports", "locates", "kept")


def params(check):
    rows = []
    for case_id, spec in DIAGNOSTICS.items():
        if check not in spec:
            continue
        issue = spec.get("xfail", {}).get(check)
        # `raises` is not decoration: it is what stops a marked row that
        # breaks before its own assertion from being counted as expected.
        marks = [pytest.mark.xfail(strict=True, reason=issue,
                                   raises=EXPECTED_FAILURE)] if issue else []
        rows.append(pytest.param(case_id, spec, id=case_id, marks=marks))
    return rows


def validate(spec):
    return run_sslabdata(["--config", "lab.yaml", "--validate"], INVALID / spec["dir"])


@pytest.mark.parametrize("case_id, spec", params("exit"))
def test_exit(case_id, spec):
    run = validate(spec)
    assert run.crash is None, f"sslabdata crashed: {run.crash}"
    if spec["exit"] == "error":
        assert run.code != 0, run.output
        assert run.output.strip(), "exited non-zero without a message"
    elif spec["exit"] == "ok":
        assert run.code == 0, run.output


@pytest.mark.parametrize("case_id, spec", params("reports"))
def test_reports(case_id, spec):
    run = validate(spec)
    missing = [t for t in spec["reports"] if t not in run.output]
    assert not missing, f"output does not name {missing}:\n{run.output}"


@pytest.mark.parametrize("case_id, spec", params("locates"))
def test_locates(case_id, spec):
    run = validate(spec)
    missing = [t for t in spec["locates"] if t not in run.output]
    assert not missing, f"output does not locate {missing}:\n{run.output}"


@pytest.mark.parametrize(
    "case_id",
    ("structure.duplicate_key_file", "structure.duplicate_key_across"),
)
@covers("structure.duplicate_key_file", "structure.duplicate_key_across",
        "diag.duplicate_citation_key")
def test_duplicate_keys_warn_but_do_not_block_nonvalidation_modes(tmp_path, case_id):
    """Exports and author reports stay available while naming malformed input."""
    spec = DIAGNOSTICS[case_id]
    unresolved = run_sslabdata(["--config", "lab.yaml", "--unresolved"],
                              INVALID / spec["dir"])
    assert unresolved.code == 0 and unresolved.crash is None, unresolved.output
    assert "BIB-DUPLICATE-KEY" in unresolved.stderr

    run, data = export(INVALID / spec["dir"], tmp_path)
    assert run.code == 0 and run.crash is None, run.output
    assert "BIB-DUPLICATE-KEY" in run.stderr
    assert data is not None


@covers("config.bib_files.name_absolute")
def test_a_fatal_at_load_code_goes_to_standard_error_in_every_mode(tmp_path):
    """The one shape that carries a code inside another one.

    Nothing is assembled, so there is no `--validate` report to gather the
    diagnostic into and it cannot be on standard output the way an
    assembly-time code is. It is on standard error, after the
    `Error loading configuration: ` prefix, in every mode -- which is why
    SPEC.md tells a consumer to search a line for a code rather than anchor
    at its start.
    """
    where = INVALID / DIAGNOSTICS["config.bib_files.name_absolute"]["dir"]
    out = tmp_path / "lab.json"
    for args in (["--validate"],
                 ["--unresolved"],
                 ["--format", "json", "--output", out]):
        run = run_sslabdata(["--config", "lab.yaml", *args], where)
        assert run.crash is None, (args, run.crash)
        assert run.code == 1, (args, run.output)
        assert "CONFIG-BIB-FILE-ABSOLUTE" in run.stderr, (args, run.output)
        assert "CONFIG-BIB-FILE-ABSOLUTE" not in run.stdout, (args, run.output)
        assert run.stderr.startswith("Error loading configuration: "), run.stderr
    assert not out.exists(), "a document was written despite a fatal diagnostic"


@covers("structure.crossref")
def test_a_fatal_diagnostic_stops_a_normal_compile(tmp_path):
    """A user cannot produce a document by skipping --validate.

    The error is reachable from a normal compile as well, and nothing is
    written: an exit code nobody reads and a file that exists anyway is the
    silent path #65 removed, one step further along.
    """
    out = tmp_path / "lab.json"
    run = run_sslabdata(["--config", "lab.yaml", "--format", "json", "--output", out],
                      INVALID / DIAGNOSTICS["structure.crossref"]["dir"])
    assert run.crash is None, run.crash
    assert run.code != 0, run.output
    assert "BIB-CROSSREF-UNSUPPORTED" in run.output
    assert not out.exists(), "a document was written despite a fatal diagnostic"


@pytest.mark.parametrize("case_id, spec", params("kept"))
def test_kept(tmp_path, case_id, spec):
    run, data = export(INVALID / spec["dir"], tmp_path)
    assert run.crash is None, f"sslabdata crashed: {run.crash}"
    assert data is not None, run.output
    keys = [w["bib_id"] for w in data["works"]]
    missing = [k for k in spec["kept"] if k not in keys]
    assert not missing, f"entries dropped: {missing}"


@covers("latex.unknown_macro")
def test_unknown_macro_keeps_its_text(tmp_path):
    """The macro's argument survives and no raw LaTeX reaches the output."""
    run, data = export(INVALID / DIAGNOSTICS["latex.unknown_macro"]["dir"], tmp_path)
    assert run.crash is None, run.crash
    title = next(w["title"] for w in data["works"] if w["bib_id"] == "unknown-macro")
    assert "Strange" in title
    assert "\\" not in title, title


@pytest.mark.parametrize("case_id, code, location", [
    case("structure.not_utf8", "BIB-ENCODING-INVALID", ("./latin1.bib", None, None)),
    case("people.invalid_yaml", "PEOPLE-YAML-INVALID", ("people.yaml", None, None)),
    case("projects.invalid_yaml", "PROJECTS-YAML-INVALID", ("projects.yaml", None, None)),
    case("collaborators.invalid_yaml", "COLLABORATORS-YAML-INVALID",
         ("collaborators.yaml", None, None)),
    case("projects.missing_id", "PROJECTS-FIELD-MISSING", ("projects.yaml", None, "id")),
    case("config.collaborators_file.not_found", "CONFIG-FILE-NOT-FOUND",
         ("lab.yaml", "collaborators_file", None)),
    case("config.collaborators_file.wrong_type", "CONFIG-TYPE-INVALID",
         ("lab.yaml", "collaborators_file", None)),
])
def test_malformed_input_is_fatal_and_coded(tmp_path, case_id, code, location):
    """No traceback; one coded, located record in JSON; nothing written."""
    where = INVALID / DIAGNOSTICS[case_id]["dir"]
    run = run_sslabdata(["--config", "lab.yaml", "--validate", "--format", "json"], where)
    assert run.crash is None and run.code == 1 and run.stderr == "", run.output
    records = [r for r in json.loads(run.stdout) if r["severity"] == "error"]
    assert [(r["code"], (r["file"], r["key"], r["field"])) for r in records] == [
        (code, location)], records
    out = tmp_path / "lab.json"
    run = run_sslabdata(["--config", "lab.yaml", "--output", out], where)
    assert run.crash is None and run.code == 1 and code in run.stderr, run.output
    assert not out.exists(), "a document was written despite a fatal diagnostic"


@covers("latex.text_macros")
def test_common_text_macros_are_converted(tmp_path):
    """Each macro becomes its text, and none is reported as unknown."""
    where = INVALID / DIAGNOSTICS["latex.text_macros"]["dir"]
    run, data = export(where, tmp_path)
    assert run.crash is None and "LATEX-COMMAND-UNKNOWN" not in run.stderr, run.output
    [work] = data["works"]
    assert work["title"] == "The TeX book 1990\u20142000"
    assert work["note"] == "Typeset with LaTeX and BibTeX, pages 1\u20132, read/write"


@covers("latex.unknown_macro_repeated")
def test_an_unknown_macro_is_one_line_per_run(tmp_path):
    """Three fields use the macro; one line reports it, at the first."""
    where = INVALID / DIAGNOSTICS["latex.unknown_macro_repeated"]["dir"]
    run = run_sslabdata(["--config", "lab.yaml", "--validate", "--format", "json"], where)
    assert run.crash is None, run.crash
    [line] = [r for r in json.loads(run.stdout) if r["code"] == "LATEX-COMMAND-UNKNOWN"]
    assert (line["file"], line["key"], line["field"]) == ("./macro.bib", "first-use", "title")
    assert "\\fictionalmacro" in line["message"] and "3 fields" in line["message"]


def test_spec_is_well_formed():
    for case_id, spec in DIAGNOSTICS.items():
        assert (INVALID / spec["dir"] / "lab.yaml").is_file(), case_id
        assert spec["exit"] in ("error", "ok", "any"), case_id
        assert set(spec) <= {"dir", "xfail", *CHECKS}, case_id
        assert set(spec.get("xfail", {})) <= set(CHECKS) & set(spec), case_id
    dirs = {spec["dir"] for spec in DIAGNOSTICS.values()}
    assert dirs == {d.name for d in INVALID.iterdir() if d.is_dir()}


@covers("identity.ambiguous_alias")
def test_an_alias_two_people_declare_resolves_to_neither(tmp_path):
    """The name both people declare is linked to nobody and says why."""
    run, data = export(INVALID / DIAGNOSTICS["identity.ambiguous_alias"]["dir"],
                       tmp_path)
    assert run.crash is None and data is not None, run.output
    work = next(w for w in data["works"] if w["bib_id"] == "brown-initial")
    [author] = work["authors"]
    assert author["person_id"] is None, author
    assert author["resolution"]["status"] == "ambiguous", author
    assert "PEOPLE-ALIAS-AMBIGUOUS" in run.stderr
