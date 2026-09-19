"""The validator behind tests/COVERAGE.md.

It takes the table, the corpus and the test directory as arguments, so it can
be driven against the real tree (test_coverage_table.py) and against tiny
synthetic trees that prove it rejects what it claims to reject
(test_coverage_check.py).

A row of the table is valid when

- its fixture marks the case with ``% CASE <id>`` (``# CASE <id>`` in YAML),
  or, for a fixture outside the corpus, simply exists;
- the test it names exists, is bound to that case ID, and carries an
  assertion: an ``assert`` of its own, or a call to a helper that asserts;
- its status agrees with the ``xfail`` markers the tests attach to the case.

A case ID is bound to a test function by a ``case()`` or ``covers()`` call in
that function or its decorators, including through a parametrize table, or, for
the invalid corpus, by naming a check that expected/diagnostics.yaml lists.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")
MARKER_RE = re.compile(r"^\s*[%#]\s*CASE\s+(\S+)\s*$", re.MULTILINE)
ISSUE_RE = re.compile(r"#\d+")
FIXTURE_SUFFIXES = (".bib", ".yaml")


@dataclass(frozen=True)
class Problem:
    """One thing wrong with the table, in a category a test can select on."""
    category: str
    message: str

    def __str__(self):
        return f"[{self.category}] {self.message}"


@dataclass
class Row:
    id: str
    input: str
    expected: str
    fixture: str
    test: str
    status: str


@dataclass
class Binding:
    """What one test function does with the case IDs it names."""
    module: str
    function: str
    ids: Dict[str, Set[str]] = field(default_factory=dict)  # id -> xfail issues
    asserts: bool = False


# --- Reading the three inputs ------------------------------------------------

def read_table(path: Path) -> List[Row]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not ROW_RE.match(line):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            raise ValueError(f"expected 6 cells, got {len(cells)}: {line}")
        rows.append(Row(*cells))
    return rows


def read_markers(corpus_dir: Path, repo_root: Path) -> Dict[str, Set[str]]:
    """{case id: set of repo-relative fixture paths that mark it}."""
    markers: Dict[str, Set[str]] = {}
    for path in sorted(Path(corpus_dir).rglob("*")):
        if not path.is_file() or path.suffix not in FIXTURE_SUFFIXES:
            continue
        for case_id in MARKER_RE.findall(path.read_bytes().decode("utf-8-sig")):
            markers.setdefault(case_id, set()).add(path.relative_to(repo_root).as_posix())
    return markers


def _diagnostics_ids(path: Optional[Path]) -> Dict[str, Dict[str, Set[str]]]:
    """{check name: {case id: xfail issues}} from expected/diagnostics.yaml."""
    if path is None or not Path(path).is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        specs = yaml.safe_load(f) or {}
    by_check: Dict[str, Dict[str, Set[str]]] = {}
    for case_id, spec in specs.items():
        for check in spec:
            if check in ("dir", "xfail"):
                continue
            issue = spec.get("xfail", {}).get(check)
            by_check.setdefault(check, {})[case_id] = {issue} if issue else set()
    return by_check


def _case_calls(node: ast.AST):
    """(ids, xfail issues) for every case()/covers() call inside ``node``."""
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id in ("case", "covers")):
            continue
        issues = {kw.value.value for kw in sub.keywords
                  if kw.arg == "xfail" and isinstance(kw.value, ast.Constant)}
        args = sub.args[:1] if sub.func.id == "case" else sub.args
        ids = {a.value for a in args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
        yield ids, issues


def _params_checks(node: ast.AST):
    """The check names passed to params(...) in a decorator."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                and sub.func.id == "params":
            for arg in sub.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    yield arg.value


