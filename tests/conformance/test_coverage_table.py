"""Meta-tests: tests/COVERAGE.md, the corpus and the tests agree.

The rules are in coverage_check.py, driven here against the real tree and in
test_coverage_check.py against synthetic ones that pin each of them. That
file's docstring says what the rules catch and where they stop.
"""

import ast
import re
from pathlib import Path

import pytest

import labdata

from .coverage_check import read_table, validate
from .support import CORPUS, EXPECTED, REPO_ROOT, TESTS_DIR

COVERAGE = TESTS_DIR / "COVERAGE.md"
CONFORMANCE = Path(__file__).parent
DIAGNOSTICS = EXPECTED / "diagnostics.yaml"


@pytest.fixture(scope="module")
def problems():
    return validate(COVERAGE, CORPUS, CONFORMANCE, REPO_ROOT, DIAGNOSTICS)


def of(problems, category):
    return "\n".join(str(p) for p in problems if p.category == category)


def test_table_is_populated():
    rows = read_table(COVERAGE)
    assert len(rows) > 100


def test_ids_are_unique_and_well_formed(problems):
    assert of(problems, "id") == ""


def test_every_row_has_fixture_data(problems):
    """Each row's fixture marks its case with `% CASE <id>`."""
    assert of(problems, "fixture") == ""


def test_every_row_has_an_assertion(problems):
    """The test each row names exists, checks that case, and asserts something.

    Honest mistakes — a missing test, one wired to another case, a body that
    was never written — not a test built to look past the check.
    """
    assert of(problems, "assertion") == ""


def test_status_matches_xfail_markers(problems):
    assert of(problems, "status") == ""


def test_diagnostics_checks_name_something(problems):
    """Every reports/locates/kept list in diagnostics.yaml says what to look for."""
    assert of(problems, "diagnostics") == ""


def test_no_orphan_cases(problems):
    """Every CASE marker and every case a test names has a row."""
    assert of(problems, "orphan") == ""


def test_unsupported_input_is_never_silently_ignored():
    """Rows for unsupported or invalid input expect a warning or an error."""
    for row in read_table(COVERAGE):
        if row.test.startswith("test_invalid_corpus.py"):
            assert re.search(r"\b(warning|error)\b", row.expected, re.I), row.id


# --- Test-suite hygiene (acceptance criteria of #43) ------------------------

# --- Strict xfails say what they expect to fail with -------------------------
#
# A strict xfail names a claim the document does not yet satisfy, and the test
# makes that claim with an `assert`. A marked test that breaks on a NameError,
# a missing key or an unreadable fixture never reached its own assertion, so
# the marker reports nothing -- and, with no `raises`, pytest counts it as
# expected and nobody looks. Declaring the exception is what makes pytest
# itself reject the other kind.

def _strict_xfails(items):
    """(item, mark) for every strict xfail marker on the collected tests."""
    return [(item, mark) for item in items
            for mark in item.iter_markers(name="xfail")
            if mark.kwargs.get("strict")]


def test_every_collected_strict_xfail_declares_the_exception_it_expects(request):
    """Over the tests actually collected, so a generated marker is covered too.

    Dropping `raises` from `support._xfail_marks()`, from the generator in
    `test_invalid_corpus.py`, or from a literal marker turns this red. It says
    nothing when the selection happens to collect no marked test, which is why
    the source check below carries the "looked and found some" half.
    """
    undeclared = sorted(item.nodeid
                        for item, mark in _strict_xfails(request.session.items)
                        if mark.kwargs.get("raises") is None)
    assert undeclared == []


def _xfail_marker_calls(tree):
    """Every ``pytest.mark.xfail(...)`` call in an AST, as its keyword names."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name, attribute = "", node.func
        while isinstance(attribute, ast.Attribute):
            name = attribute.attr + "." + name
            attribute = attribute.value
        if isinstance(attribute, ast.Name):
            name = attribute.id + "." + name
        if name.rstrip(".") == "pytest.mark.xfail":
            yield {keyword.arg for keyword in node.keywords}


# Every place in the suite that builds a strict xfail marker: the two
# generators and the one literal. Stated here so that a fourth cannot be
# added without this row moving, and so the search below cannot pass by
# finding nothing.
XFAIL_MARKER_SITES = 3


def test_every_strict_xfail_in_the_source_declares_the_exception_it_expects():
    """The other half: the search really finds the markers it is checking."""
    found, undeclared = 0, []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for keywords in _xfail_marker_calls(tree):
            if "strict" not in keywords:
                continue
            found += 1
            if "raises" not in keywords:
                undeclared.append(str(path.relative_to(TESTS_DIR)))
    assert undeclared == []
    assert found == XFAIL_MARKER_SITES, found


# One throwaway suite, covering the three shapes: the claim the marker names,
# a test that breaks in the call phase, and one that breaks in a fixture --
# which is the case a hook keyed on `report.when == "call"` cannot see.
DECLARED_RAISES_SUITE = """
import pytest


