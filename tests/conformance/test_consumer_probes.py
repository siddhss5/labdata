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

**Each probe's obligations are therefore split by kind, not gathered into
one test.** What the probe can do today -- the CSL export validating against
the published schema, the CV grouping by year, the graph's edges resolving to
declared nodes -- is asserted in tests that pass. Only the assertions that
name the missing properties sit under `xfail`, one marker per missing
property rather than one per probe, so each says what it is waiting for and
for whom. Keeping them together would neuter the first
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
would get past them. All five probes comply by direct inspection, which is
what matters; this is a guard against drift, not a sandbox.
"""

import ast
import copy
import html
import inspect
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import jsonschema
import pytest

from .support import REPO_ROOT, case, covers, export, publication


PROBES = REPO_ROOT / "examples" / "consumers"
DEMO_CONFIG = "examples/demo/lab.yaml"
CSL_SCHEMA = REPO_ROOT / "tests" / "vendor" / "csl-data.json"

# Every probe, and the tests that check what it emits: what it can produce
# today, then what it cannot, in that order and however many of each there
# are. `test_every_probe_is_exercised` fails if a probe is added to the
# directory and left out of here.
PROBE_TESTS = {
    "plain_html.py": ("test_plain_html_page_is_complete",
                      "test_plain_html_escapes_hostile_text"),
    "cv_tex.py": ("test_cv_tex_fragment_is_well_formed",
                  "test_cv_tex_entry_is_citable"),
    "csl_json.py": ("test_csl_json_export_is_schema_valid",
                    "test_csl_json_records_are_citable"),
    "graph.py": ("test_graph_is_well_formed",
                 "test_graph_covers_every_co_author",
                 "test_graph_joins_one_co_author_written_two_ways",
                 "test_graph_separates_co_authors_sharing_an_initial",
                 "test_graph_keeps_two_authorships_written_alike_apart"),
    "bibtex_roundtrip.py": ("test_bibtex_roundtrip_entry_is_well_formed",
                            "test_bibtex_roundtrip_reads_only_a_link_the_input_supplied",
                            "test_bibtex_roundtrip_loses_no_field",
                            "test_demo_field_is_in_the_input_and_in_no_property"),
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
# one -- and that escaping is the renderer's job. The demo establishes almost
# nothing about it: outside the `bibtex` record, which no probe reads, its
# only HTML-sensitive character is the apostrophe, in two abstracts and one
# project description, and an apostrophe in element text is harmless. No `<`,
# `>`, `&` or double quote appears in any field the page renders, and no demo
# value reaches an attribute carrying a character that could break out of one.
# (Its venues are full of `*`, which HTML does not treat specially: that is
# the Markdown the page deliberately renders.) So these values are put into a
# copy of the document instead, and the unmodified probe is run on that. #55
# names this probe as the Ruby-free renderer where escaping behaviour can be
# asserted. It mentions #36 alongside, but #36 is about testing the rendered
# Jekyll site and says nothing about escaping, so nothing here relies on it.

HOSTILE_TITLE = '</span></li><script>alert("x")</script> & <b>bold</b>'
HOSTILE_NAME = 'Ada <b>"Lovelace"</b> & Co'
HOSTILE_URL = 'https://example.org/?a=1&b=2" onmouseover="alert(1)'
HOSTILE_LAB = '</title><script>alert("lab")</script>'
# An id reaches an `id="..."` attribute. The schema constrains `bib_id`,
# `person.id` and `project.id` only to a non-empty string
# (`/$defs/person/properties/id`), so this one is valid output of v3.
HOSTILE_ID = 'x" onmouseover="alert(1)'
# Two ids that differ only by an escape. Unescaped they both reach the parser
# as `x&y` and the page has lost the difference between two entities.
AMBIGUOUS_IDS = ("x&y", "x&amp;y")


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
    # The ids too. Nothing that refers to them is updated, because the page
    # follows none of those references -- it renders each entity on its own.
    hostile["publications"][0]["bib_id"] = HOSTILE_ID
    hostile["people"][0]["id"] = HOSTILE_ID
    hostile["projects"][0]["id"] = HOSTILE_ID
    for offset, value in enumerate(AMBIGUOUS_IDS):
        hostile["people"][offset + 1]["id"] = value
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

    # Attribute context: each value is one attribute, not an attribute plus an
    # event handler, and its text survives intact. Both surfaces the page puts
    # a document value into -- `href` and the `id` it gives each entity.
    handlers = [a for a in collector.attrs if a[1].startswith("on")]
    assert handlers == []
    assert ("a", "href", HOSTILE_URL) in collector.attrs
    ids = [value for _, name, value in collector.attrs if name == "id"]
    assert [prefix for prefix in ("work-", "person-", "project-")
            if prefix + HOSTILE_ID not in ids] == []
    assert {"person-" + value for value in AMBIGUOUS_IDS} <= set(ids)
    assert len(set(ids)) == len(ids), "two entities share an id"

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
            "techreport": "report", "misc": "document",
            "incollection": "chapter", "inbook": "chapter",
            "book": "book", "manual": "report"}

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
    """(nodes, edges) from the probe's tab-separated records.

    An `authored` edge is a 4-tuple -- it carries the authorship's position
    after its two endpoints -- and the other two kinds are 3-tuples, so an
    edge is read by its first three fields and its arity is asserted below.
    """
    nodes, edges = {}, []
    for line in text.splitlines():
        record = line.split("\t")
        if record[0] == "node":
            nodes[record[1]] = record[2]
        else:
            edges.append(tuple(record[1:]))
    return nodes, edges


def expected_contributor(author):
    """The node one authorship implies, or None.

    Both references, because the probe follows both: `person_id` for a lab
    member, `collaborator_key` for an authorship that matched nobody. Only
    the first exists today, and this stays a statement about the document
    rather than about `schema_version` 3.
    """
    if author.get("person_id"):
        return "person:" + author["person_id"]
    if author.get("collaborator_key"):
        return "collaborator:" + author["collaborator_key"]
    return None


def expected_edges(doc):
    """Every edge the document implies, given the references it carries."""
    projects = {p["id"] for p in doc["projects"]}
    edges = []
    for pub in doc["publications"]:
        work = "work:" + pub["bib_id"]
        for index, author in enumerate(pub["authors"], 1):
            node = expected_contributor(author)
            if node:
                edges.append(("authored", node, work,
                              str(author.get("position") or index)))
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
    for edge in edges:
        kind, source, target = edge[:3]
        assert source in nodes and target in nodes, edge
    # Every `authored` edge names an authorship, not just a pair of nodes.
    # The emptiness check comes first: the filter below is satisfied by a
    # graph with no `authored` edge at all.
    assert [e for e in edges if e[0] == "authored"] != []
    assert [e for e in edges if e[0] == "authored" and len(e) != 4] == []
    assert sorted(n for n in nodes if n.startswith("work:")) == sorted(
        "work:" + p["bib_id"] for p in doc["publications"])
    assert sorted(n for n in nodes if n.startswith("project:")) == sorted(
        "project:" + p["id"] for p in doc["projects"])
    # Every `person:` node is a person the document declares. A co-author it
    # could not resolve arriving under `person:` would be the namespace
    # widening #56 rejects -- "an unresolved string is never labelled a
    # person" -- and it would quietly satisfy the identity tests below.
    assert sorted(n for n in nodes if n.startswith("person:")) == sorted(
        "person:" + p["id"] for p in doc["people"])
    # All three kinds compared as complete tuples. Counting `authored` would
    # pass with two valid edges' endpoints swapped.
    assert sorted(edges) == sorted(expected_edges(doc))


@pytest.mark.xfail(strict=True, reason=(
    "#56: a `collaborators` entry carries no key of its own, and no field of "
    "an authorship could reference one if it did -- `author.person_id` is "
    "defined by the schema as the id of a matching person in people.yaml, "
    "which a collaborator is not -- so the eleven authorships the demo cannot "
    "resolve, grouped today into seven entries, are neither nodes nor "
    "endpoints"))
def test_graph_covers_every_co_author(probe_output, demo_document):
    """A node for every co-author and an edge for every authorship."""
    _, doc = demo_document
    nodes, edges = read_graph(probe_output["graph.py"])

    people = [n for n in nodes if n.startswith("person:")]
    assert len(people) == len(doc["people"]) + len(doc["collaborators"])
    authorships = sum(len(p["authors"]) for p in doc["publications"])
    assert len([e for e in edges if e[0] == "authored"]) == authorships


# --- bibtex_roundtrip.py -----------------------------------------------------
#
# The field-loss probe of #69. It re-emits one BibTeX entry per work from the
# document's first-class properties, and the tests below ask the separate
# questions that artifact answers: what it can still write, what it cannot,
# what each individual field the demo carries for #69 does, and where it is
# allowed to look for the answer.
#
# It is deliberately **not** a value round trip. LaTeX is converted to Unicode
# on the way in and the conversion is one-way, so `C{\^o}t{\'e}` comes back as
# `Côté` and comparing values would assert something false. What the loss test
# asks instead is whether every *field name* the input carried is still
# reachable, which is the list #56's field list has to be built from.
#
# The reader below is used on both sides: on what the probe wrote, and on the
# demo's own .bib files. Only the test reads those; the probe never does.

DEMO_BIB = REPO_ROOT / "examples" / "demo" / "bib"

ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s{}]+)\s*,")
FIELD_RE = re.compile(r"^\s*(\w+)\s*=\s*(.*)$", re.S)
NOT_ENTRIES = ("string", "comment", "preamble")


def balanced(text, start):
    """The body of the brace group already open at ``start``."""
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    return text[start:]


def split_top(text, separator):
    """``text`` split on ``separator``, at brace depth zero only."""
    parts, depth, current = [], 0, []
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def unwrap(value):
    """One field value, with its delimiters off and its whitespace collapsed."""
    value = value.strip()
    if len(value) >= 2 and value[0] + value[-1] in ("{}", '""'):
        value = value[1:-1]
    return " ".join(value.split())


def read_entries(text):
    """{citation key: (entry type, {field name: value})}.

    Enough of a BibTeX reader for the demo's own files and for what the probe
    writes, and nothing more is asked of it. `test_bibtex_roundtrip_entry_is_
    well_formed` checks it can see the fields the loss test looks for, so an
    empty answer cannot pass for "nothing was lost".
    """
    entries = {}
    for match in ENTRY_RE.finditer(text):
        kind = match.group(1).lower()
        if kind in NOT_ENTRIES:
            continue
        fields = {}
        for chunk in split_top(balanced(text, match.end()), ","):
            found = FIELD_RE.match(chunk)
            if found:
                fields[found.group(1).lower()] = unwrap(found.group(2))
        entries[match.group(2)] = (kind, fields)
    return entries


def source_entries():
    """Every entry of the demo's input, read from the .bib files themselves."""
    found = {}
    for path in sorted(DEMO_BIB.glob("*.bib")):
        found.update(read_entries(path.read_text(encoding="utf-8")))
    return found


