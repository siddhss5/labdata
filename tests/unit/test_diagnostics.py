"""The code classes, and the three adapter codes only a fault can reach."""

import re

from labdata.diagnostics import CLASSES, NEVER_AN_ERROR

from ..conformance.support import REPO_ROOT
from ..test_strict_json import (
    CODE, json_run, spec_classes, spec_never_an_error, spec_registry, write_lab,
)


def test_the_code_classes_are_the_ones_spec_states():
    assert spec_registry() == set(CLASSES)
    assert spec_classes() == CLASSES
    assert spec_never_an_error() == NEVER_AN_ERROR
    assert NEVER_AN_ERROR <= set(CLASSES)


def test_every_code_the_source_names_is_classified():
    named = set()
    for path in (REPO_ROOT / "labdata").rglob("*.py"):
        named |= set(re.findall(rf'"({CODE})"', path.read_text(encoding="utf-8")))
    assert named and named - set(CLASSES) == set()


def test_a_field_whose_latex_cannot_be_read_is_located(tmp_path, monkeypatch):
    import labdata.parsers.bibtex as bibtex

    def unreadable(value):
        if "Broken" in value:
            raise ValueError("cannot read")
        return value
    monkeypatch.setattr(bibtex, "latex_to_text", unreadable)
    write_lab(tmp_path, "@article{e, title = {Broken {Title}}, journal = {J},"
                        " year = 2024}\n")
    run, [record] = json_run(tmp_path, "--validate", "--strict")
    assert (record["code"], record["file"], record["key"], record["field"]) == (
        "LATEX-CONVERSION-FAILED", "./w.bib", "e", "title")
    assert record["severity"] == "error" and run.code == 1


def test_an_entry_that_cannot_be_written_back_is_located(tmp_path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise ValueError("cannot write")
    monkeypatch.setattr("labdata.parsers.bibtex.Entry.to_string", refuse)
    write_lab(tmp_path, "@article{e, title = {T}, journal = {J}, year = 2024}\n")
    run, [record] = json_run(tmp_path, "--validate")
    assert (record["code"], record["file"], record["key"], record["field"]) == (
        "BIB-WRITE-BACK-FAILED", "./w.bib", "e", "bibtex")
    assert run.code == 0
