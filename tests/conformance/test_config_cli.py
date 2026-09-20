"""Config keys and CLI flags, run on the valid corpus and variants of its lab.yaml.

Wrong-typed and otherwise invalid config lives in tests/corpus/invalid/ and is
checked by test_invalid_corpus.py.
"""

import json

import pytest
import yaml

from .support import VALID, case, covers, export, item, publication, run_labdata, write_variant


# --- Config keys: present ----------------------------------------------------

@covers("config.lab.present", "config.bib_dir.present", "config.bib_files.present",
        "config.site")
def test_config_present(valid_output):
    assert valid_output["lab"]["name"] == "Corpus Lab"
    categories = {p["category"] for p in valid_output["publications"]}
    assert categories == {"Strings", "Names", "LaTeX", "Structure", "Encoding", "Links",
                          "Projects"}
    # site is for scripts/generate_site_config.py; labdata accepts it and
    # does not copy it into the output.
    assert "site" not in valid_output


@covers("config.pdf_base_url.present")
def test_config_pdf_base_url_present(valid_output):
    assert "present.pdf" in publication(valid_output, "present")["pdf_url"]


@covers("config.people_file.present")
def test_config_people_file_present(valid_output):
    assert len(valid_output["people"]) == 12
    assert publication(valid_output, "name-last-first")["authors"][0]["person_id"] == "aadams"


@covers("config.projects_file.present")
def test_config_projects_file_present(valid_output):
    assert [p["id"] for p in valid_output["projects"]] == ["homebot", "sharedarm"]


# --- Config keys: missing (optional keys) ------------------------------------

@covers("config.lab.missing")
def test_config_lab_missing(tmp_path):
    run, data = export(VALID, tmp_path, write_variant(tmp_path, lab=None))
    assert run.code == 0 and run.crash is None, run.output
    assert "lab" not in data


@covers("config.pdf_base_url.missing")
def test_config_pdf_base_url_missing(tmp_path):
    run, data = export(VALID, tmp_path, write_variant(tmp_path, pdf_base_url=None))
    assert run.code == 0 and run.crash is None, run.output
    assert [p["pdf_url"] for p in data["publications"] if p["pdf_url"]] == []


@covers("config.people_file.missing")
def test_config_people_file_missing(tmp_path):
    run, data = export(VALID, tmp_path, write_variant(tmp_path, people_file=None))
    assert run.code == 0 and run.crash is None, run.output
    assert data["people"] == []
    assert {a["person_id"] for p in data["publications"] for a in p["authors"]} == {None}
    assert item(data, "collaborators", "name", "A. Adams")["publication_count"] > 1


@covers("config.people_file.missing", xfail="#22", owns=())
def test_unresolved_without_people_file(tmp_path):
    """--unresolved says author resolution is not configured, naming people_file."""
    run = run_labdata(["--config", write_variant(tmp_path, people_file=None), "--unresolved"],
                      VALID)
    assert "people_file" in run.output


@covers("config.projects_file.missing")
def test_config_projects_file_missing(tmp_path):
    run, data = export(VALID, tmp_path, write_variant(tmp_path, projects_file=None))
    assert run.code == 0 and run.crash is None, run.output
    assert data["projects"] == []
    # Project tags on publications are kept.
    assert publication(data, "proj-multiple")["project_ids"] == ["homebot", "sharedarm"]


# --- Links that depend on config --------------------------------------------

@covers("links.pdf.remote_guess", xfail="#20", owns=("missing",))
def test_remote_pdf_url_not_guessed(tmp_path):
    """A remote pdf_base_url gives a PDF link only for papers known to have a PDF."""
    variant = write_variant(tmp_path, pdf_base_url="https://example.org/pdfs")
    run, data = export(VALID, tmp_path, variant)
    assert run.code == 0 and run.crash is None, run.output
    assert publication(data, "missing")["pdf_url"] is None


# --- CLI flags and output formats --------------------------------------------

@covers("cli.config")
def test_cli_config_required():
    run = run_labdata(["--validate"], VALID)
    assert run.crash is None
    assert run.code == 2
    assert "--config" in run.stderr


