"""tests/COVERAGE.md names a fixture and a test for each case, and test-suite
hygiene: tests reach sslabdata only through its public names."""

import ast
import re

import sslabdata

from .support import CORPUS, EXPECTED, REPO_ROOT, TESTS_DIR

ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|[^|]*\|[^|]*\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def mentions(text, case_id):
    return re.search(r"(?<![\w.])" + re.escape(case_id) + r"(?![\w.])", text)


def test_every_row_appears_in_its_fixture_and_a_test():
    """Each row's ID is in the fixture it names and in a test or diagnostics.yaml.

    A fixture outside tests/corpus (the demo, a schema) carries no markers,
    so for those the named file only has to exist.
    """
    rows = ROW_RE.findall((TESTS_DIR / "COVERAGE.md").read_text(encoding="utf-8"))
    test_files = [*TESTS_DIR.rglob("test_*.py"), EXPECTED / "diagnostics.yaml"]
    tests = "\n".join(path.read_text(encoding="utf-8") for path in test_files)
    problems = []
    for case_id, fixture in rows:
        path = REPO_ROOT / fixture
        if not path.is_file():
            problems.append(f"{case_id}: no fixture {fixture}")
        elif CORPUS in path.parents and not mentions(
                path.read_bytes().decode("utf-8", errors="replace"), case_id):
            problems.append(f"{case_id}: not in {fixture}")
        if not mentions(tests, case_id):
            problems.append(f"{case_id}: in no test")
    assert len(rows) > 100, len(rows)
    assert not problems, "\n".join(problems)


# --- Test-suite hygiene (acceptance criteria of #43) ------------------------

PUBLIC = set(sslabdata.__all__) | {"main"}


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
ADAPTER = {"sslabdata/parsers/bibtex.py", "sslabdata/parsers/latex.py"}
PARSER_LIBRARIES = {"pybtex", "pylatexenc", "bibtexparser"}


def test_no_test_imports_a_parser_library():
    """Tests check sslabdata's output, never a parser library's objects."""
    offenders = [str(p.relative_to(TESTS_DIR)) for p in TESTS_DIR.rglob("*.py")
                 if any(m.split(".")[0] in PARSER_LIBRARIES for m, _ in imports(p))]
    assert offenders == []


def test_only_the_adapter_imports_a_parser_library():
    """pybtex and pylatexenc stay behind the adapter, as #23 requires."""
    offenders = []
    for path in sorted((REPO_ROOT / "sslabdata").rglob("*.py")):
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


def test_only_unit_tests_import_sslabdata_internals():
    """Outside tests/unit/, tests use only sslabdata's public names and cli.main."""
    offenders = []
    for path in TESTS_DIR.rglob("*.py"):
        if "unit" in path.relative_to(TESTS_DIR).parts:
            continue
        for module, name in imports(path):
            if not module.startswith("sslabdata"):
                continue
            if name is None:
                public = module == "sslabdata"
            else:
                public = name in PUBLIC and (name != "main" or module == "sslabdata.cli")
            if not public:
                offenders.append(f"{path.relative_to(TESTS_DIR)}: {module} {name}")
    assert offenders == []
