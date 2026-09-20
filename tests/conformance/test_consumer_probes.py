"""The consumer probes of #55, run against the demo output.

Each probe under `examples/consumers/` is a small program that reads the
emitted document and nothing else. It is run here the way a consumer would
run it -- as a subprocess taking the document's path -- so "reads only the
document" is true of how the test invokes it and not only of how it is
written.

The governing rule, stated in `examples/consumers/README.md` and in SPEC.md
section 1: **if a consumer probe cannot be written from the emitted document
alone, that is a schema bug, not a probe bug.** So a probe that cannot
produce correct output is marked `xfail(strict=True)` against the issue that
owns the missing property, and the probe itself is left alone. A probe is
never edited to assert its own incompleteness: it emits the best artifact it
can from what the document gives it, and the tests here say what a correct
artifact would have contained.

**Each probe therefore has its obligations split across two tests.** What the
probe can do today -- the CSL export validating against the published schema,
the CV grouping by year, the graph's edges resolving to declared nodes -- is
asserted in a test that passes. Only the assertions that name the missing
properties sit under `xfail`. Keeping them together would neuter the first
group: a regression in schema validity would surface as the already-expected
`#56` xfail and CI would stay green.

What the static checks catch, and where they stop.

`test_no_probe_imports_labdata` and
`test_no_probe_reads_the_inputs_or_the_reserialized_export` read ordinary
Python and assume it was written in good faith, in the same spirit as
`coverage_check.py`. They catch the honest mistake: a probe that imports the
compiler to get at a value, one that opens an input file beside the document
it was handed, one that reaches into `publication.bibtex` for a field the
document does not emit. They see `import` and `from ... import` statements,
string literals the code evaluates, and calls to the bare builtin `open`.
They do not see `__import__`, `importlib`, `Path.read_text()`, a literal
assembled at run time, or a subprocess. A probe written to get past them
would get past them. The four probes comply by direct inspection, which is
what matters; this is a guard against drift, not a sandbox.
"""

import ast
import copy
import html
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