def expected_bibtex_name(author):
    """One name back in BibTeX's own order, from the document's parts."""
    if author.get("literal"):
        return "{%s}" % author["literal"]
    family = " ".join(p for p in (author.get("von"), author.get("family")) if p)
    return ", ".join(p for p in (family, author.get("suffix"), author.get("given")) if p)


def expected_entry_fields(pub):
    """Exactly the fields `schema_version` 3 can still put in an entry."""
    values = {
        "author": " and ".join(expected_bibtex_name(a) for a in pub["authors"]),
        "title": pub["title"],
        "year": str(pub["year"]),
        "abstract": pub["abstract"],
        "note": pub["note"],
        # One input field the compiler routes to one of two properties by
        # looking at the host, so both hold part of the answer.
        "url": pub["url"] or pub["video_url"],
    }
    return {name: " ".join(str(value).split())
            for name, value in values.items() if value}


@covers("probe.roundtrip_shape")
def test_bibtex_roundtrip_entry_is_well_formed(probe_output, demo_document):
    """One entry per work, keyed and typed by the document, carrying exactly
    the fields the document can still supply -- matched per work, because a
    count would pass with two works' fields swapped."""
    _, doc = demo_document
    entries = read_entries(probe_output["bibtex_roundtrip.py"])

    assert {key: kind for key, (kind, _) in entries.items()} == {
        p["bib_id"]: p["entry_type"] for p in doc["publications"]}
    assert {key: fields for key, (_, fields) in entries.items()} == {
        p["bib_id"]: expected_entry_fields(p) for p in doc["publications"]}

    # The reader has to be able to see a field in the demo's own input, or
    # the loss test below would pass by finding nothing at all to lose.
    source = source_entries()
    assert sorted(source) == sorted(entries)
    assert source["brown2025tidy"][0] == "article"
    assert {"pages", "volume", "number", "doi", "month", "issn"} <= set(
        source["brown2025tidy"][1])
    assert source["adams2022survey"][1]["editor"] == "Quinn, Quentin and Silva, Sofia"


