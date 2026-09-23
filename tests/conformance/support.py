"""Helpers for the conformance tests (see tests/COVERAGE.md).

The conformance tests run sslabdata only through its public entry points,
``sslabdata.cli.main()`` and the assembler, and check sslabdata's own output and
messages. They never look at parser-library objects or messages, so the same
tests run before and after the parser swap in #23.

Every test names the tests/COVERAGE.md case IDs it checks, with ``case()``
in a parameter table or ``covers()`` on a test function. The meta-test in
test_coverage_table.py reads those calls to match tests to table rows.
"""

import contextlib
import importlib
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pytest
import yaml

from sslabdata.cli import main


TESTS_DIR = Path(__file__).parent.parent
CORPUS = TESTS_DIR / "corpus"
VALID = CORPUS / "valid"
INVALID = CORPUS / "invalid"
EXPECTED = CORPUS / "expected"
REPO_ROOT = TESTS_DIR.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "v4" / "output.schema.json"

# The previous version's schema, which stays reachable byte for byte after v4
# ships: a consumer pinned to v3 keeps a stable target (SPEC.md section 6).
PREVIOUS_SCHEMA_PATH = REPO_ROOT / "schema" / "v3" / "output.schema.json"


# Every strict xfail in this suite names a claim the document does not yet
# satisfy, and a test makes that claim with an ``assert``. Declaring the
# exception makes pytest itself reject any other one: a marked test that
# breaks on a NameError, a missing key or an unreadable fixture never reached
# its own assertion, so the marker would be reporting nothing, and without
# this it would be counted as expected and nobody would look. It covers the
# fixture phase too, which is where a broken marker is hardest to see.
#
# A future xfail whose finding really is another exception declares that type
# instead; what is not allowed is declaring none.
EXPECTED_FAILURE = AssertionError


def _xfail_marks(xfail, because=None, raises=EXPECTED_FAILURE):
    """The xfail mark for ``xfail="#N"``, with ``because`` spelled into it.

    The issue number alone is what tests/COVERAGE.md's status column is
    matched against, so it stays the argument. ``because`` names the specific
    property the fix has to deliver, which is what a reader of the failure
    sees. ``raises`` is the exception the claim is made with; see above.
    """
    if not xfail:
        return []
    reason = "%s: %s" % (xfail, because) if because else xfail
    return [pytest.mark.xfail(strict=True, reason=reason, raises=raises)]


# Corpus entries whose values an open issue owns, declared by the xfailed
# case()/covers() calls below: {case id: {bib key}}. The snapshot in
# test_output_format.py reads this to stay off output a fix will change.
XFAIL_OWNERSHIP: Dict[str, Set[str]] = {}


def _record_ownership(case_ids: Iterable[str], owns: Iterable[str]):
    for case_id in case_ids:
        XFAIL_OWNERSHIP.setdefault(case_id, set()).update(owns)


def case(case_id, *values, xfail=None, owns=None, raises=EXPECTED_FAILURE):
    """One row of a parameter table: a case ID, then the test's values.

    ``xfail="#N"`` marks the row as failing until issue #N is fixed. An
    xfailed row owns the corpus entry it checks, which is ``values[0]`` in the
    per-entry tables; ``owns`` states it explicitly for any other shape.
    """
    if xfail:
        if owns is None:
            owns = [values[0]] if values and isinstance(values[0], str) else []
        _record_ownership([case_id], owns)
    label = ":".join([case_id] + [str(v) for v in values[:2]])
    return pytest.param(case_id, *values, id=label,
                        marks=_xfail_marks(xfail, raises=raises))


def covers(*case_ids, xfail=None, because=None, owns=None,
           raises=EXPECTED_FAILURE):
    """Decorate a test that checks the given case IDs.

    An xfailed test must say what it ``owns``: the corpus entries whose values
    issue ``xfail`` will change, or ``()`` when it owns none, because a
    covers() test has no entry to infer one from. Leaving it out is an error,
    so an omission cannot pass for "owns nothing".

    ``because`` is the rest of the xfail reason: the specific property the
    issue has to deliver, rather than "not supported yet".
    """
    if xfail:
        if owns is None:
            raise TypeError(
                f"covers({case_ids[0]!r}, xfail={xfail!r}) needs owns=(...): name the "
                "corpus entries the fix will change, or owns=() if it changes none")
        _record_ownership(case_ids, owns)

    def decorate(func):
        for mark in _xfail_marks(xfail, because, raises):
            func = mark(func)
        return func
    return decorate


# --- Running sslabdata ---------------------------------------------------------

@dataclass
class Run:
    """The result of one ``sslabdata`` command run in-process."""
    code: int
    stdout: str
    stderr: str
    crash: Optional[str] = None  # an uncaught exception, which is never OK

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