def _called_names(node: ast.AST) -> Set[str]:
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                names.add(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                names.add(sub.func.attr)
    return names


def read_tests(tests_dir: Path, diagnostics: Optional[Path] = None) -> Dict[str, Binding]:
    """{"module.py::function": Binding} for every test function in ``tests_dir``.

    Also indexes the helpers the tests call, so a test that asserts only
    through a helper still counts as asserting.
    """
    tests_dir = Path(tests_dir)
    by_check = _diagnostics_ids(diagnostics)
    trees = {p.name: ast.parse(p.read_text(encoding="utf-8"))
             for p in sorted(tests_dir.glob("*.py"))}

    # Which functions assert, directly or through another function.
    direct: Dict[str, bool] = {}
    calls: Dict[str, Set[str]] = {}
    by_name: Dict[str, List[str]] = {}
    for module, tree in trees.items():
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            key = f"{module}::{fn.name}"
            direct[key] = any(isinstance(n, ast.Assert) for n in ast.walk(fn))
            calls[key] = _called_names(fn)
            by_name.setdefault(fn.name, []).append(key)

    asserts = dict(direct)
    for _ in range(len(asserts) + 1):
        changed = False
        for key, called in calls.items():
            if asserts[key]:
                continue
            for name in called:
                # Resolve a call in the defining module first, then anywhere.
                module = key.split("::")[0]
                candidates = [k for k in by_name.get(name, []) if k.startswith(f"{module}::")] \
                    or by_name.get(name, [])
                if any(asserts.get(k) for k in candidates):
                    asserts[key] = changed = True
                    break
        if not changed:
            break

    bindings: Dict[str, Binding] = {}
    for module, tree in trees.items():
        tables = {}   # module-level table variable -> [(ids, issues)]
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                found = list(_case_calls(node.value))
                if found:
                    tables[node.targets[0].id] = found
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            key = f"{module}::{fn.name}"
            binding = Binding(module=module, function=fn.name, asserts=asserts[key])
            found = list(_case_calls(fn))
            for dec in fn.decorator_list:
                for sub in ast.walk(dec):
                    if isinstance(sub, ast.Name) and sub.id in tables:
                        found += tables[sub.id]
                for check in _params_checks(dec):
                    found += [({cid}, issues) for cid, issues in by_check.get(check, {}).items()]
            for ids, issues in found:
                for case_id in ids:
                    binding.ids.setdefault(case_id, set()).update(issues)
            if binding.ids:
                bindings[key] = binding
    return bindings


# --- Validation --------------------------------------------------------------

def validate(table: Path, corpus_dir: Path, tests_dir: Path, repo_root: Path,
             diagnostics: Optional[Path] = None) -> List[Problem]:
    """Every way tests/COVERAGE.md, the corpus and the tests can disagree."""
    rows = read_table(table)
    markers = read_markers(corpus_dir, repo_root)
    bindings = read_tests(tests_dir, diagnostics)
    corpus_dir, repo_root = Path(corpus_dir), Path(repo_root)
    problems: List[Problem] = []

    def bad(category, message):
        problems.append(Problem(category, message))

    seen = set()
    for row in rows:
        if not ID_RE.match(row.id):
            bad("id", f"{row.id}: not a well-formed case ID")
        if row.id in seen:
            bad("id", f"{row.id}: more than one row")
        seen.add(row.id)

        fixture = repo_root / row.fixture
        if corpus_dir == fixture or corpus_dir in fixture.parents:
            if row.fixture not in markers.get(row.id, set()):
                bad("fixture", f"{row.id}: {row.fixture} has no '% CASE {row.id}' marker")
        elif not fixture.is_file():
            bad("fixture", f"{row.id}: fixture {row.fixture} does not exist")

        binding = bindings.get(row.test)
        module = row.test.partition("::")[0]
        if binding is None:
            known = {k.split("::")[0] for k in bindings}
            if module not in known:
                bad("assertion", f"{row.id}: no test module {module}")
            else:
                bad("assertion", f"{row.id}: {row.test} names no case")
        elif row.id not in binding.ids:
            named = sorted(k for k, b in bindings.items() if row.id in b.ids)
            bad("assertion", f"{row.id}: {row.test} does not check this case"
                             + (f" (named by {named})" if named else ""))
        elif not binding.asserts:
            bad("assertion", f"{row.id}: {row.test} has no assertion")

        issues = set()
        for b in bindings.values():
            issues |= b.ids.get(row.id, set())
        if issues:
            if not row.status.startswith("xfail") or set(ISSUE_RE.findall(row.status)) != issues:
                bad("status", f"{row.id}: status {row.status!r}, but tests xfail "
                              f"{', '.join(sorted(issues))}")
        elif row.status != "pass":
            bad("status", f"{row.id}: status {row.status!r}, but no test is xfailed")

    known_ids = set(markers)
    for binding in bindings.values():
        known_ids |= set(binding.ids)
    for case_id in sorted(known_ids - seen):
        bad("orphan", f"{case_id}: has a fixture marker or a test, but no row")

    return problems