# The one field the probe is not asked to put back. It is named here on its
# own, never matched by a pattern, so a field that stops reaching the document
# has to show up in the failure below rather than be absorbed by a wildcard.
#
#   project   labdata's own tag field, not part of BibTeX. It does reach the
#             document, as `project_ids`, and the `fields.project` row of
#             tests/COVERAGE.md asserts that; this probe re-emits
#             bibliographic fields, so it is not expected back here.
IGNORED_SOURCE_FIELDS = ("project",)


@covers("probe.field_loss", xfail="#56", owns=(), because=(
    "a work carries no `pages`, `volume`, `number`, `publisher`, `address`, "
    "`series`, `edition`, `editor`, `chapter`, `month`, `organization`, "
    "`isbn`, `issn` or `howpublished` property; its `doi` and `eprint` reach "
    "the document only as the links built from them, which are not "
    "invertible; and the name of its journal, proceedings, collection, "
    "school, institution or issuing body is fused into the composed `venue` "
    "string, which a probe may not take apart"))
def test_bibtex_roundtrip_loses_no_field(probe_output, demo_document):
    """Every field name of every source entry reaches a first-class property.

    The message is the deliverable: it names each entry that lost a field and
    every field name lost across the demo, which is the list #56 builds its
    field list from.
    """
    entries = read_entries(probe_output["bibtex_roundtrip.py"])
    lost = {}
    for key, (kind, fields) in source_entries().items():
        missing = sorted(set(fields) - set(IGNORED_SOURCE_FIELDS)
                         - set(entries[key][1]))
        if missing:
            lost[key] = (kind, missing)
    every = sorted({name for _, names in lost.values() for name in names})
    assert lost == {}, "\n".join(
        ["%d of %d demo entries lose at least one field." % (len(lost), len(entries)),
         "",
         "Every field name lost, across the demo (%d):" % len(every),
         "  " + ", ".join(every),
         "",
         "Per entry:"]
        + ["  %s (%s): %s" % (key, kind, ", ".join(names))
           for key, (kind, names) in sorted(lost.items())])