@contextlib.contextmanager
def working_dir(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_sslabdata(args: List[str], cwd: Path) -> Run:
    """Run ``sslabdata <args>`` from ``cwd``, capturing its exit code and output."""
    out, err = io.StringIO(), io.StringIO()
    code, crash = 0, None
    with working_dir(cwd), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            main([str(a) for a in args])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        except Exception as e:  # noqa: BLE001 - a crash is a result to report
            crash = f"{type(e).__name__}: {e}"
    return Run(code=code, stdout=out.getvalue(), stderr=err.getvalue(), crash=crash)


def export(cwd: Path, out_dir: Path, config="lab.yaml", fmt="json"):
    """Run ``sslabdata --output`` from ``cwd`` and return (run, parsed output)."""
    out_path = Path(out_dir) / f"lab.{fmt}"
    run = run_sslabdata(["--config", config, "--format", fmt, "--output", out_path], cwd)
    data = None
    if run.crash is None and run.code == 0:
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f) if fmt == "json" else yaml.safe_load(f)
    return run, data


def write_variant(tmp_path: Path, **changes) -> Path:
    """Write valid/lab.yaml with some keys changed (None removes a key).

    The variant keeps the valid corpus's relative paths, so run it from VALID.
    """
    with open(VALID / "lab.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    for key, value in changes.items():
        if value is None:
            config.pop(key, None)
        else:
            config[key] = value
    path = tmp_path / "variant.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return path


ENTRY_KEY_RE = re.compile(r"^@(\w+)\s*\{\s*([^,\s}]+)\s*,", re.MULTILINE)
NOT_ENTRIES = {"string", "comment", "preamble"}


def corpus_entry_keys() -> Set[str]:
    """Every citation key defined anywhere in tests/corpus."""
    keys = set()
    for path in sorted(CORPUS.rglob("*.bib")):
        # errors="replace": the corpus holds a file that is deliberately not UTF-8.
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        keys |= {key for kind, key in ENTRY_KEY_RE.findall(text)
                 if kind.lower() not in NOT_ENTRIES}
    return keys


def xfail_owned_entries() -> Set[str]:
    """Every corpus entry an open issue's xfail owns.

    Imports the test modules first, so the answer does not depend on which of
    them pytest happens to have collected. Entries of the invalid corpus are
    declared the same way; they simply never appear in the valid output.
    """
    for name in ("test_valid_corpus", "test_config_cli", "test_invalid_corpus"):
        importlib.import_module(f"{__package__}.{name}")
    owned: Set[str] = set()
    for entries in XFAIL_OWNERSHIP.values():
        owned |= entries
    return owned


# --- Looking things up in the output ---------------------------------------

def work(data, bib_id):
    matches = [w for w in data["works"] if w["bib_id"] == bib_id]
    assert len(matches) == 1, f"expected one work {bib_id!r}, found {len(matches)}"
    return matches[0]


def item(data, section, key, value):
    matches = [x for x in data[section] if x[key] == value]
    assert len(matches) == 1, f"expected one {section} entry with {key}={value!r}"
    return matches[0]


def get_path(obj, path: str):
    """Follow a dotted path: ``authors.0.name``, ``authors.*.name``."""
    parts = path.split(".")
    for i, part in enumerate(parts):
        if part == "*":
            rest = ".".join(parts[i + 1:])
            return [get_path(x, rest) if rest else x for x in obj]
        if isinstance(obj, list):
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            raise KeyError(f"cannot follow {path!r} at {part!r}")
    return obj


# --- Expected values ---------------------------------------------------------

class Contains:
    """Expected: a string or list that contains every one of ``parts``."""
    def __init__(self, *parts):
        self.parts = parts

    def check(self, actual):
        return actual is not None and all(p in actual for p in self.parts)

    def __repr__(self):
        return f"Contains{self.parts!r}"


class Excludes:
    """Expected: a string or list that contains none of ``parts``."""
    def __init__(self, *parts):
        self.parts = parts

    def check(self, actual):
        return actual is not None and not any(p in actual for p in self.parts)

    def __repr__(self):
        return f"Excludes{self.parts!r}"


class AllOf:
    """Expected: every one of the given expectations."""
    def __init__(self, *expectations):
        self.expectations = expectations

    def check(self, actual):
        return all(matches(e, actual) for e in self.expectations)

    def __repr__(self):
        return f"AllOf{self.expectations!r}"


def matches(expected, actual):
    if hasattr(expected, "check"):
        return expected.check(actual)
    return actual == expected


def assert_field(obj, path, expected, where=""):
    actual = get_path(obj, path)
    assert matches(expected, actual), f"{where}{path}: expected {expected!r}, got {actual!r}"
