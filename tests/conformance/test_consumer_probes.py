"""The consumer probes of #55, run against the demo output.

Each probe under `examples/consumers/` is a small program that reads the
emitted document and nothing else. It is run here the way a consumer would
run it -- as a subprocess taking the document's path -- so "reads only the
document" is true of how the test invokes it and not only of how it is
written. `test_no_probe_imports_labdata` and
`test_no_probe_reads_the_inputs_or_the_verbatim_export` back that up
statically.

The governing rule, stated in `examples/consumers/README.md` and in SPEC.md
section 1: **if a consumer probe cannot be written from the emitted document
alone, that is a schema bug, not a probe bug.** So a probe that cannot
produce correct output is marked `xfail(strict=True)` against the issue that
owns the missing property, and the probe itself is left alone. A probe is
never edited to assert its own incompleteness: it emits the best artifact it
can from what the document gives it, and the test here says what a correct
artifact would have contained.
"""

import ast
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import jsonschema
import pytest

from .support import REPO_ROOT, export, publication


PROBES = REPO_ROOT / "examples" / "consumers"
DEMO_CONFIG = "examples/demo/lab.yaml"
CSL_SCHEMA = REPO_ROOT / "tests" / "vendor" / "csl-data.json"

# Every probe, and the test that checks what it emits. `test_every_probe_is_
# exercised` fails if a probe is added to the directory and left out of here.
PROBE_TESTS = {
    "plain_html.py": "test_plain_html_page_is_complete",
    "cv_tex.py": "test_cv_tex_entry_is_citable",
    "csl_json.py": "test_csl_json_records_are_citable",
    "graph.py": "test_graph_covers_every_co_author",
}

# The demo record #56 is written against, and what a consumer must be able to
# say about it. Taken from examples/demo/bib/journal.bib, which no probe reads.
ARTICLE = "brown2025tidy"
JOURNAL = "Transactions on Robot Learning"
VOLUME, NUMBER, PAGES = "4", "2", "112--131"
DOI = "10.5555/example.trl.2025.0412"


@pytest.fixture(scope="module")
def demo_document(tmp_path_factory):
    """(path, parsed) for the demo exported as JSON."""
    out = tmp_path_factory.mktemp("probes")
    run, data = export(REPO_ROOT, out, DEMO_CONFIG, "json")
    assert run.crash is None, run.crash
    assert run.code == 0, run.output
    return out / "lab.json", data