# --- bibtex_roundtrip.py: where a link is allowed to count -------------------
#
# The probe reads a link as evidence that the entry's own `url` field reached
# the document only when the document says the link came from the input. The
# demo cannot exercise that rule at all: it still carries flat `url` and
# `video_url` properties, which the probe reaches first, so the branch would
# go untested in CI and could be lost in a refactor without anything turning
# red. The properties are therefore cleared in a copy of the document and one
# link put in their place, one origin per work, and the **unmodified** probe
# is run on that -- the same arrangement `hostile_page` uses above.

# (link kind, the origin the record states, whether the probe may read it).
# #56 section 3 makes `origin` an open string over `input`, `sidecar`,
# `enrichment`, `inferred` and `derived`; only the first says the entry's own
# field is what put the link there. A record that states no origin is not
# read either: the question is what the document says, and silence is not an
# answer.
LINK_ORIGINS = (
    ("url", "input", True),
    ("video", "input", True),
    ("url", "enrichment", False),
    ("url", "sidecar", False),
    ("url", "derived", False),
    ("url", "inferred", False),
    ("url", None, False),
)
LINK_URL = "https://links.invalid/%s/%s"


@pytest.fixture(scope="module")
def link_origin_entries(tmp_path_factory, demo_document):
    """(the works used, what the probe wrote) for one origin per work."""
    _, doc = demo_document
    altered = copy.deepcopy(doc)
    works = altered["publications"][:len(LINK_ORIGINS)]
    assert len(works) == len(LINK_ORIGINS), "the demo is too small for this"
    for pub, (kind, origin, _) in zip(works, LINK_ORIGINS):
        pub["url"] = None
        pub["video_url"] = None
        record = {"url": LINK_URL % (kind, origin), "label": None,
                  "verification": {"status": "unchecked", "checked_at": None}}
        if origin is not None:
            record["origin"] = origin
        pub["links"] = {kind: [record]}
    path = tmp_path_factory.mktemp("links") / "lab.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(altered, f, ensure_ascii=False)
    return [p["bib_id"] for p in works], read_entries(
        run_probe("bibtex_roundtrip.py", path))


@covers("probe.link_origin")
def test_bibtex_roundtrip_reads_only_a_link_the_input_supplied(link_origin_entries):
    """`url` comes back from a link the document attributes to the input, and
    from no other, whatever kind it is filed under.

    Both directions in one comparison: a probe that ignored `links` entirely
    would fail on the two that must survive, and one that ignored `origin`
    would fail on the five that must not.
    """
    keys, entries = link_origin_entries
    assert [entries[key][1].get("url") for key in keys] == [
        LINK_URL % (kind, origin) if survives else None
        for kind, origin, survives in LINK_ORIGINS]

# --- The demo's four entry types with no venue rule --------------------------
#
# `format_venue()` has a rule for article, inproceedings, the two theses,
# techreport and misc, and falls through to the bare year for everything else.
# The demo now contains four such types, and what that fallthrough costs is
# the whole container: the collection, the book, the publisher and the issuing
# organization reach no property at all. It is recorded here because it is the
# same loss the probe above reports, seen from the compiler's side.

# {bib_id: (entry type, the field naming its container, that field's value)}.
# The value is taken from examples/demo/bib/books.bib, which no probe reads,
# so the absence below is checked against the text the input actually wrote.
NO_VENUE_RULE = {
    "adams2022survey": ("incollection", "booktitle",
                        "Handbook of Robots in the Home"),
    "hughes2021gaits": ("inbook", "publisher", "Example Technical Publishing"),
    "adams2023handbook": ("book", "publisher", "Example Academic Press"),
    "ingram2019toolkit": ("manual", "organization",
                          "Example University Personal Robotics Laboratory"),
}


def first_class_values(pub):
    """Every string anywhere in a work, except inside the re-serialized export.

    **Recursive on purpose.** The only record left out is the re-serialized
    export, which is a copy of the entry and holds every field read or not,
    so a search that included it could never find anything absent. Everything
    else is walked to any depth, because that is where a field that has
    stopped being lost would appear: `editors` is a list of name objects,
    `identifiers` is a map from scheme to a list of strings, and a structured
    `venue` is an object. A check that looked only at the work's own string
    properties would call every one of those absent and would stay green
    after the very loss it pins had been fixed.
    """
    found = []

    def walk(value):
        if isinstance(value, dict):
            for name, inner in value.items():
                if name != "bibtex":
                    walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)
        elif isinstance(value, str):
            found.append(value)

    walk(pub)
    return found