@covers("cli.config_not_found", "diag.config_not_found")
def test_cli_config_not_found():
    run = run_labdata(["--config", "no-such-lab.yaml", "--validate"], VALID)
    assert run.crash is None
    assert run.code == 1
    assert "no-such-lab.yaml" in run.stderr


@covers("cli.mode.required", "diag.mode_required")
def test_cli_mode_required():
    run = run_labdata(["--config", "lab.yaml"], VALID)
    assert run.crash is None
    assert run.code == 2
    for flag in ("--output", "--validate", "--unresolved"):
        assert flag in run.stderr


@covers("cli.help")
def test_cli_help():
    run = run_labdata(["--help"], VALID)
    assert run.code == 0
    for flag in ("--config", "--format", "--output", "--validate", "--unresolved"):
        assert flag in run.stdout


FORMATS = [
    case("cli.format.yaml", ["--format", "yaml"], yaml.safe_load),
    case("cli.format.yaml", [], yaml.safe_load),  # the default
    case("cli.format.json", ["--format", "json"], json.loads),
]


@pytest.mark.parametrize("case_id, args, parse", FORMATS)
def test_cli_format(tmp_path, valid_output, case_id, args, parse):
    out = tmp_path / "lab.out"
    run = run_labdata(["--config", "lab.yaml", *args, "--output", out], VALID)
    assert run.code == 0 and run.crash is None, run.output
    assert parse(out.read_text(encoding="utf-8")) == valid_output


@covers("cli.format.invalid", "diag.format_invalid")
def test_cli_format_invalid(tmp_path):
    run = run_labdata(["--config", "lab.yaml", "--format", "xml", "--output",
                       tmp_path / "lab.xml"], VALID)
    assert run.code == 2
    assert "xml" in run.stderr
    assert not (tmp_path / "lab.xml").exists()


@covers("cli.output", "diag.wrote")
def test_cli_output_creates_parent_dirs(tmp_path, valid_output):
    out = tmp_path / "site" / "_data" / "lab.yml"
    run = run_labdata(["--config", "lab.yaml", "--output", out], VALID)
    assert run.code == 0 and run.crash is None, run.output
    assert out.exists()
    assert str(out) in run.stdout
    assert str(len(valid_output["publications"])) in run.stdout


@covers("cli.validate", "diag.unresolved_authors")
def test_cli_validate(valid_validate, valid_output):
    assert valid_validate.crash is None
    assert valid_validate.code == 0, valid_validate.output
    # Counts, and unresolved external authors, which are not errors.
    for section in ("publications", "people", "projects"):
        assert str(len(valid_output[section])) in valid_validate.stdout
    assert "Q. Quinn" in valid_validate.stdout


@covers("diag.validation_passed")
def test_cli_validate_closes_with_a_summary_line(valid_validate, valid_output):
    """A passing --validate ends with a line of its own, after the counts.

    Checked by shape rather than by wording: the closing line is not indented
    like a listed name, and is not one of the count lines.
    """
    assert valid_validate.code == 0, valid_validate.output
    lines = [line for line in valid_validate.stdout.splitlines() if line.strip()]
    counts = {str(len(valid_output[s])) for s in ("publications", "people", "projects")}
    closing = lines[-1]
    assert not closing.startswith(" "), closing
    assert not any(count in closing for count in counts), closing
    assert closing not in lines[:-1], closing


@covers("cli.unresolved", "diag.unresolved_authors")
def test_cli_unresolved(valid_unresolved, valid_output):
    assert valid_unresolved.crash is None
    assert valid_unresolved.code == 0
    listed = {c["name"] for c in valid_output["collaborators"]}
    for name in listed:
        assert name in valid_unresolved.stdout
    assert "A. Adams" not in valid_unresolved.stdout


@covers("cli.unresolved_none", "diag.all_resolved")
def test_cli_unresolved_none(tmp_path):
    """Every author resolves: labdata says so in one line and lists nobody."""
    variant = write_variant(tmp_path, bib_files=[{"name": "encoding.bib", "category": "E"}])
    run = run_labdata(["--config", variant, "--unresolved"], VALID)
    assert run.code == 0 and run.crash is None, run.output
    lines = [line for line in run.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, run.stdout
    assert not lines[0].startswith(" "), run.stdout
    for name in ("Adams", "Côté"):
        assert name not in run.stdout
