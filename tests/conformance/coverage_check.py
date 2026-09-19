"""The validator behind tests/COVERAGE.md.

It takes the table, the corpus and the test directory as arguments, so it can
be driven against the real tree (test_coverage_table.py) and against tiny
synthetic trees that prove it rejects what it claims to reject
(test_coverage_check.py).

A row of the table is valid when

- its fixture marks the case with ``% CASE <id>`` (``# CASE <id>`` in YAML),
  or, for a fixture outside the corpus, simply exists;
- the test it names exists, is bound to that case ID, and carries an
  effective assertion: an ``assert`` that can run, over something other than
  a literal expression, made by the test or by a helper it defines or imports
  by name. A parametrized test must also read the values its table supplies
  where they can run, so a table cannot be attached to a function that
  ignores it;
- its status agrees with the ``xfail`` markers the tests attach to the case.

A case ID is bound to a test function by a ``case()`` or ``covers()`` call in
that function or its decorators, including through a parametrize table, or, for
the invalid corpus, by naming a check that expected/diagnostics.yaml lists.

What it rejects, all of it decidable from the source: a test whose only
assertions are syntactically literal-only (``assert True``, ``assert 1``,
``assert 2 + 2 == 4``); one that can never run, because it follows an
unconditional ``return``/``raise``/``continue``/``break``, sits in a
statically false branch (``if False:``), or is only inside a nested ``def``
or ``class``, which is a definition rather than something the test runs; an
assertion inherited from a same-named function in a module the test does not
import; a parametrize table whose values the test never reads where they can
run; and an empty token list in expected/diagnostics.yaml.

What it cannot do:

- decide whether an assertion is *about the right thing*. A test that asserts
  something true but beside the point, or a weaker property than its row
  claims, still passes. Only review catches that;
- see through anything but literal syntax. The literal check is syntactic, so
  ``assert bool(True)`` passes because it contains a call, and a test that
  assigns its parameters to ``_`` and then asserts something unrelated
  satisfies the parameter check;
- read helpers reached any other way than a plain call to a local or imported
  name. A call through a module object (``helpers.check(...)``) or into a
  nested ``def`` carries no assertion here — that is the accepted form, not an
  oversight, and test_coverage_check.py pins both.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
    reads_parameters: bool = True


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


def _diagnostics_tokens(path: Optional[Path]):
    """(check, case id, tokens) for each token list in expected/diagnostics.yaml."""
    if path is None or not Path(path).is_file():
        return
    with open(path, encoding="utf-8") as f:
        specs = yaml.safe_load(f) or {}
    for case_id, spec in specs.items():
        for check in ("reports", "locates", "kept"):
            if check in spec:
                yield check, case_id, spec[check]


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


TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _constant_truth(test: Optional[ast.expr]) -> Optional[bool]:
    """True/False for a test that is a literal, None when it is not decidable."""
    if test is None:
        return None
    try:
        return bool(ast.literal_eval(test))
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def _live_blocks(stmt: ast.stmt):
    """The blocks of a statement that can run, with constant tests decided."""
    if isinstance(stmt, (ast.If, ast.While)):
        truth = _constant_truth(stmt.test)
        if truth is True:          # `if True:` / `while True:`: the else arm cannot run
            yield stmt.body
            return
        if truth is False:         # `if False:` / `while False:`: only the else arm can
            yield stmt.orelse
            return
    for name in ("body", "orelse", "finalbody"):
        block = getattr(stmt, name, None)
        if isinstance(block, list):
            yield block
    for handler in getattr(stmt, "handlers", []):
        yield handler.body


def _reachable(body: List[ast.stmt]):
    """Statements that can run with the test.

    Anything after a terminator in a block cannot, nor can the body of a
    statically false branch. A nested ``def`` or ``class`` is a definition,
    not a statement that runs, so its body is not part of the test: a helper
    has to be a module-level function to carry an assertion.
    """
    for stmt in body:
        yield stmt
        if isinstance(stmt, DEFINITIONS):
            continue
        for block in _live_blocks(stmt):
            yield from _reachable(block)
        if isinstance(stmt, TERMINATORS):
            return


def _own_expressions(stmt: ast.stmt):
    """The expressions of one statement, without the blocks nested inside it."""
    for name, value in ast.iter_fields(stmt):
        if name in ("body", "orelse", "finalbody", "handlers"):
            continue
        for node in (value if isinstance(value, list) else [value]):
            if isinstance(node, ast.AST):
                yield from ast.walk(node)


def _called_names(fn: ast.FunctionDef) -> Set[str]:
    """Plain function calls that can run: a call in dead code carries nothing."""
    return {sub.func.id for stmt in _reachable(fn.body)
            for sub in _own_expressions(stmt)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)}


def _is_trivial(test: ast.expr) -> bool:
    """True for a test built only from literals: ``True``, ``1``, ``2 + 2 == 4``."""
    return not any(isinstance(n, (ast.Name, ast.Call, ast.Attribute, ast.Subscript,
                                  ast.Starred, ast.Await, ast.Yield))
                   for n in ast.walk(test))


def _asserts_something(fn: ast.FunctionDef) -> bool:
    return any(isinstance(stmt, ast.Assert) and not _is_trivial(stmt.test)
               for stmt in _reachable(fn.body))


def _import_map(tree: ast.Module, modules: Set[str]) -> Dict[str, Tuple[str, str]]:
    """{local name: (module file, name there)} for imports within the test dir.

    ``from .support import assert_field as check`` binds ``check`` to
    ``support.py::assert_field``.
    """
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            target = f"{node.module.split('.')[-1]}.py"
            if target in modules:
                for alias in node.names:
                    imported[alias.asname or alias.name] = (target, alias.name)
    return imported


def _parametrized_names(fn: ast.FunctionDef) -> List[List[str]]:
    """The argnames of each @pytest.mark.parametrize on ``fn``."""
    found = []
    for dec in fn.decorator_list:
        for sub in ast.walk(dec):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr == "parametrize" and sub.args \
                    and isinstance(sub.args[0], ast.Constant):
                found.append([n.strip() for n in sub.args[0].value.split(",") if n.strip()])
    return found


def _reads_parameters(fn: ast.FunctionDef) -> bool:
    """Every parametrized value the table supplies is read where it can run.

    ``case_id`` is a label, so a test that ignores it is fine; ignoring the
    input or the expectation is not, and a reference in dead code is not a
    read.
    """
    used = {n.id for stmt in _reachable(fn.body) for n in _own_expressions(stmt)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    for argnames in _parametrized_names(fn):
        wanted = [n for n in argnames if n != "case_id"] or argnames
        if not set(wanted) <= used:
            return False
    return True


def read_tests(tests_dir: Path, diagnostics: Optional[Path] = None) -> Dict[str, Binding]:
    """{"module.py::function": Binding} for every test function in ``tests_dir``.

    Also indexes the helpers the tests call, so a test that asserts only
    through a helper still counts as asserting.
    """
    tests_dir = Path(tests_dir)
    by_check = _diagnostics_ids(diagnostics)
    trees = {p.name: ast.parse(p.read_text(encoding="utf-8"))
             for p in sorted(tests_dir.glob("*.py"))}

    # Which functions assert, on their own or through a helper. A call is
    # resolved in the defining module, then in the module it was imported
    # from: never by bare name, so a same-named function elsewhere in the
    # tree cannot donate its assert.
    defined: Set[str] = set()
    direct: Dict[str, bool] = {}
    calls: Dict[str, Set[str]] = {}
    imports = {module: _import_map(tree, set(trees)) for module, tree in trees.items()}
    for module, tree in trees.items():
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            key = f"{module}::{fn.name}"
            defined.add(key)
            direct[key] = _asserts_something(fn)
            calls[key] = _called_names(fn)

    def resolve(module: str, name: str) -> Optional[str]:
        own = f"{module}::{name}"
        if own in defined:
            return own
        target = imports[module].get(name)
        if target:
            key = f"{target[0]}::{target[1]}"
            if key in defined:
                return key
        return None

    asserts = dict(direct)
    for _ in range(len(asserts) + 1):
        changed = False
        for key, called in calls.items():
            if asserts[key]:
                continue
            module = key.split("::")[0]
            for name in called:
                resolved = resolve(module, name)
                if resolved and asserts.get(resolved):
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
            binding = Binding(module=module, function=fn.name, asserts=asserts[key],
                              reads_parameters=_reads_parameters(fn))
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
            bad("assertion", f"{row.id}: {row.test} has no effective assertion "
                             "(none, unreachable, or only over literals)")
        elif not binding.reads_parameters:
            bad("assertion", f"{row.id}: {row.test} never reads the values its "
                             "parametrize table supplies")

        issues = set()
        for b in bindings.values():
            issues |= b.ids.get(row.id, set())
        if issues:
            if not row.status.startswith("xfail") or set(ISSUE_RE.findall(row.status)) != issues:
                bad("status", f"{row.id}: status {row.status!r}, but tests xfail "
                              f"{', '.join(sorted(issues))}")
        elif row.status != "pass":
            bad("status", f"{row.id}: status {row.status!r}, but no test is xfailed")

    for check, case_id, tokens in _diagnostics_tokens(diagnostics):
        if not tokens:
            bad("diagnostics", f"{case_id}: '{check}' lists nothing to look for")

    known_ids = set(markers)
    for binding in bindings.values():
        known_ids |= set(binding.ids)
    for case_id in sorted(known_ids - seen):
        bad("orphan", f"{case_id}: has a fixture marker or a test, but no row")

    return problems