@covers("types.incollection", "types.inbook", "types.book", "types.manual")
def test_entry_types_without_a_venue_rule_degrade_to_the_year(demo_document):
    """Each of the four is emitted, its venue is the year and nothing else,
    and the field naming its container reaches no property at all."""
    _, doc = demo_document
    for bib_id, (entry_type, field, container) in sorted(NO_VENUE_RULE.items()):
        pub = publication(doc, bib_id)
        assert pub["entry_type"] == entry_type, bib_id
        assert pub["venue"] == str(pub["year"]), bib_id
        # The claim the COVERAGE row makes: not merely absent under its own
        # name, but nowhere in the work at all.
        assert field not in pub, bib_id
        assert [value for value in first_class_values(pub)
                if container in value] == [], bib_id
        # The value is in the input, so the search above looked for something
        # that is really there.
        assert source_entries()[bib_id][1][field] == container, bib_id
    # A type that does have a rule still composes one, so the check above is
    # about these four rather than about every venue in the demo.
    article = publication(doc, ARTICLE)
    assert article["venue"] != str(article["year"])


# --- Fields the demo carries that reach no property --------------------------
#
# One row per field, each bound to an assertion that **passes**: the field is
# in the input and is nowhere in the work. The field-loss probe reports all
# of them together, but that test is xfailed, so deleting one of these
# fixtures would not turn anything red there. These give each field its own
# grip: remove the fixture and the row's own test fails.

def value_locations(pub, values):
    """Every path in a work whose leaf is one of ``values``.

    Three properties of this search, each of them load-bearing:

    **Leaves, not keys.** A container that exists but is empty -- `#56`
    makes `identifiers` always present, so `identifiers: {}` is what a work
    with no identifier looks like -- and a declared-but-null flat property
    are not survivals of anything. Asking whether a key is present would call
    both of them a recovery and turn these rows red while the field was
    exactly as lost as before.

    **Equality, not containment.** `chapter = {9}` and the ISBN
    `978-1-00-000003-5` are on the same work, and `"9"` is a substring of
    that ISBN; a substring search would report the chapter recovered the
    moment the ISBN arrived. Every needle here is an atomic value, so exact
    equality is the right relation and it is also the one that cannot
    collide across fields.

    **Any depth, and the path is the answer.** `editors` is a list of name
    objects, `identifiers` a map from scheme to a list, a structured `venue`
    an object: a search of the work's own string properties would miss all
    three, which is exactly where a field goes when it stops being lost. The
    path each hit is found at is returned rather than a bare count, so a
    failure says *where* the field turned up. Only the re-serialized export
    is skipped, because it holds every field read or not.
    """
    found = []

    def walk(value, path):
        if isinstance(value, dict):
            for name, inner in value.items():
                if name != "bibtex":
                    walk(inner, path + "/" + str(name))
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                walk(inner, path + "/" + str(index))
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            if str(value) in values:
                found.append("%s = %r" % (path, value))

    walk(pub, "")
    return sorted(found)


# (case, entry, source field, the atomic values that would mean it survived).
# For `editor` those are the editors' own name parts rather than the one
# combined string the entry wrote, because a document that stopped losing the
# field would carry them parsed -- `editors` is a list of name objects, and
# `Quinn, Quentin and Silva, Sofia` appears nowhere in it.
UNREAD_FIELDS = [
    case("fields.editor", "adams2022survey", "editor",
         ("Quinn", "Quentin", "Silva", "Sofia")),
    case("fields.month", "adams2022survey", "month", ("March",)),
    case("fields.chapter", "hughes2021gaits", "chapter", ("9",)),
    case("fields.isbn", "adams2023handbook", "isbn", ("978-1-00-000002-8",)),
    case("fields.organization", "ingram2019toolkit", "organization",
         ("Example University Personal Robotics Laboratory",)),
    case("fields.issn", "brown2025tidy", "issn", ("2999-0001",)),
    case("fields.howpublished", "fischer2025benchmark", "howpublished",
         ("Dataset and evaluation protocol on the project site",)),
]


@pytest.mark.parametrize("case_id,bib_id,field,values", UNREAD_FIELDS)
def test_demo_field_is_in_the_input_and_in_no_property(probe_output, demo_document,
                                                       case_id, bib_id, field,
                                                       values):
    """The input entry carries the field, and the work carries it nowhere.

    Asked two ways, because one is not enough to mean "in no property":

    1. No value anywhere in the work, at any depth, is the field's -- the
       flat property, `identifiers[scheme]`, a parsed `editors` entry and a
       structured `venue` are all reached by the same walk, and all four are
       compared by value rather than by whether their container exists.
    2. The round-trip probe, which looks in every one of those places, still
       cannot emit the field. That is the consumer-visible statement, and the
       one a reader of `tests/COVERAGE.md` is actually promised.

    `test_field_absence_reads_the_value_not_the_container` pins both
    directions of the first: which additions must turn this row red, and
    which must leave it alone.
    """
    _, doc = demo_document
    source_value = source_entries()[bib_id][1][field]
    # The needles are really in the input, so the searches below looked for
    # something that exists rather than for nothing.
    assert [one for one in values if one not in source_value] == [], bib_id

    assert value_locations(publication(doc, bib_id), values) == [], bib_id
    emitted = read_entries(probe_output["bibtex_roundtrip.py"])[bib_id][1]
    assert field not in emitted, bib_id