@pytest.mark.xfail(strict=True, reason="#0", raises=AssertionError)
def test_makes_the_claim_its_marker_names():
    assert False, "the property the issue owes"


@pytest.mark.xfail(strict=True, reason="#0", raises=AssertionError)
def test_breaks_in_the_call_phase():
    RenamedAwayFromUnderTheTest  # noqa: F821


@pytest.fixture
def broken_fixture():
    return RenamedAwayFromUnderTheTest  # noqa: F821


@pytest.mark.xfail(strict=True, reason="#0", raises=AssertionError)
def test_breaks_in_the_fixture_phase(broken_fixture):
    assert False, "never reached"
"""


def test_a_declared_raises_rejects_a_marker_that_broke_before_its_assertion(pytester):
    """End to end, in an isolated pytest run: one xfail, two refusals.

    `pytester` is pytest's own fixture and adds no dependency. The run is a
    subprocess with its own rootdir, so this repository's settings do not
    reach it and what it shows is pytest's behaviour and nothing else.
    """
    pytester.makepyfile(DECLARED_RAISES_SUITE)
    outcomes = pytester.runpytest_subprocess("-q").parseoutcomes()

    # The one that made its claim is expected; the two that broke on the way
    # are not, whichever phase they broke in.
    assert outcomes.get("xfailed", 0) == 1, outcomes
    assert outcomes.get("failed", 0) + outcomes.get("errors", 0) == 2, outcomes


# --- Test-suite hygiene (acceptance criteria of #43) ------------------------

PUBLIC = set(labdata.__all__) | {"main"}


def imports(path):
    """(module, name) for each import; name is None for ``import module``."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                yield node.module, alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None


# The adapter of #23: the only place pybtex and pylatexenc may be imported.
ADAPTER = {"labdata/parsers/bibtex.py", "labdata/parsers/latex.py"}
PARSER_LIBRARIES = {"pybtex", "pylatexenc", "bibtexparser"}


def test_no_test_imports_a_parser_library():
    """Tests check labdata's output, never a parser library's objects."""
    offenders = [str(p.relative_to(TESTS_DIR)) for p in TESTS_DIR.rglob("*.py")
                 if any(m.split(".")[0] in PARSER_LIBRARIES for m, _ in imports(p))]
    assert offenders == []


def test_only_the_adapter_imports_a_parser_library():
    """pybtex and pylatexenc stay behind the adapter, as #23 requires."""
    offenders = []
    for path in sorted((REPO_ROOT / "labdata").rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in ADAPTER:
            continue
        for module, _ in imports(path):
            if module.split(".")[0] in PARSER_LIBRARIES:
                offenders.append(f"{relative}: {module}")
    assert offenders == []
    # An empty list has to mean "looked and found none": the adapter itself
    # imports both libraries, so the search above can see one when it is there.
    found = {module.split(".")[0] for path in ADAPTER
             for module, _ in imports(REPO_ROOT / path)}
    assert {"pybtex", "pylatexenc"} <= found


def test_only_unit_tests_import_labdata_internals():
    """Outside tests/unit/, tests use only labdata's public names and cli.main."""
    offenders = []
    for path in TESTS_DIR.rglob("*.py"):
        if "unit" in path.relative_to(TESTS_DIR).parts:
            continue
        for module, name in imports(path):
            if not module.startswith("labdata"):
                continue
            if name is None:
                public = module == "labdata"
            else:
                public = name in PUBLIC and (name != "main" or module == "labdata.cli")
            if not public:
                offenders.append(f"{path.relative_to(TESTS_DIR)}: {module} {name}")
    assert offenders == []
