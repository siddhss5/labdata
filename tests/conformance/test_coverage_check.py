"""Negative controls for coverage_check.validate().

Each test builds a tiny tree — one table row, one fixture, one test module —
in tmp_path, breaks exactly one thing, and checks that the validator says so.
Without these, the meta-test could quietly stop enforcing anything.
"""

import textwrap

import pytest

from .coverage_check import validate

HEADER = ("| Case | Input | Expected | Fixture | Test | Status |\n"
          "|---|---|---|---|---|---|\n")


def build(tmp_path, *, marker=True, assertion=True, named_function="test_demo",
          row_test="test_demo.py::test_demo", status="pass", xfail=None,
          row=True, fixture="corpus/valid/demo.bib"):
    """A minimal tree for one case, ``names.demo``, with one thing optionally off."""
    corpus = tmp_path / "corpus" / "valid"
    corpus.mkdir(parents=True, exist_ok=True)
    body = "    assert True\n" if assertion else "    pass\n"
    (corpus / "demo.bib").write_text(
        ("% CASE names.demo\n" if marker else "") + "@article{demo,\n  year = {2024}\n}\n",
        encoding="utf-8")

    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    xfail_arg = f', xfail="{xfail}"' if xfail else ""
    module = textwrap.dedent(f"""
        from .support import covers


        @covers("names.demo"{xfail_arg})
        def {named_function}():
        {{body}}

        def test_demo():
        {{body}}
    """).replace("{body}", body.rstrip("\n"))
    if named_function == "test_demo":       # only one function in the usual case
        module = module.split("def test_demo():")[0] + f"def test_demo():\n{body}"
    (tests / "test_demo.py").write_text(module, encoding="utf-8")

    table = tmp_path / "COVERAGE.md"
    line = (f"| `names.demo` | an entry | read | `{fixture}` | "
            f"`{row_test}` | {status} |\n") if row else ""
    table.write_text(HEADER + line, encoding="utf-8")
    return dict(table=table, corpus_dir=tmp_path / "corpus", tests_dir=tests,
                repo_root=tmp_path)


def categories(tmp_path, **kwargs):
    return sorted({p.category for p in validate(**build(tmp_path, **kwargs))})


def test_accepts_a_well_formed_row(tmp_path):
    assert validate(**build(tmp_path)) == []


def test_rejects_a_fixture_without_the_case_marker(tmp_path):
    assert categories(tmp_path, marker=False) == ["fixture"]


def test_rejects_a_named_test_with_no_assertion(tmp_path):
    assert categories(tmp_path, assertion=False) == ["assertion"]


def test_rejects_a_case_named_only_by_another_function(tmp_path):
    """The row names test_demo, but only test_elsewhere checks the case."""
    assert categories(tmp_path, named_function="test_elsewhere") == ["assertion"]


def test_rejects_a_status_that_disagrees_with_the_xfail_marker(tmp_path):
    assert categories(tmp_path, xfail="#23") == ["status"]
    assert categories(tmp_path, status="xfail #23") == ["status"]
    assert validate(**build(tmp_path, xfail="#23", status="xfail #23")) == []


def test_rejects_a_missing_test_module(tmp_path):
    assert categories(tmp_path, row_test="test_absent.py::test_demo") == ["assertion"]


def test_rejects_a_case_with_no_row(tmp_path):
    assert categories(tmp_path, row=False) == ["orphan"]


def test_rejects_a_fixture_outside_the_corpus_that_does_not_exist(tmp_path):
    assert categories(tmp_path, fixture="nowhere.bib") == ["fixture"]
