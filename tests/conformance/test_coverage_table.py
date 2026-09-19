"""Meta-tests: tests/COVERAGE.md, the corpus and the tests agree.

Every row of the supported-cases table must have
- fixture data: a ``CASE <id>`` marker in the fixture file the row names
  (``% CASE <id>`` in a .bib file, ``# CASE <id>`` in a YAML file). The one
  fixture outside tests/corpus/, the demo, only has to exist;
- an assertion: the row's test module names the ID in ``case()`` or
  ``covers()``, or, for test_invalid_corpus.py, in expected/diagnostics.yaml;
- a status that matches the tests: ``pass``, or ``xfail #N`` listing every
  issue that the ID's xfail markers point to.

And every CASE marker and every ID a test names must have a row.
"""

import ast
import re
from pathlib import Path

import yaml

import labdata

from .support import CORPUS, EXPECTED, REPO_ROOT, TESTS_DIR

COVERAGE = TESTS_DIR / "COVERAGE.md"
CONFORMANCE = Path(__file__).parent
ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")
MARKER_RE = re.compile(r"^\s*[%#]\s*CASE\s+(\S+)\s*$", re.MULTILINE)
ISSUE_RE = re.compile(r"#\d+")


def table_rows():
    rows = []
    for line in COVERAGE.read_text(encoding="utf-8").splitlines():
        if not ROW_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 6, f"expected 6 cells: {line}"
        case_id, _input, expected, fixture, test, status = (c.strip("`") for c in cells)
        rows.append({"id": case_id, "expected": expected, "fixture": fixture,
                     "test": test, "status": status})
    return rows


def code_cases():
    """{module file name: {case id: set of xfail issues}} from case()/covers() calls."""
    found = {}
    for path in sorted(CONFORMANCE.glob("test_*.py")):
        ids = found.setdefault(path.name, {})
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("case", "covers")):
                continue
            xfail = {kw.value.value for kw in node.keywords
                     if kw.arg == "xfail" and isinstance(kw.value, ast.Constant)}
            args = node.args[:1] if node.func.id == "case" else node.args
            for arg in args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    ids.setdefault(arg.value, set()).update(xfail)
    with open(EXPECTED / "diagnostics.yaml", encoding="utf-8") as f:
        diagnostics = yaml.safe_load(f)
    found["test_invalid_corpus.py"] = {
        case_id: set(spec.get("xfail", {}).values()) for case_id, spec in diagnostics.items()
    }
    return found


def corpus_markers():
    """{case id: set of repo-relative fixture paths that mark it}."""
    markers = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix not in (".bib", ".yaml") or EXPECTED in path.parents:
            continue
        text = path.read_bytes().decode("utf-8-sig")
        for case_id in MARKER_RE.findall(text):
            markers.setdefault(case_id, set()).add(path.relative_to(REPO_ROOT).as_posix())
    return markers


def test_ids_are_unique_and_well_formed():
    ids = [row["id"] for row in table_rows()]
    assert len(ids) > 100
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})
    assert [i for i in ids if not ID_RE.match(i)] == []


def test_every_row_has_fixture_data():
    markers = corpus_markers()
    missing = []
    for row in table_rows():
        fixture = REPO_ROOT / row["fixture"]
        if CORPUS in fixture.parents:
            ok = row["fixture"] in markers.get(row["id"], set())
        else:
            ok = fixture.is_file()
        if not ok:
            missing.append(f"{row['id']} (fixture {row['fixture']})")
    assert missing == [], "rows without a CASE marker in their fixture file:\n" + "\n".join(missing)


def test_every_row_has_an_assertion():
    cases = code_cases()
    problems = []
    for row in table_rows():
        module, _, function = row["test"].partition("::")
        path = CONFORMANCE / module
        if not path.is_file():
            problems.append(f"{row['id']}: no test module {module}")
            continue
        defined = {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                   if isinstance(n, ast.FunctionDef)}
        if function not in defined:
            problems.append(f"{row['id']}: no test {row['test']}")
        if row["id"] not in cases.get(module, {}):
            problems.append(f"{row['id']}: {module} does not name this case")
    assert problems == [], "\n".join(problems)


def test_status_matches_xfail_markers():
    cases = code_cases()
    problems = []
    for row in table_rows():
        issues = set().union(*(ids.get(row["id"], set()) for ids in cases.values()))
        if issues:
            if not row["status"].startswith("xfail") or \
                    set(ISSUE_RE.findall(row["status"])) != issues:
                problems.append(f"{row['id']}: status {row['status']!r}, tests xfail "
                                f"{sorted(issues)}")
        elif row["status"] != "pass":
            problems.append(f"{row['id']}: status {row['status']!r}, but no test is xfailed")
    assert problems == [], "\n".join(problems)


def test_unsupported_input_is_never_silently_ignored():
    """Rows for unsupported or invalid input expect a warning or an error."""
    for row in table_rows():
        if row["test"].startswith("test_invalid_corpus.py"):
            assert re.search(r"\b(warning|error)\b", row["expected"], re.I), row["id"]


def test_no_orphan_cases():
    """Every CASE marker and every case a test names has a row in the table."""
    ids = {row["id"] for row in table_rows()}
    named = set(corpus_markers())
    for module_ids in code_cases().values():
        named |= set(module_ids)
    assert sorted(named - ids) == []


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