# Every probe, and the tests that check what it emits: what it can produce
# today, then what it cannot. `test_every_probe_is_exercised` fails if a probe
# is added to the directory and left out of here.
PROBE_TESTS = {
    "plain_html.py": ("test_plain_html_page_is_complete",
                      "test_plain_html_escapes_hostile_text"),
    "cv_tex.py": ("test_cv_tex_fragment_is_well_formed",
                  "test_cv_tex_entry_is_citable"),
    "csl_json.py": ("test_csl_json_export_is_schema_valid",
                    "test_csl_json_records_are_citable"),
    "graph.py": ("test_graph_is_well_formed",
                 "test_graph_covers_every_co_author"),
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


# --- What the document says a name is ----------------------------------------
#
# `author.name` is the document's display form and abbreviates the given name
# unconditionally (`A. Adams`), so it is lossy as a source. The parts preserve
# whatever the input supplied, which is a full given name for most of the demo
# and an initial for the authors whose entry wrote `Brown, B.`. A probe must
# reproduce the parts as it found them -- neither abbreviating a full name nor
# inventing one from an initial -- so the tests below check every authorship
# rather than spot-checking one.

def expected_name_from_parts(author):
    if author.get("literal"):
        return author["literal"]
    parts = [author.get(k) for k in ("given", "von", "family", "suffix")]
    return " ".join(p for p in parts if p)


def expected_csl_name(author):
    if author.get("literal"):
        return {"literal": author["literal"]}
    name = {}
    for csl_key, doc_key in (("given", "given"), ("family", "family"),
                             ("non-dropping-particle", "von"), ("suffix", "suffix")):
        if author.get(doc_key):
            name[csl_key] = author[doc_key]
    return name


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


def esc(text):
    return html.escape(str(text), quote=True)


def keyed_items(markup, class_name):
    """{id: contents} for each `<li class="..." id="...">`. They do not nest."""
    found = re.findall(r'<li class="%s" id="([^"]*)">(.*?)</li>' % class_name,
                       markup, re.S)
    assert len({key for key, _ in found}) == len(found), "duplicate id"
    return dict(found)


def fields(markup, class_name):
    """The contents of each `<span class="...">`. They do not nest either."""
    return re.findall(r'<span class="%s">(.*?)</span>' % class_name, markup, re.S)


def one(markup, class_name):
    found = fields(markup, class_name)
    assert len(found) == 1, "expected one %r, found %d" % (class_name, len(found))
    return found[0]


def shown(markup):
    """The text a reader sees, with the tags taken out."""
    return re.sub(r"<[^>]+>", "", markup)


def test_plain_html_page_is_complete(probe_output, demo_document):
    """Tags nest, and every entity appears once with the fields the document
    gives it, matched to that entity by the id the document supplies."""
    _, doc = demo_document
    page = probe_output["plain_html.py"]

    balance = TagBalance()
    balance.feed(page)
    balance.close()
    assert balance.problems == []
    assert balance.open_tags == []

    # Per work, keyed by `bib_id`: a global count would pass with two works'
    # author lists swapped, which is the whole failure mode worth catching.
    assert {key: {name: one(item, name) for name in ("authors", "title", "year")}
            for key, item in keyed_items(page, "publication").items()} == {
        "work-" + pub["bib_id"]: {
            "authors": ", ".join(esc(expected_name_from_parts(a))
                                 for a in pub["authors"]),
            "title": esc(pub["title"]),
            "year": esc(pub["year"]),
        } for pub in doc["publications"]}

    assert {key: shown(one(item, "name"))
            for key, item in keyed_items(page, "person").items()} == {
        "person-" + person["id"]: esc(person["name"]) for person in doc["people"]}
    assert {key: shown(one(item, "name"))
            for key, item in keyed_items(page, "project").items()} == {
        "project-" + project["id"]: esc(project["title"])
        for project in doc["projects"]}

    # Collaborators are compared as a multiset, not per record: the document
    # gives them no id to key on. That absence is what graph.py fails on.
    assert sorted(shown(one(item, "name"))
                  for item in re.findall(r'<li class="collaborator">(.*?)</li>',
                                         page, re.S)) == sorted(
        esc(c["name"]) for c in doc["collaborators"])

    # The venue's Markdown emphasis is rendered, not printed. Scoped to the
    # venue: a title may legitimately contain an asterisk (SPEC.md section 2
    # names `Informed RRT*`), and that is not this probe's business.
    venues = {key: one(item, "venue")
              for key, item in keyed_items(page, "publication").items()}
    assert sorted(venues) == sorted("work-" + p["bib_id"] for p in doc["publications"])
    assert [v for v in venues.values() if "*" in v] == []
    assert "<em>%s</em>" % JOURNAL in venues["work-" + ARTICLE]


# --- plain_html.py: escaping -------------------------------------------------
#
# SPEC.md section 2 is emphatic that text in the document is untrusted -- a
# title may contain `<`, `&`, `"`, `*` or `$`, and `Informed RRT*` is a real
# one -- and that escaping is the renderer's job. Nothing in the demo contains
# any of those characters, so running the probe on the demo establishes
# nothing about escaping. These values are put into a copy of the document
# instead, and the unmodified probe is run on that. #55 names this probe as
# the Ruby-free renderer where escaping behaviour can be asserted; #36 owns
# escaping across the rest of the project.

HOSTILE_TITLE = '</span></li><script>alert("x")</script> & <b>bold</b>'
HOSTILE_NAME = 'Ada <b>"Lovelace"</b> & Co'
HOSTILE_URL = 'https://example.org/?a=1&b=2" onmouseover="alert(1)'
HOSTILE_LAB = '</title><script>alert("lab")</script>'


class Collector(HTMLParser):
    """Every tag, attribute and run of text a browser would see."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.tags = []
        self.attrs = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, name, value) for name, value in attrs]

    def handle_data(self, data):
        self.text.append(data)


@pytest.fixture(scope="module")
def hostile_page(tmp_path_factory, demo_document):
    """The unmodified probe, run on a document carrying hostile text."""
    _, doc = demo_document
    hostile = copy.deepcopy(doc)
    hostile["lab"]["name"] = HOSTILE_LAB
    hostile["publications"][0]["title"] = HOSTILE_TITLE
    hostile["people"][0]["name"] = HOSTILE_NAME
    hostile["people"][0]["website"] = HOSTILE_URL
    hostile["projects"][0]["description"] = HOSTILE_TITLE
    path = tmp_path_factory.mktemp("hostile") / "lab.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hostile, f, ensure_ascii=False)
    return run_probe("plain_html.py", path)


def test_plain_html_escapes_hostile_text(hostile_page):
    """Hostile text stays text, in the body and inside an attribute."""
    collector = Collector()
    collector.feed(hostile_page)
    collector.close()

    # Body context: the markup in the values never became markup, and came
    # back out as the characters that went in.
    assert "script" not in collector.tags
    assert "b" not in collector.tags
    assert HOSTILE_TITLE in collector.text
    assert HOSTILE_NAME in collector.text
    assert HOSTILE_LAB in collector.text

    # Attribute context: the value is one attribute, not an attribute plus an
    # event handler, and its text survives intact.
    handlers = [a for a in collector.attrs if a[1].startswith("on")]
    assert handlers == []
    assert ("a", "href", HOSTILE_URL) in collector.attrs

    # Tags still nest, and every `&` is an entity reference.
    balance = TagBalance()
    balance.feed(hostile_page)
    balance.close()
    assert balance.problems == []
    assert balance.open_tags == []
    assert BARE_AMPERSAND.findall(hostile_page) == []


# --- cv_tex.py ---------------------------------------------------------------

TEX_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
               "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
               "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def tex(text):
    return "".join(TEX_ESCAPES.get(c, c) for c in str(text))


def tex_entry(fragment, title):
    """The one `\\item` of a LaTeX fragment that carries ``title``."""
    found = [i for i in fragment.split(r"\item ") if tex(title) in i]
    assert len(found) == 1, "expected one entry for %r, found %d" % (title, len(found))
    return found[0]


def test_cv_tex_fragment_is_well_formed(probe_output, demo_document):
    """Grouped by year newest first, one entry per work, each entry opening
    with its authors' names as the document's parts have them."""
    _, doc = demo_document
    fragment = probe_output["cv_tex.py"]

    years = [int(y) for y in re.findall(r"\\section\*\{(\d+)\}", fragment)]
    assert years == sorted({p["year"] for p in doc["publications"]}, reverse=True)
    assert fragment.count(r"\section*{") == fragment.count(r"\begin{enumerate}")
    assert fragment.count(r"\begin{enumerate}") == fragment.count(r"\end{enumerate}")
    assert fragment.count(r"\item ") == len(doc["publications"])

    for pub in doc["publications"]:
        lines = tex_entry(fragment, pub["title"]).splitlines()
        authors = ", ".join(expected_name_from_parts(a) for a in pub["authors"])
        assert lines[0] == tex(authors) + ".", pub["bib_id"]
        assert r"\newblock %s." % tex(pub["title"]) in lines, pub["bib_id"]
        # The year closes a block of its own. Searching the whole entry for it
        # would be satisfied by a DOI that happens to contain the year.
        assert [l for l in lines if l.startswith(r"\newblock")
                and l.endswith("%s." % pub["year"])], pub["bib_id"]


@pytest.mark.xfail(strict=True, reason=(
    "#56: a journal article's `pages`, `volume` and `number` are not emitted "
    "as first-class properties, and `venue` is a composed Markdown string "
    "rather than a venue name plus parts, so the CV entry has no journal "
    "name to emphasise and no volume, issue or page range"))
def test_cv_tex_entry_is_citable(probe_output, demo_document):
    """A CV entry a reader could look the paper up from."""
    _, doc = demo_document
    entry = tex_entry(probe_output["cv_tex.py"], publication(doc, ARTICLE)["title"])

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


def csl_errors(validator, records):
    return [e.message for e in validator.iter_errors(records)]


# The CSL type for each entry type the demo contains, stated here rather than
# read from the probe. `test_csl_json_export_is_schema_valid` checks the demo
# still contains exactly these, so a new entry type cannot slip through
# unmapped.
CSL_TYPE = {"article": "article-journal", "inproceedings": "paper-conference",
            "phdthesis": "thesis", "mastersthesis": "thesis",
            "techreport": "report", "misc": "document"}

# The CSL fields a record can be built from `schema_version` 3 alone. The
# comparison is restricted to these, so #56 adding `container-title` and the
# rest does not have to be anticipated here.
CSL_CORE = ("id", "type", "title", "author", "issued", "abstract", "note", "URL")


def expected_csl_core(pub):
    """What every field of CSL_CORE must hold for ``pub``, or None for absent."""
    return {
        "id": pub["bib_id"],
        "type": CSL_TYPE[pub["entry_type"]],
        "title": pub["title"],
        "author": [expected_csl_name(a) for a in pub["authors"]],
        "issued": {"date-parts": [[pub["year"]]]},
        "abstract": pub["abstract"],
        "note": pub["note"],
        "URL": (pub["url"] or pub["pdf_url"] or pub["doi_url"]
                or pub["arxiv_url"]),
    }


def test_csl_json_export_is_schema_valid(probe_output, demo_document, csl_validator):
    """Valid against the published CSL-JSON schema, and every record carrying
    the fields `schema_version` 3 can supply, matched to its work by id."""
    _, doc = demo_document
    records = json.loads(probe_output["csl_json.py"])

    assert csl_errors(csl_validator, records) == []
    # An empty error list has to mean "looked and found none": a record with a
    # type CSL does not define must be rejected by the same validator.
    assert csl_errors(csl_validator, [{"id": "x", "type": "not-a-csl-type"}]) != []

    assert [r["id"] for r in records] == [p["bib_id"] for p in doc["publications"]]
    assert {p["entry_type"] for p in doc["publications"]} == set(CSL_TYPE)
    by_id = {r["id"]: r for r in records}
    for pub in doc["publications"]:
        record = by_id[pub["bib_id"]]
        assert {k: record.get(k) for k in CSL_CORE} == expected_csl_core(pub), \
            pub["bib_id"]


@pytest.mark.xfail(strict=True, reason=(
    "#56: a journal article's `pages`, `volume` and `number` are not emitted "
    "as first-class properties, `venue` is a composed Markdown string rather "
    "than a venue name plus parts, and the DOI reaches the document only as "
    "the link `doi_url`, so the CSL record has no `container-title`, "
    "`volume`, `issue`, `page` or `DOI`"))
def test_csl_json_records_are_citable(probe_output, demo_document):
    """A CSL record a citation processor could format a full reference from."""
    _, doc = demo_document
    records = json.loads(probe_output["csl_json.py"])
    record = {r["id"]: r for r in records}[ARTICLE]

    assert record.get("container-title") == JOURNAL
    assert record.get("volume") == VOLUME
    assert record.get("issue") == NUMBER
    assert record.get("page") == PAGES.replace("--", "-")
    assert record.get("DOI") == DOI


# --- graph.py ----------------------------------------------------------------

def read_graph(text):
    """(nodes, edges) from the probe's tab-separated records."""
    nodes, edges = {}, []
    for line in text.splitlines():
        record = line.split("\t")
        if record[0] == "node":
            nodes[record[1]] = record[2]
        else:
            edges.append(tuple(record[1:]))
    return nodes, edges


def expected_edges(doc):
    """Every edge the document implies, given the ids it carries today."""
    projects = {p["id"] for p in doc["projects"]}
    edges = []
    for pub in doc["publications"]:
        work = "work:" + pub["bib_id"]
        for author in pub["authors"]:
            if author["person_id"]:
                edges.append(("authored", "person:" + author["person_id"], work))
        edges += [("part_of", work, "project:" + i) for i in pub["project_ids"]
                  if i in projects]
    for project in doc["projects"]:
        edges += [("member_of", "person:" + i, "project:" + project["id"])
                  for i in project["people_ids"]]
    return edges


def test_graph_is_well_formed(probe_output, demo_document):
    """One node per work and per project, and exactly the edges the document
    implies -- every one matched by both endpoints, not counted."""
    _, doc = demo_document
    nodes, edges = read_graph(probe_output["graph.py"])

    assert edges != []
    for kind, source, target in edges:
        assert source in nodes and target in nodes, (kind, source, target)
    assert sorted(n for n in nodes if n.startswith("work:")) == sorted(
        "work:" + p["bib_id"] for p in doc["publications"])
    assert sorted(n for n in nodes if n.startswith("project:")) == sorted(
        "project:" + p["id"] for p in doc["projects"])
    # All three kinds compared as complete tuples. Counting `authored` would
    # pass with two valid edges' endpoints swapped.
    assert sorted(edges) == sorted(expected_edges(doc))


@pytest.mark.xfail(strict=True, reason=(
    "#56: a `collaborators` entry carries no `id`, and no field of an "
    "authorship could reference one if it did -- `author.person_id` is "
    "defined by the schema as the id of a matching person in people.yaml, "
    "which a collaborator is not -- so the five co-authors of the demo who "
    "are not lab members are neither nodes nor endpoints"))
def test_graph_covers_every_co_author(probe_output, demo_document):
    """A node for every co-author and an edge for every authorship."""
    _, doc = demo_document
    nodes, edges = read_graph(probe_output["graph.py"])

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
    for name, tests in sorted(PROBE_TESTS.items()):
        assert tests, "%s names no test" % name
        for test in tests:
            assert callable(getattr(module, test, None)), "%s: no %s" % (name, test)


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
# re-serialized export of the entry rather than a set of first-class
# properties. Mining that record for `pages` would let a probe pass while
# proving nothing about the schema.
FORBIDDEN = (".bib", "bibtex", "lab.yaml", "people.yaml", "projects.yaml")


def test_no_probe_reads_the_inputs_or_the_reserialized_export():
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
