"""Diagnostics for the invalid corpus (tests/corpus/invalid/<dir>/).

Each case in tests/corpus/expected/diagnostics.yaml is run in its own folder,
so one broken input cannot hide another. Checks look at the exit status and
at tokens (file, entry key, field, value) in sslabdata's output, never at exact
wording or at parser-library messages.
"""

import json
import shutil

import pytest
import yaml

from sslabdata import (
    AssemblyError, ConfigurationError, LabData, LabDataConfig, assemble,
)

from .support import (
    EXPECTED, INVALID, case, export, item, run_sslabdata, working_dir,
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
        # raises: a row that breaks before its assertion fails rather than xfails.
        marks = [pytest.mark.xfail(strict=True, reason=issue,
                                   raises=AssertionError)] if issue else []
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
# Covers structure.duplicate_key_file, structure.duplicate_key_across,
# diag.duplicate_citation_key
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


# Covers config.bib_files.name_absolute
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


OUTSIDE = INVALID / "config_bib_file_outside"

# Names that leave bib_dir by their spelling alone. The backslash and drive
# forms are rejected on every host, so Linux CI exercises the Windows syntax
# rules (not the Windows filesystem).
LEAVING_BY_SPELLING = ["../outside.bib", "../../outside.bib", "sub/../../outside.bib",
                       "..\\outside.bib", "sub\\..\\..\\outside.bib", "C:outside.bib"]
# Names that are spelt inside bib_dir and leave it through a symlink there:
# to a file, to a sibling directory whose name begins with "bib", to nothing,
# and to the directory above.
SYMLINKS = {"link.bib": "../outside.bib", "lookalike.bib": "../bib_evil/x.bib",
            "dangling.bib": "../missing.bib", "up": ".."}
LEAVING_BY_SYMLINK = ["link.bib", "lookalike.bib", "dangling.bib", "up/outside.bib"]


def outside_tree(tmp_path, names):
    """The outside-bib_dir fixture, copied, with `crossref.bib` then `names`
    listed as its bib_files and the symlinks above made in bib_dir."""
    where = tmp_path / "case"
    shutil.copytree(OUTSIDE, where)
    config = yaml.safe_load((where / "lab.yaml").read_text(encoding="utf-8"))
    config["bib_files"] = [{"name": n, "category": "Papers"}
                           for n in ["crossref.bib", *names]]
    (where / "lab.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    for link, target in SYMLINKS.items():
        try:
            (where / "bib" / link).symlink_to(target, target_is_directory=link == "up")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks cannot be created here")
    return where


# Covers config.bib_files.name_outside_bib_dir
@pytest.mark.parametrize("name", LEAVING_BY_SPELLING + LEAVING_BY_SYMLINK)
def test_a_name_outside_bib_dir_is_rejected_before_anything_is_parsed(tmp_path, name):
    """A name that leaves bib_dir is a coded error, in every mode, with nothing written.

    `crossref.bib`, listed first, is fatal if it is read: the error being the
    only one reported shows the whole configuration was checked before any
    file was parsed. To reproduce one case, run `sslabdata --config lab.yaml
    --validate` in tests/corpus/invalid/config_bib_file_outside (`../outside.bib`).
    """
    where = outside_tree(tmp_path, [name])
    out = tmp_path / "written" / "lab.json"
    out.parent.mkdir()
    for args in (["--validate"], ["--format", "json", "--output", out]):
        run = run_sslabdata(["--config", "lab.yaml", *args], where)
        assert run.crash is None, (args, run.crash)
        assert run.code == 1 and run.stdout == "", (args, run.output)
        assert run.stderr.startswith("Error loading configuration: "), run.stderr
        assert "CONFIG-BIB-FILE-OUTSIDE-BIB-DIR lab.yaml:bib_files:name: " in run.stderr
        assert f"'{name}'" in run.stderr
        assert "BIB-CROSSREF-UNSUPPORTED" not in run.output, "a file was parsed"
    assert list(out.parent.iterdir()) == [], "something was written despite the error"


# Covers config.bib_files.name_outside_bib_dir
def test_a_nested_name_under_bib_dir_is_accepted_and_emitted_as_written(tmp_path):
    """The document is the artifact: `works[].source.file` is `conference/2026.bib`.
    To reproduce, list that name in the fixture's lab.yaml and run
    `sslabdata --config lab.yaml --output lab.json`."""
    where = outside_tree(tmp_path, [])
    config = yaml.safe_load((where / "lab.yaml").read_text(encoding="utf-8"))
    config["bib_files"] = [{"name": "conference/2026.bib", "category": "Papers"}]
    (where / "lab.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    run, data = export(where, tmp_path)
    assert run.code == 0 and run.crash is None, run.output
    assert [w["source"]["file"] for w in data["works"]] == ["conference/2026.bib"]


# Covers structure.crossref
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


# Covers latex.unknown_macro
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


# Covers records.unknown_key
def test_an_unknown_record_key_is_located(tmp_path):
    """One key in each file, each a warning at the file, the record and the
    key, and an error under `--strict`; no key is emitted."""
    where = INVALID / DIAGNOSTICS["records.unknown_key"]["dir"]
    located = [("people.yaml", "aadams", "webiste"),
               ("projects.yaml", "homebot", "funding"),
               ("collaborators.yaml", "Priya Patel", "affiliation")]
    for strict, level, code in (((), "warning", 0),
                                (("--strict",), "error", 1)):
        run = run_sslabdata(["--config", "lab.yaml", "--validate", *strict,
                             "--format", "json"], where)
        assert run.crash is None and run.code == code, run.output
        records = [(r["code"], r["severity"], r["file"], r["key"], r["field"])
                   for r in json.loads(run.stdout)]
        assert records == [("RECORD-KEY-UNKNOWN", level, *location)
                           for location in located], records
    run, data = export(where, tmp_path)
    assert run.code == 0, run.output
    assert not [key for _, _, key in located if key in json.dumps(data)]


# Covers records.required_type_invalid
def test_a_required_field_that_is_not_a_string_is_fatal_and_located(tmp_path):
    """An `id`, `name` or `title` is never coerced: a number, a list or a
    boolean makes the record unusable, one located error per file, no
    traceback and no document.

    To inspect: `diagnostics.json` in the test's tmp directory is the
    `--validate --format json` report; rerun the command in
    tests/corpus/invalid/record_id_types to reproduce it.
    """
    where = INVALID / DIAGNOSTICS["records.required_type_invalid"]["dir"]
    run = run_sslabdata(["--config", "lab.yaml", "--validate", "--format", "json"], where)
    (tmp_path / "diagnostics.json").write_text(run.stdout, encoding="utf-8")
    assert run.crash is None and run.code == 1 and run.stderr == "", run.output
    assert [(r["code"], r["file"], r["key"], r["field"], r["severity"])
            for r in json.loads(run.stdout)] == [
        ("PEOPLE-FIELD-MISSING", "people.yaml", None, "id", "error"),
        ("PEOPLE-FIELD-MISSING", "people.yaml", "bbrown", "name", "error"),
        ("PROJECTS-FIELD-MISSING", "projects.yaml", None, "id", "error"),
        ("COLLABORATORS-FIELD-MISSING", "collaborators.yaml", None, "name", "error"),
    ]
    out = tmp_path / "lab.json"
    run = run_sslabdata(["--config", "lab.yaml", "--output", out], where)
    assert run.crash is None and run.code == 1, run.output
    assert not out.exists(), "a document was written despite a fatal diagnostic"


# Covers records.optional_type_invalid
def test_an_optional_field_of_the_wrong_type_is_reported_and_emitted_as_null(tmp_path):
    """Each wrong-typed optional field is one located warning and a null in
    the document (a status that is not a string reads as the default, and
    the aliases that are not a list of strings declare none); the record
    is kept. The document is `lab.json` in the test's tmp directory, and
    `sslabdata --config lab.yaml --format json --output lab.json` in
    tests/corpus/invalid/record_field_types writes the same bytes.
    """
    where = INVALID / DIAGNOSTICS["records.optional_type_invalid"]["dir"]
    run = run_sslabdata(["--config", "lab.yaml", "--validate", "--format", "json"], where)
    assert run.crash is None and run.code == 0, run.output
    assert sorted((r["code"], r["severity"], r["file"], r["key"], r["field"])
                  for r in json.loads(run.stdout)) == sorted(
        [("RECORD-TYPE-INVALID", "warning", "people.yaml", key, field)
         for key, field in (("aadams", "photo"), ("aadams", "website"),
                            ("aadams", "start_year"), ("aadams", "aliases"),
                            ("bbrown", "email"), ("bbrown", "end_year"),
                            ("bbrown", "aliases"))]
        + [("RECORD-TYPE-INVALID", "warning", "projects.yaml", "homebot", field)
           for field in ("description", "website", "image")]
        + [("RECORD-TYPE-INVALID", "warning", "collaborators.yaml", "Priya Patel",
            "aliases"),
           ("PEOPLE-STATUS-INVALID", "warning", "people.yaml", "aadams", "status"),
           ("PROJECTS-STATUS-INVALID", "warning", "projects.yaml", "homebot", "status")])
    run, data = export(where, tmp_path)
    assert run.crash is None and run.code == 0, run.output
    aadams, bbrown = item(data, "people", "id", "aadams"), item(data, "people", "id", "bbrown")
    assert (aadams["status"], aadams["role"]) == ("current", "professor")
    assert [aadams[f] for f in ("photo", "website", "start_year")] == [None] * 3
    assert [bbrown[f] for f in ("email", "end_year")] == [None] * 2
    homebot = item(data, "projects", "id", "homebot")
    assert homebot["status"] == "active"
    assert [homebot[f] for f in ("description", "website", "image")] == [None] * 3


def test_an_input_file_the_system_will_not_open_is_coded_not_a_traceback(tmp_path):
    """The one read failure the loaders leave to the CLI: a people file that
    exists but cannot be opened. Coded `CONFIG-UNREADABLE`, naming the file
    in the system's words, exit 1, nothing written.
    """
    where = tmp_path / "case"
    shutil.copytree(INVALID / "record_unknown_key", where)
    people = where / "people.yaml"
    people.chmod(0)
    try:
        people.read_bytes()
    except OSError:
        pass
    else:
        pytest.skip("this account can read a file with no permissions")
    try:
        out = tmp_path / "lab.json"
        run = run_sslabdata(["--config", "lab.yaml", "--output", out], where)
    finally:
        people.chmod(0o644)
    assert run.crash is None and run.code == 1, run.output
    assert run.stderr.startswith("Error loading configuration: CONFIG-UNREADABLE lab.yaml::: "), run.stderr
    assert "people.yaml" in run.stderr
    assert not out.exists()


# Covers latex.text_macros
def test_common_text_macros_are_converted(tmp_path):
    """Each macro becomes its text, and none is reported as unknown."""
    where = INVALID / DIAGNOSTICS["latex.text_macros"]["dir"]
    run, data = export(where, tmp_path)
    assert run.crash is None and "LATEX-COMMAND-UNKNOWN" not in run.stderr, run.output
    [work] = data["works"]
    assert work["title"] == "The TeX book 1990\u20142000"
    assert work["note"] == "Typeset with LaTeX and BibTeX, pages 1\u20132, read/write"


# Covers latex.unknown_macro_repeated
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


# Covers identity.ambiguous_alias
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


# The cases whose configuration loads and whose assembly finds a fatal code.
FATAL = ["bib_file_not_found", "bib_not_utf8", "collaborators_file_not_found",
         "collaborators_invalid_yaml", "crossref_entry", "crossref_no_parent",
         "crossref_undefined_parent", "people_file_not_found",
         "people_invalid_yaml", "people_missing_name", "people_not_a_list",
         "projects_file_not_found", "projects_invalid_yaml",
         "projects_missing_id", "record_id_types"]


def loads(name):
    """True when the case's configuration loads, so `assemble()` is reached."""
    with working_dir(INVALID / name):
        try:
            LabDataConfig.from_yaml("lab.yaml")
        except ConfigurationError:
            return False
    return True


def assembled(name, diagnostics):
    with working_dir(INVALID / name):
        return assemble(LabDataConfig.from_yaml("lab.yaml"),
                        diagnostics=diagnostics)


@pytest.mark.parametrize("name", FATAL)
def test_the_python_api_returns_no_document_on_a_fatal_diagnostic(name, capsys):
    """Whatever `diagnostics` is: it decides printing, never compiling. With
    False every diagnostic is printed first, fatal ones included."""
    for diagnostics in (False, True):
        with pytest.raises(AssemblyError) as raised:
            assembled(name, diagnostics)
        printed = "".join(f"Warning: {line}\n" for line in raised.value.diagnostics)
        assert capsys.readouterr().err == ("" if diagnostics else printed)


@pytest.mark.parametrize("name", sorted(
    d.name for d in INVALID.iterdir()
    if d.is_dir() and d.name not in FATAL and loads(d.name)))
def test_the_python_api_returns_a_document_otherwise(name):
    """A validation error, such as a repeated citation key, still returns a
    document, as `--output` still writes one."""
    assert isinstance(assembled(name, False), LabData)
