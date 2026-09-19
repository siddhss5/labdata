"""Meta-tests: tests/COVERAGE.md, the corpus and the tests agree.

The rules are in coverage_check.py, driven here against the real tree and in
test_coverage_check.py against synthetic ones that prove each rule bites.
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
    """The test each row names exists, checks that case, and asserts something."""
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


def test_no_test_imports_bibtexparser():
    offenders = [str(p.relative_to(TESTS_DIR)) for p in TESTS_DIR.rglob("*.py")
                 if any(m.split(".")[0] == "bibtexparser" for m, _ in imports(p))]
    assert offenders == []


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