def run_probe(name, document):
    """Run one probe as a consumer would: a subprocess given the document."""
    result = subprocess.run(
        [sys.executable, str(PROBES / name), str(document)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8")


@pytest.fixture(scope="module")
def probe_output(demo_document):
    """{probe name: what it wrote}, one subprocess per probe."""
    path, _ = demo_document
    return {name: run_probe(name, path) for name in PROBE_TESTS}


# --- plain_html.py -----------------------------------------------------------

VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}
BARE_AMPERSAND = re.compile(r"&(?!#?\w+;)")


class TagBalance(HTMLParser):
    """Enough of a parser to say whether the tags nest."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.open_tags = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_ELEMENTS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if not self.open_tags or self.open_tags[-1] != tag:
            self.problems.append("</%s> closes %s" % (tag, self.open_tags[-1:]))
        else:
            self.open_tags.pop()


def test_plain_html_page_is_complete(probe_output, demo_document):
    """A zero-dependency page: every entity, full author names, no stray markup."""
    _, doc = demo_document
    page = probe_output["plain_html.py"]

    balance = TagBalance()
    balance.feed(page)
    balance.close()
    assert balance.problems == []
    assert balance.open_tags == []
    assert BARE_AMPERSAND.findall(page) == []

    for pub in doc["publications"]:
        assert pub["title"] in page, pub["bib_id"]
    for person in doc["people"]:
        assert person["name"] in page, person["id"]
    for project in doc["projects"]:
        assert project["title"] in page, project["id"]

    # The full name, built from the parts, not the document's `B. Brown`.
    assert "Bob Brown" in page
    assert "Carol Côté" in page
    # The venue's Markdown emphasis is rendered, not printed.
    assert "<em>%s</em>" % JOURNAL in page
    assert "*" not in page


# --- cv_tex.py ---------------------------------------------------------------

def tex_entry(fragment, title):
    """The one `\\item` of a LaTeX fragment that carries ``title``."""
    items = [i for i in fragment.split(r"\item ") if title in i]
    assert len(items) == 1, "expected one entry for %r, found %d" % (title, len(items))
    return items[0]


@pytest.mark.xfail(strict=True, reason=(
    "#56: a journal article's `pages`, `volume` and `number` are not emitted "
    "as first-class properties, and `venue` is a composed Markdown string "
    "rather than a venue name plus parts, so the CV entry has no journal "
    "name to emphasise and no volume, issue or page range"))
def test_cv_tex_entry_is_citable(probe_output, demo_document):
    """A CV entry a reader could look the paper up from."""
    _, doc = demo_document
    fragment = probe_output["cv_tex.py"]

    years = [int(y) for y in re.findall(r"\\section\*\{(\d+)\}", fragment)]
    assert years == sorted(set(y["year"] for y in doc["publications"]), reverse=True)
    assert fragment.count(r"\item ") == len(doc["publications"])
    for pub in doc["publications"]:
        entry = tex_entry(fragment, pub["title"])
        assert str(pub["year"]) in entry, pub["bib_id"]
    # Full names, built from the parts, not the document's `B. Brown`.
    assert "Bob Brown" in fragment

    entry = tex_entry(fragment, publication(doc, ARTICLE)["title"])
    assert r"\emph{%s}" % JOURNAL in entry
    assert "%s(%s)" % (VOLUME, NUMBER) in entry
    assert PAGES in entry


# --- csl_json.py -------------------------------------------------------------

@pytest.fixture(scope="module")
def csl_validator():
    with open(CSL_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    return validator(schema)


@pytest.mark.xfail(strict=True, reason=(
    "#56: a journal article's `pages`, `volume` and `number` are not emitted "
    "as first-class properties, `venue` is a composed Markdown string rather "
    "than a venue name plus parts, and the DOI reaches the document only as "
    "the link `doi_url`, so the CSL record has no `container-title`, "
    "`volume`, `issue`, `page` or `DOI`"))
def test_csl_json_records_are_citable(probe_output, demo_document, csl_validator):
    """A CSL-JSON export a citation processor could format a reference from."""
    _, doc = demo_document
    records = json.loads(probe_output["csl_json.py"])

    assert [r["id"] for r in records] == [p["bib_id"] for p in doc["publications"]]
    assert [e.message for e in csl_validator.iter_errors(records)] == []
    by_id = {r["id"]: r for r in records}
    assert by_id[ARTICLE]["type"] == "article-journal"
    # Full names, from the parts, not the document's `B. Brown`.
    assert {"given": "Bob", "family": "Brown"} in by_id[ARTICLE]["author"]

    assert by_id[ARTICLE].get("container-title") == JOURNAL
    assert by_id[ARTICLE].get("volume") == VOLUME
    assert by_id[ARTICLE].get("issue") == NUMBER
    assert by_id[ARTICLE].get("page") == PAGES.replace("--", "-")
    assert by_id[ARTICLE].get("DOI") == DOI


# --- graph.py ----------------------------------------------------------------

def read_graph(text):
    """(nodes, edges) from the probe's tab-separated records."""
    nodes, edges = {}, []
    for line in text.splitlines():
        fields = line.split("\t")
        if fields[0] == "node":
            nodes[fields[1]] = fields[2]
        else:
            edges.append(tuple(fields[1:]))
    return nodes, edges


@pytest.mark.xfail(strict=True, reason=(
    "#56: a `collaborators` entry carries no `id` and an unresolved author "
    "carries no reference to one, only `person_id: null` and a display name "
    "the document states is not an identity, so the five co-authors who are "
    "not lab members cannot be nodes and their authorships cannot be edges"))
def test_graph_covers_every_co_author(probe_output, demo_document):
    """An edge list with a node for every co-author and an edge for every authorship."""
    _, doc = demo_document
    nodes, edges = read_graph(probe_output["graph.py"])

    for kind, source, target in edges:
        assert source in nodes and target in nodes, (kind, source, target)
    assert len([n for n in nodes if n.startswith("work:")]) == len(doc["publications"])
    assert len([n for n in nodes if n.startswith("project:")]) == len(doc["projects"])
    assert ("part_of", "work:" + ARTICLE, "project:homebot") in edges

    people = [n for n in nodes if n.startswith("person:")]
    assert len(people) == len(doc["people"]) + len(doc["collaborators"])
    authorships = sum(len(p["authors"]) for p in doc["publications"])
    assert len([e for e in edges if e[0] == "authored"]) == authorships


# --- The probes themselves ---------------------------------------------------

@pytest.mark.parametrize("name", sorted(PROBE_TESTS))
def test_probe_runs_on_the_demo_document(probe_output, name):
    """Every probe runs to completion against the demo and writes something."""
    assert probe_output[name].strip() != ""


def test_every_probe_is_exercised():
    """No probe can be added to the directory and silently never run."""
    on_disk = sorted(p.name for p in PROBES.glob("*.py"))
    assert on_disk == sorted(PROBE_TESTS)
    module = sys.modules[__name__]
    for name, test in sorted(PROBE_TESTS.items()):
        assert callable(getattr(module, test, None)), "%s names no test" % name


def imported_modules(tree):
    """Every module name an AST imports."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
    return names


def test_no_probe_imports_labdata():
    """A probe reads the emitted document; it does not call the compiler."""
    offenders = []
    for path in sorted(PROBES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += ["%s: %s" % (path.name, m) for m in imported_modules(tree)
                      if m.split(".")[0] == "labdata"]
    assert offenders == []
    # An empty list has to mean "looked and found none".
    assert imported_modules(ast.parse("import labdata.cli")) == {"labdata.cli"}


def code_strings(tree):
    """Every string literal an AST evaluates, leaving out the docstrings.

    Docstrings are prose about the probe and may name anything; a string the
    code actually uses is the one that could open a file or reach into the
    document.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings}


# The inputs a probe must not read, and the one part of the document that is a
# verbatim export rather than structured data. Mining that record for `pages`
# would let a probe pass while proving nothing about the schema.
FORBIDDEN = (".bib", "bibtex", "lab.yaml", "people.yaml", "projects.yaml")


def test_no_probe_reads_the_inputs_or_the_verbatim_export():
    """A probe reads the document handed to it, and reads it as structured data."""
    offenders = []
    for path in sorted(PROBES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += ["%s: %r" % (path.name, s) for s in code_strings(tree)
                      if any(token in s for token in FORBIDDEN)]
        # One `open()` and no other literal path: the only file a probe can
        # read is the one named on its command line.
        opens = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "open"]
        assert len(opens) == 1, "%s opens %d files" % (path.name, len(opens))
    assert offenders == []
    # An empty list has to mean "looked and found none".
    assert code_strings(ast.parse('"""doc"""\nx = pub["bibtex"]')) == {"bibtex"}