# What each row must and must not react to. The left column is a change made
# to one work of a copy of the demo document; the right is the set of rows
# above that must then find the field. A row that reacts to the wrong change
# would send #56 after a loss that is still exactly as lost, or tell it a
# loss had been closed when it had not.
EDITORS = [{"given": "Quentin", "von": None, "family": "Quinn", "suffix": None,
            "literal": None, "person_id": None},
           {"given": "Sofia", "von": None, "family": "Silva", "suffix": None,
            "literal": None, "person_id": None}]
ABSENCE_PROBES = [
    # A container that exists is not a field that survived.
    ("an empty identifiers map", "adams2023handbook", {"identifiers": {}}, ()),
    ("a declared but null chapter", "hughes2021gaits", {"chapter": None}, ()),
    ("an empty editors list", "adams2022survey", {"editors": []}, ()),
    # Nor is a different field's value, even one the other is a substring of.
    ("the isbn of the work that carries the chapter", "hughes2021gaits",
     {"identifiers": {"isbn": ["978-1-00-000003-5"]}}, ()),
    # The field's own value, in the place #56 puts it, is.
    ("the isbn, as an identifier", "adams2023handbook",
     {"identifiers": {"isbn": ["978-1-00-000002-8"]}}, ("fields.isbn",)),
    ("the issn, as an identifier", "brown2025tidy",
     {"identifiers": {"issn": ["2999-0001"]}}, ("fields.issn",)),
    ("parsed editors", "adams2022survey", {"editors": EDITORS},
     ("fields.editor",)),
    ("the organization, as a structured venue", "ingram2019toolkit",
     {"venue": {"kind": "institution",
                "name": "Example University Personal Robotics Laboratory"}},
     ("fields.organization",)),
    ("a flat chapter", "hughes2021gaits", {"chapter": "9"}, ("fields.chapter",)),
    ("a flat chapter, as a number", "hughes2021gaits", {"chapter": 9},
     ("fields.chapter",)),
    ("a flat month", "adams2022survey", {"month": "March"}, ("fields.month",)),
    ("flat howpublished", "fischer2025benchmark",
     {"howpublished": "Dataset and evaluation protocol on the project site"},
     ("fields.howpublished",)),
]


@pytest.mark.parametrize("label,bib_id,change,flips",
                         [pytest.param(*p, id=p[0]) for p in ABSENCE_PROBES])
def test_field_absence_reads_the_value_not_the_container(demo_document, label,
                                                         bib_id, change, flips):
    """Every row above reacts to its own field's value and to nothing else.

    Run over *all* the rows for each change, not just the one expected to
    move, so a row that reacted to a neighbour's value would be caught here
    rather than after #56 had acted on it.
    """
    _, doc = demo_document
    altered = copy.deepcopy(doc)
    for pub in altered["publications"]:
        if pub["bib_id"] == bib_id:
            pub.update(change)

    found = set()
    for row in UNREAD_FIELDS:
        case_id, row_id, _, values = row.values
        if value_locations(publication(altered, row_id), values):
            found.add(case_id)
    assert found == set(flips), label
    # The unaltered document finds nothing, so the answer above is the
    # change's doing and not the document's.
    assert {row.values[0] for row in UNREAD_FIELDS
            if value_locations(publication(doc, row.values[1]),
                               row.values[3])} == set()


# --- graph.py: who the co-authors are ----------------------------------------
#
# The four identity scenarios of #69, taken from examples/demo/bib/books.bib
# and examples/demo/bib/conference.bib, which no probe reads. They are stated
# here because the document cannot state them: that is the finding.
#
# Priya Patel is one external co-author on three works, written `Patel, Priya`
# on two of them and `Patel, P.` on the third. Pradeep Patel is a different
# person on a fourth work, sharing her first initial and her family name. The
# two `Lee, Lin` co-authors of `nolan2020stairs` are two different people
# written identically on one work.
#
# **The three scenarios are filed against two different issues, because they
# are promised by two different issues.** #56 settles a grouping over
# unresolved authorships keyed on the *normalised full name*, and says in as
# many words that the policy is #24's and that this key over-splits. So:
#
#   - Separating `Pradeep Patel` from `Priya Patel` is #56's. Under a
#     normalised full-name key `pradeep patel` and `priya patel` are two
#     keys, where today's abbreviated `p patel` is one.
#   - Keeping the two `Lee, Lin` authorships apart is #56's, but not by
#     making them two contributors: any grouping by name puts them together,
#     and #56's key is a grouping by name. What #56 promises is that the
#     authorship is the primary contributor record, addressed by
#     `(work.bib_id, author.position)`, so the two occurrences survive.
#   - Joining `Patel, Priya` and `Patel, P.` is **not** #56's, and asserting
#     it against #56 would be a marker #56 could not remove. A normalised
#     full-name key splits those two spellings by construction. #24 is the
#     issue that groups collaborators by full name *and* gives external
#     collaborators aliases, which is the mechanism that joins two spellings
#     of one person; #25 layers explicit overrides and ORCID on top of it.
#
# The scenarios are asserted over the node and edge sets `graph.py` already
# builds, per #69's own recommendation, rather than in a fifth probe. Nothing
# below reads a node's label or a collaborator's spelling: a contributor is
# identified only by the works it authored, so the assertions survive #56
# changing what the display form of a name is.

