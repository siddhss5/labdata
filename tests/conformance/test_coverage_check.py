"""Negative controls for coverage_check.validate().

Each test builds a tiny tree — one table row, one fixture, one test module —
in tmp_path, breaks exactly one thing, and checks that the validator says so.
Without these, the meta-test could quietly stop enforcing anything.

The validator only rejects what static analysis can decide. These controls
pin that list down; see coverage_check's docstring for what stays out of
reach (an assertion that is real but checks the wrong thing).
"""

import textwrap

from .coverage_check import validate

HEADER = ("| Case | Input | Expected | Fixture | Test | Status |\n"
          "|---|---|---|---|---|---|\n")

# What a real test in this suite looks like: an assertion over case data.
REAL_BODY = """\
    entry = read_entry(bib_key)
    assert entry["year"] == expected
"""
PREAMBLE = """\
from .support import case, covers


def read_entry(key):
    return {"year": "2024"}
"""


def build(tmp_path, *, marker=True, body=REAL_BODY, decorator='@covers("names.demo")',
          signature="bib_key, expected", named_function="test_demo",
          row_test="test_demo.py::test_demo", status="pass", xfail=None, row=True,
          fixture="corpus/valid/demo.bib", preamble=PREAMBLE, extra_modules=None,
          diagnostics=None):
    """A minimal tree for one case, ``names.demo``, with one thing optionally off."""
    corpus = tmp_path / "corpus" / "valid"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "demo.bib").write_text(
        ("% CASE names.demo\n" if marker else "") + "@article{demo,\n  year = {2024}\n}\n",
        encoding="utf-8")

    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    if xfail:
        decorator = decorator.replace(")", f', xfail="{xfail}")')
    module = f"{preamble}\n\n{decorator}\ndef {named_function}({signature}):\n{body}"
    if named_function != "test_demo":   # the row names a function that checks nothing
        module += f"\n\ndef test_demo({signature}):\n{body}"
    (tests / "test_demo.py").write_text(module, encoding="utf-8")
    for name, source in (extra_modules or {}).items():
        (tests / name).write_text(textwrap.dedent(source), encoding="utf-8")

    diagnostics_path = None
    if diagnostics is not None:
        diagnostics_path = tmp_path / "diagnostics.yaml"
        diagnostics_path.write_text(diagnostics, encoding="utf-8")

    table = tmp_path / "COVERAGE.md"
    line = (f"| `names.demo` | an entry | read | `{fixture}` | "
            f"`{row_test}` | {status} |\n") if row else ""
    table.write_text(HEADER + line, encoding="utf-8")
    return dict(table=table, corpus_dir=tmp_path / "corpus", tests_dir=tests,
                repo_root=tmp_path, diagnostics=diagnostics_path)


def categories(tmp_path, **kwargs):
    return sorted({p.category for p in validate(**build(tmp_path, **kwargs))})


def test_accepts_a_well_formed_row(tmp_path):
    assert validate(**build(tmp_path)) == []


def test_rejects_a_fixture_without_the_case_marker(tmp_path):
    assert categories(tmp_path, marker=False) == ["fixture"]


def test_rejects_a_named_test_with_no_assertion(tmp_path):
    assert categories(tmp_path, body="    pass\n") == ["assertion"]


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


# --- Assertions that establish nothing ---------------------------------------

def test_rejects_a_constant_assertion(tmp_path):
    for body in ("    assert True\n", "    assert 1\n", '    assert "x"\n'):
        assert categories(tmp_path, body=body) == ["assertion"], body


def test_rejects_a_comparison_between_literals(tmp_path):
    for body in ("    assert 2 + 2 == 4\n", '    assert "a" in "abc"\n'):
        assert categories(tmp_path, body=body) == ["assertion"], body


def test_rejects_an_assertion_after_an_unconditional_return(tmp_path):
    body = "    return\n    assert read_entry(bib_key) == expected\n"
    assert categories(tmp_path, body=body) == ["assertion"]
    # The same assertion before the return is fine.
    live = "    assert read_entry(bib_key) == expected\n    return\n"
    assert validate(**build(tmp_path, body=live)) == []


def test_rejects_a_helper_call_after_an_unconditional_return(tmp_path):
    """A dead call cannot donate the assertion inside the helper either."""
    assert categories(
        tmp_path,
        preamble=PREAMBLE + "\ndef check_entry(key, expected):\n    assert read_entry(key) == expected\n",
        body="    return\n    check_entry(bib_key, expected)\n",
    ) == ["assertion"]


def test_rejects_an_unused_parametrize_table(tmp_path):
    """A table naming the case, attached to a test that never reads its values."""
    assert categories(
        tmp_path,
        preamble=PREAMBLE + '\nimport pytest\n\nROWS = [case("names.demo", "demo", "2024")]\n',
        decorator='@pytest.mark.parametrize("case_id, bib_key, expected", ROWS)',
        signature="case_id, bib_key, expected",
        body='    assert read_entry(bib_key) == "2024"\n',   # ignores expected
    ) == ["assertion"]


def test_rejects_an_assert_borrowed_from_another_module(tmp_path):
    """A helper of the same name in a module this one does not import."""
    assert categories(
        tmp_path,
        body="    check_entry(bib_key, expected)\n",
        extra_modules={"other_helpers.py": '''
            def check_entry(key, expected):
                assert read_entry(key) == expected
        '''},
    ) == ["assertion"]


def test_accepts_an_assert_from_an_imported_helper(tmp_path):
    """The same helper, imported: its assertion does carry over."""
    assert validate(**build(
        tmp_path,
        preamble=PREAMBLE + "from .other_helpers import check_entry\n",
        body="    check_entry(bib_key, expected)\n",
        extra_modules={"other_helpers.py": '''
            def check_entry(key, expected):
                assert key == expected
        '''},
    )) == []


def test_rejects_an_empty_diagnostics_token_list(tmp_path):
    """A diagnostics check that advertises tokens but lists none."""
    spec = "names.demo:\n  dir: demo\n  exit: error\n  reports: []\n"
    assert categories(
        tmp_path,
        preamble=PREAMBLE + "\nimport pytest\n\n\ndef params(check):\n    return []\n",
        decorator='@pytest.mark.parametrize("case_id, spec", params("reports"))',
        signature="case_id, spec",
        body='    assert spec["reports"]\n',
        row_test="test_demo.py::test_demo",
        diagnostics=spec,
    ) == ["diagnostics"]