ONE_PERSON_WORKS = ("adams2022survey", "adams2023handbook", "ingram2019toolkit")
OTHER_PERSON_WORK = "hughes2021gaits"
SHARED_FAMILY = "Patel"
SAME_NAME_WORK = "nolan2020stairs"
SAME_NAME_FAMILY, SAME_NAME_GIVEN = "Lee", "Lin"


def authors_named(pub, family, given=None):
    return [a for a in pub["authors"] if a["family"] == family
            and (given is None or a["given"] == given)]


@covers("probe.identity_fixtures")
def test_identity_fixtures_are_present(demo_document):
    """The document carries all four scenarios the graph tests assert over.

    A strict xfail keeps failing when its fixture is deleted, so without this
    the three markers below could go on looking like findings about the
    schema after the works they are about had gone.
    """
    _, doc = demo_document

    # One person on three works in two spellings, and a second person with
    # the same first initial and family name on a fourth.
    spellings = {}
    for bib_id in ONE_PERSON_WORKS + (OTHER_PERSON_WORK,):
        found = authors_named(publication(doc, bib_id), SHARED_FAMILY)
        assert len(found) == 1, bib_id
        assert found[0]["person_id"] is None, bib_id
        spellings.setdefault(found[0]["given"], []).append(bib_id)
    assert {given: sorted(works) for given, works in spellings.items()} == {
        "Priya": ["adams2022survey", "adams2023handbook"],
        "P.": ["ingram2019toolkit"],
        "Pradeep": ["hughes2021gaits"],
    }
    # Every one of them writes the same display name today, which is what
    # makes the grouping question a real one rather than a hypothetical.
    assert {a["name"] for bib_id in ONE_PERSON_WORKS + (OTHER_PERSON_WORK,)
            for a in authors_named(publication(doc, bib_id), SHARED_FAMILY)} == {
        "P. Patel"}

    # Two different people under one written name, on one work.
    alike = authors_named(publication(doc, SAME_NAME_WORK),
                          SAME_NAME_FAMILY, SAME_NAME_GIVEN)
    assert len(alike) == 2
    assert [a["person_id"] for a in alike] == [None, None]
    # They are the only external co-authors of that work, and they sit at
    # adjacent positions in its author list, which is what the authorship
    # test below reads.
    assert [a for a in publication(doc, SAME_NAME_WORK)["authors"]
            if a["person_id"] is None] == alike
    assert alike_indexes(publication(doc, SAME_NAME_WORK)) == [2, 3]


def alike_indexes(pub):
    """Where the two identically written authorships sit in the author list.

    Read off the list, not off a `position` property: this says what the
    *fixture* looks like, and it has to keep saying it against a document
    that declares no position -- which is every document today. What the
    document declares is the separate question
    `test_graph_keeps_two_authorships_written_alike_apart` asks.
    """
    return [i for i, a in enumerate(pub["authors"], 1)
            if a["family"] == SAME_NAME_FAMILY and a["given"] == SAME_NAME_GIVEN]


def external_contributors(edges):
    """{node: the works it authored} for every contributor in the
    `collaborator:` namespace.

    Selected by namespace, not by "is not in `people`". A co-author reaching
    the graph under `person:` is the semantic widening #56 rejects, and these
    tests must not be satisfied by it: a grouping over unresolved authorships
    is not a person, whatever it is keyed on. That every `person:` node is a
    declared person is asserted in `test_graph_is_well_formed`, which passes,
    so this selection cannot quietly miss one either.
    """
    authored = {}
    for edge in edges:
        if edge[0] == "authored" and edge[1].startswith("collaborator:"):
            authored.setdefault(edge[1], set()).add(edge[2].split(":", 1)[1])
    return authored


@covers("probe.identity_one_person", xfail="#24", owns=(), because=(
    "one external co-author written `Patel, Priya` on two works and "
    "`Patel, P.` on a third is not one contributor under any key the "
    "document has or #56 gives it -- today's abbreviated key merges her with "
    "a different person, and #56's normalised full-name key splits her in "
    "two spellings by construction. Joining the spellings of one external "
    "person needs the full-name grouping *plus* the collaborator aliases "
    "this issue adds"))
def test_graph_joins_one_co_author_written_two_ways(probe_output, demo_document):
    """One external person on three works is one contributor, holding exactly
    those three works.

    Stated in both directions on purpose: exactly one external contributor
    touches any of the three, and its work set is exactly those three. A
    weaker form -- one contributor holding all three -- would pass with a
    second contributor holding one of them as well.
    """
    _, doc = demo_document
    _, edges = read_graph(probe_output["graph.py"])
    authored = external_contributors(edges)

    joined = [node for node, works in authored.items()
              if works & set(ONE_PERSON_WORKS)]
    assert len(joined) == 1, sorted(authored.items())
    assert authored[joined[0]] == set(ONE_PERSON_WORKS)


@covers("probe.identity_distinct_people", xfail="#56", owns=(), because=(
    "`collaborators` is keyed on the abbreviated display name, so `P. Patel` "
    "the author of three works and `P. Patel` the author of a fourth are one "
    "entry with one count and one `last_year`; the authorships keep their "
    "given names apart but the entry offers no key that does, and carries "
    "none of its own, so a consumer cannot make two contributors of them"))
def test_graph_separates_co_authors_sharing_an_initial(probe_output, demo_document):
    """Two external people who share a first initial and a family name are
    separate contributors, and neither holds any of the other's works.

    Both work sets are pinned exactly, in both directions: requiring only
    that the two differ would be satisfied by a contributor that had taken
    one of the other's works as well, which is the merge this is about.
    """
    _, doc = demo_document
    _, edges = read_graph(probe_output["graph.py"])
    authored = external_contributors(edges)

    other = [node for node, works in authored.items() if OTHER_PERSON_WORK in works]
    assert len(other) == 1, sorted(authored.items())
    assert authored[other[0]] == {OTHER_PERSON_WORK}
    shared = [node for node, works in authored.items()
              if works & set(ONE_PERSON_WORKS)]
    assert shared != [], sorted(authored.items())
    assert set(shared) & set(other) == set()


@covers("probe.identity_authorship", xfail="#56", owns=(), because=(
    "two different people listed on one work under one written name are "
    "counted twice into a single `collaborators` entry, and neither "
    "occurrence is addressable: an authorship carries no `position` and no "
    "reference to the contributor it was grouped into, so the two reach a "
    "consumer as one indistinguishable pair"))
def test_graph_keeps_two_authorships_written_alike_apart(probe_output, demo_document):
    """Two different people written identically on one work stay two
    authorships of it, told apart by their positions.

    Not two contributors: any grouping by name puts them together, and #56's
    normalised full-name key is a grouping by name. What has to survive is
    the occurrence -- the authorship addressed by its work and its position
    -- because that is the record a consumer that distrusts the grouping
    falls back to.
    """
    _, doc = demo_document
    _, edges = read_graph(probe_output["graph.py"])
    pub = publication(doc, SAME_NAME_WORK)

    # The document *declares* the position of each of the two authorships.
    # Asserted against the document, not against the graph: the probe falls
    # back to the list index when no position is declared -- faithfully, and
    # that fallback stays -- so a position column in the output is no
    # evidence the document said anything, and this marker names `position`
    # as one of the two properties it is waiting for.
    declared = [a.get("position") for a in authors_named(
        pub, SAME_NAME_FAMILY, SAME_NAME_GIVEN)]
    assert [p for p in declared if p is None] == [], declared
    assert len(set(declared)) == len(declared) == 2, declared

    alike = [edge for edge in edges if edge[0] == "authored"
             and edge[2] == "work:" + SAME_NAME_WORK
             and edge[1].startswith("collaborator:")]
    assert len(alike) == 2, alike
    # One grouping, two authorships: both edges leave the *same* contributor,
    # because any grouping by name puts these two together. Two endpoints
    # would be a different answer, and the wrong one.
    assert len({edge[1] for edge in alike}) == 1, alike
    # And the two records are told apart by the positions the document
    # declared, not by the order the probe happened to read them in.
    assert sorted(edge[3] for edge in alike) == sorted(str(p) for p in declared)


# --- The probes themselves ---------------------------------------------------

@pytest.mark.parametrize("name", sorted(PROBE_TESTS))
def test_probe_runs_on_the_demo_document(probe_output, name):
    """Every probe runs to completion against the demo and writes something."""
    assert probe_output[name].strip() != ""


def reads_probe_output(source, name):
    """True when ``source`` subscripts the `probe_output` fixture with ``name``.

    An expression, not a mention: a probe's name in a comment or a docstring
    is prose, and prose is not a test reading what the probe wrote.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id == "probe_output" \
                and isinstance(node.slice, ast.Constant) and node.slice.value == name:
            return True
    return False


def test_every_probe_is_exercised():
    """No probe can be added to the directory and silently never run, and
    none can be wired to tests that never look at what it wrote.

    The second half is what `PROBE_TESTS` alone cannot promise: its keys are
    how `probe_output` is keyed, so a probe none of whose named tests reads
    `probe_output[<its name>]` is a probe that ran and was never read.
    """
    on_disk = sorted(p.name for p in PROBES.glob("*.py"))
    assert on_disk == sorted(PROBE_TESTS)
    module = sys.modules[__name__]
    for name, tests in sorted(PROBE_TESTS.items()):
        assert tests, "%s names no test" % name
        sources = []
        for test in tests:
            found = getattr(module, test, None)
            assert callable(found), "%s: no %s" % (name, test)
            sources.append(inspect.getsource(found))
        assert [s for s in sources if reads_probe_output(s, name)], \
            "%s: none of %s reads its output" % (name, ", ".join(tests))
    # A mention that is not a read has to fail the check above, or it
    # establishes nothing: this is the shape it must reject.
    assert not reads_probe_output('def t():\n    """graph.py"""\n    pass\n',
                                  "graph.py")
    assert reads_probe_output('def t(probe_output):\n'
                              '    return probe_output["graph.py"]\n', "graph.py")


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
