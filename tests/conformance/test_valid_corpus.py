"""Field-level checks on the valid corpus (tests/corpus/valid/).

Each table row is ``case(case_id, bib_key, field_path, expected)`` and checks
one field of one exported publication. Rows marked ``xfail="#N"`` describe
the intended behavior, which issue #N delivers.
"""

import pytest

from .support import (
    VALID, AllOf, Contains, Excludes, assert_field, case, covers, item, publication,
)


def check_publication(output, bib_key, path, expected):
    assert_field(publication(output, bib_key), path, expected, where=f"{bib_key}: ")


# --- @string macros ----------------------------------------------------------

STRINGS = [
    case("strings.macro", "str-repeat", "venue", Contains("Robotics Venue")),
    case("strings.repeat_last_wins", "str-repeat", "venue", Excludes("Old Robotics Venue")),
    case("strings.concat", "str-concat", "title", "Joined Title"),
    case("strings.concat", "str-concat", "venue",
         AllOf(Contains("Proceedings of the Fictional Conference"), Excludes("Old"))),
    case("strings.macro_journal", "str-journal", "venue",
         Contains("Journal of Fictional Robots Letters")),
    case("strings.defined_once", "str-once", "venue",
         Contains("Journal of Fictional Robots")),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", STRINGS)
def test_strings(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


@covers("strings.redefined_report", xfail="#21", owns=())
def test_redefined_strings_reported_once(valid_validate):
    """The three redefined macros are reported together by labdata, not one by one."""
    lines = valid_validate.output.splitlines()
    summary = [line for line in lines if all(m in line for m in ("rss", "cfx", "jfx"))]
    assert len(summary) == 1, valid_validate.output


@covers("strings.defined_once")
def test_macro_defined_once_is_not_reported(valid_validate, valid_export):
    """A macro defined exactly once is used, and nothing is said about it."""
    run, _ = valid_export
    for output in (valid_validate.output, run.output):
        assert "jrl" not in output, output


# --- Names and identity ------------------------------------------------------

NAMES = [
    case("names.last_first", "name-last-first", "authors.0.name", "A. Adams"),
    case("names.last_first", "name-last-first", "authors.0.person_id", "aadams"),
    case("names.first_last", "name-first-last", "authors.0.name", "B. Brown"),
    case("names.first_last", "name-first-last", "authors.0.person_id", "bbrown"),
    case("names.particle_last_first", "name-particle-van", "authors.0.name", "V. van den Berg"),
    case("names.particle_last_first", "name-particle-van", "authors.0.person_id", "vvandenberg"),
    case("names.particle_first_last", "name-particle-de", "authors.0.name", "R. de la Cruz"),
    case("names.particle_first_last", "name-particle-de", "authors.0.person_id", "rdelacruz"),
    case("names.suffix", "name-suffix", "authors.0.name",
         AllOf(Contains("Smith", "Jr."), Excludes("J. J."))),
    case("names.suffix", "name-suffix", "authors.1.person_id", "aadams"),
    case("names.corporate", "name-corporate", "authors.0.name",
         "Example Robotics Consortium"),
    case("names.corporate", "name-corporate", "authors.0.person_id", None),
    case("names.corporate_escaped", "name-corporate-amp", "authors.0.name", "AT&T Research"),
    case("names.corporate_escaped", "name-corporate-amp", "authors.1.person_id", "aadams"),
    case("names.hyphenated", "name-hyphen", "authors.0.name", "G.-A. Green"),
    case("names.hyphenated", "name-hyphen", "authors.0.person_id", "ggreen"),
    case("names.accent_tex", "name-accent-tex", "authors.0.name", "C. Côté"),
    case("names.accent_tex", "name-accent-tex", "authors.0.person_id", "ccote"),
    case("names.accent_utf8", "name-accent-utf8", "authors.0.name", "C. Côté"),
    case("names.accent_utf8", "name-accent-utf8", "authors.0.person_id", "ccote"),
    case("names.others", "name-others", "authors.*.person_id", Contains("aadams", "bbrown")),
    case("names.others", "name-others", "authors.*.name", Excludes("others")),
    case("names.same_initial_alex", "name-kim-alex", "authors.0.person_id", "akim"),
    case("names.same_initial_alan", "name-kim-alan", "authors.0.person_id", "alankim",
         xfail="#24"),
    case("names.initials_ambiguous", "name-kim-initial", "authors.0.person_id", None,
         xfail="#24"),
    case("identity.alias", "name-last-first", "authors.0.person_id", "aadams"),
    case("identity.full_name", "id-full-name", "authors.0.person_id", "ffischer", xfail="#24"),
    case("identity.normalized", "id-normalized", "authors.0.person_id", "ddavis"),
    case("identity.fuzzy", "id-fuzzy", "authors.0.person_id", None, xfail="#24"),
    case("identity.external", "id-external-2023", "authors.1.person_id", None),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", NAMES)
def test_names(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


# --- Equal contribution ------------------------------------------------------
# Four corpus entries differing only in the marker form, each writing it on a
# different part of a name, give the sixteen combinations of form and part.
# Every marked author is a lab member, so each one also says the cleaned name
# still finds its person.

EQUAL_ENTRIES = ["name-equal-dollar", "name-equal-caret",
                 "name-equal-superscript", "name-equal-star"]
EQUAL_NAMES = ["B. Brown", "C. Côté", "V. van den Berg", "J. Smith, Jr.", "A. Adams"]
EQUAL_IDS = ["bbrown", "ccote", "vvandenberg", "jsmith", "aadams"]
# The part each author carries the marker on, and how that part reads once it
# is off. The last author is never marked.
EQUAL_PARTS = [("authors.0.given", "Bob"), ("authors.1.family", "Côté"),
               ("authors.2.von", "van den"), ("authors.3.suffix", "Jr.")]
EQUAL_MARKED = [True, True, True, True, False]

EQUAL_CONTRIBUTION = [
    case("names.equal_contribution", bib_key, path, expected)
    for bib_key in EQUAL_ENTRIES
    for path, expected in ([("authors.*.name", EQUAL_NAMES),
                            ("authors.*.person_id", EQUAL_IDS)] + EQUAL_PARTS)
] + [
    case("names.equal_contribution_marker", bib_key, "authors.*.equal_contribution",
         EQUAL_MARKED)
    for bib_key in EQUAL_ENTRIES
] + [
    # A marker written twice, one in a brace group of its own, and one whose
    # command and argument BibTeX split into two name parts: each comes off
    # whole, and the name still resolves. A brace group holding only a star is
    # another command's argument, not a marker, and is left alone.
    case("names.equal_contribution_normalized", "name-equal-normalized",
         "authors.*.person_id", ["bbrown", "akim", "ggreen", "ddavis", "aadams"]),
    case("names.equal_contribution_normalized", "name-equal-normalized",
         "authors.*.equal_contribution", [True, True, True, False, False]),
    case("names.equal_contribution_normalized", "name-equal-normalized",
         "authors.0.name", "B. Brown"),
    case("names.equal_contribution_normalized", "name-equal-normalized",
         "authors.1.name", "A. Kim"),
    case("names.equal_contribution_normalized", "name-equal-normalized",
         "authors.2.name", "G.-A. Green"),
    case("names.equal_contribution_normalized", "name-equal-normalized",
         "authors.3.name", Contains("Davis", "*")),
    # An escaped star, caret or dollar is text: nobody is marked, and what was
    # written stays in the name rather than being read as an annotation.
    case("names.equal_contribution_escaped", "name-equal-escaped",
         "authors.*.equal_contribution", [False, False, False, False]),
    case("names.equal_contribution_escaped", "name-equal-escaped",
         "authors.1.name", Contains("Davis", "*")),
    case("names.equal_contribution_escaped", "name-equal-escaped",
         "authors.2.name", Contains("Green", "*")),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", EQUAL_CONTRIBUTION)
def test_equal_contribution(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


# The parts BibTeX split each name into, carried through to the output rather
# than collapsed into the display string. Matching on them is #24.

NAME_PARTS = [
    case("names.structured", "name-suffix", "authors.0.given", "John"),
    case("names.structured", "name-suffix", "authors.0.von", None),
    case("names.structured", "name-suffix", "authors.0.family", "Smith"),
    case("names.structured", "name-suffix", "authors.0.suffix", "Jr."),
    case("names.structured", "name-suffix", "authors.0.literal", None),
    case("names.structured", "name-particle-van", "authors.0.given", "Victor"),
    case("names.structured", "name-particle-van", "authors.0.von", "van den"),
    case("names.structured", "name-particle-van", "authors.0.family", "Berg"),
    case("names.structured", "name-hyphen", "authors.0.given", "Grace-Ann"),
    case("names.structured", "name-hyphen", "authors.0.family", "Green"),
    case("names.structured", "name-corporate", "authors.0.literal",
         "Example Robotics Consortium"),
    case("names.structured", "name-corporate", "authors.0.given", None),
    case("names.structured", "name-corporate", "authors.0.family", None),
    case("names.structured", "name-corporate-amp", "authors.0.literal", "AT&T Research"),
    case("names.structured", "name-corporate-amp", "authors.1.given", "Alice"),
    case("names.structured", "name-corporate-amp", "authors.1.family", "Adams"),
    case("names.structured", "name-corporate-amp", "authors.1.literal", None),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", NAME_PARTS)
def test_name_parts(valid_output, case_id, bib_key, path, expected):
    """The structured parts survive on the author, not only the display name."""
    check_publication(valid_output, bib_key, path, expected)


def display_name_from_parts(author):
    """The display form the parts imply: ``F. M. van Last, Jr.``

    Each given name is abbreviated to its initial, and each half of a
    hyphenated one keeps its own: ``Grace-Ann`` is ``G.-A.``, ``Dave M.`` is
    ``D. M.``
    """
    initials = " ".join(
        "-".join(f"{piece[0]}." for piece in part.split("-") if piece)
        for part in (author["given"] or "").split())
    name = " ".join(part for part in (initials, author["von"], author["family"]) if part)
    return f"{name}, {author['suffix']}" if author["suffix"] else name


@covers("names.structured")
def test_every_display_name_agrees_with_its_parts(valid_output):
    """Across the whole corpus, the display name follows from the parts.

    A row-by-row check of the parts would still pass if the parts were filled
    in beside a display name built some other way, and a containment check
    would still pass if the initials were dropped. This rebuilds the whole
    name from the parts and compares it.
    """
    checked = 0
    for publication in valid_output["publications"]:
        for author in publication["authors"]:
            where = f"{publication['bib_id']}: {author}"
            if author["literal"]:
                assert author["name"] == author["literal"], where
                assert [author[part] for part in ("given", "von", "family", "suffix")] \
                    == [None, None, None, None], where
            else:
                assert author["family"], where
                assert author["name"] == display_name_from_parts(author), where
            checked += 1
    # The loop has to have run over the names the corpus is built from.
    assert checked > 40, checked


MARKED_ENTRIES = set(EQUAL_ENTRIES) | {"name-equal-normalized"}


@covers("names.equal_contribution_marker")
def test_only_marked_authors_are_equal_contributors(valid_output):
    """Across the corpus, equal_contribution is set exactly where a marker was.

    The rows above say the marked authors are marked. This says the unmarked
    ones are not: no name elsewhere in the corpus — a starred title, a
    corporate name, an accent written in TeX, an escaped star — picks the flag
    up. Nor does a marked name keep a star once the marker is off.
    """
    marked = {(p["bib_id"], a["name"]) for p in valid_output["publications"]
              for a in p["authors"] if a["equal_contribution"]}
    assert {bib_id for bib_id, _ in marked} == MARKED_ENTRIES
    # Four parts marked in each of the four form entries, and three of the
    # five authors of name-equal-normalized.
    assert len(marked) == len(EQUAL_ENTRIES) * 4 + 3, sorted(marked)
    assert [name for _, name in marked if "*" in name] == []


@covers("names.initials_ambiguous", xfail="#24", owns=("name-kim-initial",))
def test_ambiguous_initials_listed(valid_unresolved):
    """An initials-only name that fits two members is listed for a human to resolve."""
    assert "A. Kim" in valid_unresolved.stdout


@covers("identity.external")
def test_external_author_listed(valid_unresolved, valid_output):
    assert "Q. Quinn" in valid_unresolved.stdout
    quinn = item(valid_output, "collaborators", "name", "Q. Quinn")
    assert quinn["publication_count"] == 2


# --- LaTeX and text ----------------------------------------------------------
# Titles and abstracts come out as plain Unicode text; $...$ math stays TeX.

LATEX = [
    case("latex.textbf", "tex-textbf", "title", "A Bold Claim"),
    case("latex.nested", "tex-nested", "title", "a B c and d e f"),
    case("latex.accent_braced", "tex-accent", "title", "Café Robots in München"),
    case("latex.caron_space", "tex-caron", "title", "Haček on č"),
    case("latex.dotless_i", "tex-dotless", "title", "María's Robot"),
    case("latex.ampersand", "tex-amp", "title", "Pick & Place"),
    case("latex.percent", "tex-percent", "title", "A 50% Speedup"),
    case("latex.underscore", "tex-underscore", "title", "The robot_arm Package"),
    case("latex.endash", "tex-endash", "title", "Pages 1–10"),
    case("latex.emdash", "tex-emdash", "title", "Robots—and People"),
    case("latex.quotes", "tex-quotes", "title", "The “Tidy” Robot"),
    case("latex.star_braced", "tex-rrt", "title", "Faster RRT* Planning"),
    case("latex.star_plain", "tex-bit", "title", "BIT* in Clutter"),
    case("latex.star_braced_whole", "tex-bit-braced", "title", "BIT* Revisited"),
    case("latex.math", "tex-math", "title", r"Planning in $O(n \log n)$ Time"),
    case("latex.html_special", "tex-html", "title", "When a < b > c & \"d\" isn't 'e'"),
    case("latex.markdown_punctuation", "tex-markdown", "title",
         "Not [a link](x), not `code`, not # heading, not *emphasis*"),
    case("latex.unicode_raw", "tex-unicode", "title", "Robots 机器人 and Émoji 🤖"),
    case("latex.abstract", "tex-abstract", "abstract",
         "Café robots run in $O(n)$ time and are very tidy."),
    case("latex.note_href", "tex-note-href", "note",
         Contains("https://example.org/code", "our site")),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", LATEX)
def test_latex(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


# --- Links -------------------------------------------------------------------

LINKS = [
    case("links.doi_bare", "link-doi-bare", "doi_url", "https://doi.org/10.5555/corpus.0001"),
    case("links.doi_url", "link-doi-url", "doi_url", "https://doi.org/10.5555/corpus.0002"),
    case("links.arxiv_prefixed", "link-arxiv-prefix", "arxiv_url",
         "https://arxiv.org/abs/2401.00001"),
    case("links.arxiv_unprefixed", "link-arxiv-bare", "arxiv_url",
         "https://arxiv.org/abs/2401.00002"),
    case("links.youtube", "link-youtube", "video_url",
         "https://www.youtube.com/watch?v=corpus00001"),
    case("links.youtube", "link-youtube", "url", None),
    case("links.vimeo", "link-vimeo", "video_url", "https://vimeo.com/000000001"),
    case("links.url", "link-url", "url", "https://example.org/papers/link-url"),
    case("links.url", "link-url", "video_url", None),
    case("links.pdf.local_present", "present", "pdf_url", Contains("present.pdf")),
    case("links.pdf.local_missing", "missing", "pdf_url", None),
    case("links.note_link_award", "link-note-award", "note",
         Contains("https://example.org/papers/award")),
    case("links.note_link_award", "link-note-award", "award", "Best Paper Award Finalist",
         xfail="#27"),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", LINKS)
def test_links(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


# --- BibTeX structure, entry types and fields -------------------------------

STRUCTURE = [
    case("structure.uppercase", "struct-upper", "entry_type", "article"),
    case("structure.uppercase", "struct-upper", "title", "Upper-Case Type and Fields"),
    case("structure.uppercase", "struct-upper", "authors.0.person_id", "aadams"),
    case("structure.uppercase", "struct-upper", "venue", Contains("Journal of Fictional Robots")),
    case("structure.value_quoted", "struct-quoted", "title", "A Quoted Title"),
    case("structure.value_quoted", "struct-quoted", "year", 2019),
    case("structure.value_braced", "struct-braced", "title", "A Braced Title"),
    case("structure.value_numeric", "struct-numeric", "year", 2019),
    case("structure.value_numeric", "struct-numeric", "venue", Contains("7(2)")),
    case("structure.crossref", "struct-child", "year", 2018),
    case("structure.crossref", "struct-child", "title", "A Child Paper"),
    case("structure.crossref", "struct-child", "venue",
         Contains("Proceedings of the Fictional Workshop")),
    case("structure.bom_crlf", "enc-bom-crlf", "title", "Byte Order Mark and CRLF"),
    case("structure.bom_crlf", "enc-bom-crlf", "authors.0.person_id", "ccote"),
    case("structure.bom_crlf", "enc-second", "title", "Second Entry After CRLF"),
    case("types.article", "type-article", "venue",
         AllOf(Contains("Journal of Fictional Robots", "12(3)", "2020"))),
    case("types.inproceedings", "type-inproceedings", "venue",
         AllOf(Contains("Proceedings of the Fictional Conference", "2020"), Excludes("{"))),
    case("types.phdthesis", "type-phdthesis", "venue",
         Contains("PhD thesis", "Example University", "2020")),
    case("types.mastersthesis", "type-mastersthesis", "venue",
         Contains("Masters thesis", "Example University", "2020")),
    case("types.techreport", "type-techreport", "venue",
         Contains("Technical Report EU-TR-7", "Example University", "2020")),
    case("types.techreport_default", "type-techreport-plain", "venue",
         Contains("Technical Report", "Example University", "2020")),
    case("types.misc_arxiv", "type-misc-arxiv", "venue", Contains("arXiv:2401.00007", "2020")),
    case("types.misc", "type-misc", "venue", "2020"),
    case("fields.journal", "type-article", "venue", Contains("Journal of Fictional Robots")),
    case("fields.volume", "type-article", "venue", Contains("12")),
    case("fields.number", "type-article", "venue", Contains("(3)")),
    case("fields.booktitle", "type-inproceedings", "venue",
         Contains("Proceedings of the Fictional Conference")),
    case("fields.school", "type-phdthesis", "venue", Contains("Example University")),
    case("fields.institution", "type-techreport", "venue", Contains("Example University")),
    case("fields.type", "type-techreport", "venue", Contains("Technical Report")),
    case("fields.eprint", "type-misc-arxiv", "arxiv_url", "https://arxiv.org/abs/2401.00007"),
    case("fields.archiveprefix", "link-arxiv-prefix", "arxiv_url",
         "https://arxiv.org/abs/2401.00001"),
    case("fields.doi", "link-doi-bare", "doi_url", "https://doi.org/10.5555/corpus.0001"),
    case("fields.url", "link-url", "url", "https://example.org/papers/link-url"),
    case("fields.project", "proj-single", "project_ids", ["homebot"]),
    case("fields.unread", "type-article", "bibtex", Contains("Fictional Press")),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", STRUCTURE)
def test_structure(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


@covers("structure.comment_lines", "structure.comment_entry", "structure.preamble",
        "structure.comment_mentions_command")
def test_comments_and_preamble_are_not_publications(valid_output):
    structure = {p["bib_id"] for p in valid_output["publications"]
                 if p["category"] == "Structure"}
    # Entries on both sides of the comments and the preamble are all read.
    assert {"struct-upper", "type-article", "type-misc"} <= structure
    # The @article inside @comment{...} is not a publication.
    assert "fake" not in structure
    # A % comment line that only mentions @comment{ is prose, not a command:
    # the entry after it is read like any other.
    assert "struct-comment-prose" in structure
    assert not [p for p in valid_output["publications"]
                if p["entry_type"] in ("comment", "preamble", "string")]


@covers("structure.bom_crlf")
def test_encoding_fixture_has_bom_and_crlf():
    """Guard the fixture itself: git or an editor must not normalize it."""
    raw = (VALID / "encoding.bib").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf@article{")
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


# --- Projects ----------------------------------------------------------------

PROJECTS = [
    case("projects.single", "proj-single", "project_ids", ["homebot"]),
    case("projects.multiple", "proj-multiple", "project_ids", ["homebot", "sharedarm"]),
    case("projects.none", "proj-none", "project_ids", []),
    case("projects.keywords", "proj-keywords", "project_ids", Contains("sharedarm"),
         xfail="#28"),
]


@pytest.mark.parametrize("case_id, bib_key, path, expected", PROJECTS)
def test_projects(valid_output, case_id, bib_key, path, expected):
    check_publication(valid_output, bib_key, path, expected)


@covers("projects.single", "projects.multiple")
def test_project_backlinks(valid_output):
    homebot = item(valid_output, "projects", "id", "homebot")
    sharedarm = item(valid_output, "projects", "id", "sharedarm")
    assert homebot["publication_ids"] == ["proj-single", "proj-multiple"]
    assert sharedarm["publication_ids"] == ["proj-multiple"]
    assert homebot["people_ids"] == ["aadams", "bbrown", "ccote"]
    assert sharedarm["people_ids"] == ["aadams", "ccote"]


# --- Every output field ------------------------------------------------------
# (case_id, section, lookup key, lookup value, field path, expected)

OUTPUT_FIELDS = [
    case("output.schema_version", "", "", "", "schema_version", 3),
    case("output.lab", "", "", "", "lab.name", "Corpus Lab"),
    case("output.publication.bib_id", "publications", "bib_id", "type-article", "bib_id",
         "type-article"),
    case("output.publication.title", "publications", "bib_id", "tex-unicode", "title",
         "Robots 机器人 and Émoji 🤖"),
    case("output.publication.authors", "publications", "bib_id", "name-last-first", "authors",
         [{"name": "A. Adams", "person_id": "aadams", "given": "Alice", "von": None,
           "family": "Adams", "suffix": None, "literal": None,
           "equal_contribution": False}]),
    case("output.publication.year", "publications", "bib_id", "type-article", "year", 2020),
    case("output.publication.venue", "publications", "bib_id", "type-article", "venue",
         Contains("Journal of Fictional Robots")),
    case("output.publication.category", "publications", "bib_id", "type-article", "category",
         "Structure"),
    case("output.publication.entry_type", "publications", "bib_id", "type-phdthesis",
         "entry_type", "phdthesis"),
    case("output.publication.abstract", "publications", "bib_id", "tex-abstract", "abstract",
         Contains("$O(n)$")),
    case("output.publication.note", "publications", "bib_id", "tex-note-href", "note",
         Contains("our site")),
    case("output.publication.pdf_url", "publications", "bib_id", "present", "pdf_url",
         Contains("present.pdf")),
    case("output.publication.doi_url", "publications", "bib_id", "link-doi-bare", "doi_url",
         "https://doi.org/10.5555/corpus.0001"),
    case("output.publication.arxiv_url", "publications", "bib_id", "link-arxiv-prefix",
         "arxiv_url", "https://arxiv.org/abs/2401.00001"),
    case("output.publication.url", "publications", "bib_id", "link-url", "url",
         "https://example.org/papers/link-url"),
    case("output.publication.video_url", "publications", "bib_id", "link-vimeo", "video_url",
         "https://vimeo.com/000000001"),
    case("output.publication.project_ids", "publications", "bib_id", "proj-multiple",
         "project_ids", ["homebot", "sharedarm"]),
    case("output.publication.bibtex", "publications", "bib_id", "type-article", "bibtex",
         Contains("@article{type-article,", "Journal of Fictional Robots")),
    case("output.person.id", "people", "name", "Alice Adams", "id", "aadams"),
    case("output.person.name", "people", "id", "ccote", "name", "Carol Côté"),
    case("output.person.role", "people", "id", "aadams", "role", "professor"),
    case("output.person.status", "people", "id", "eevans", "status", "alumni"),
    case("output.person.website", "people", "id", "aadams", "website",
         "https://example.org/people/aadams"),
    case("output.person.photo", "people", "id", "aadams", "photo", "images/aadams.jpg"),
    case("output.person.email", "people", "id", "aadams", "email", "aadams@example.org"),
    case("output.person.co_advisor", "people", "id", "bbrown", "co_advisor", "Peggy Park"),
    case("output.person.start_year", "people", "id", "aadams", "start_year", 2015),
    case("output.person.end_year", "people", "id", "eevans", "end_year", 2020),
    case("output.person.degree", "people", "id", "eevans", "degree", "PhD"),
    case("output.person.thesis_title", "people", "id", "eevans", "thesis_title",
         "Learning to Tidy"),
    case("output.person.current_position", "people", "id", "eevans", "current_position",
         "Research Scientist, Example Robotics Inc."),
    case("output.person.publication_count", "people", "id", "ccote", "publication_count", 8),
    case("output.person.publication_ids", "people", "id", "ccote", "publication_ids",
         ["proj-multiple", "name-accent-tex", "name-accent-utf8", "name-equal-dollar",
          "name-equal-caret", "name-equal-superscript", "name-equal-star",
          "enc-bom-crlf"]),
    case("output.project.id", "projects", "title", "Household Manipulation", "id", "homebot"),
    case("output.project.title", "projects", "id", "sharedarm", "title", "Shared Control"),
    case("output.project.description", "projects", "id", "homebot", "description",
         "Robots that tidy up a fictional kitchen."),
    case("output.project.website", "projects", "id", "homebot", "website",
         "https://example.org/projects/homebot"),
    case("output.project.status", "projects", "id", "sharedarm", "status", "completed"),
    case("output.project.publication_ids", "projects", "id", "homebot", "publication_ids",
         ["proj-single", "proj-multiple"]),
    case("output.project.people_ids", "projects", "id", "homebot", "people_ids",
         ["aadams", "bbrown", "ccote"]),
    case("output.collaborator.name", "collaborators", "name", "R. Ross", "name", "R. Ross"),
    case("output.collaborator.publication_count", "collaborators", "name", "Q. Quinn",
         "publication_count", 2),
    case("output.collaborator.last_year", "collaborators", "name", "Q. Quinn", "last_year",
         2023),
]


@pytest.mark.parametrize("case_id, section, key, value, path, expected", OUTPUT_FIELDS)
def test_output_fields(valid_output, case_id, section, key, value, path, expected):
    obj = item(valid_output, section, key, value) if section else valid_output
    assert_field(obj, path, expected, where=f"{section} {value}: ")


@covers("output.collaborators.order")
def test_collaborators_order(valid_output):
    """Most recent first, then most papers, then name."""
    rows = [(-c["last_year"], -c["publication_count"], c["name"])
            for c in valid_output["collaborators"]]
    assert rows == sorted(rows)
    assert valid_output["collaborators"][0]["name"] == "Q. Quinn"
    assert valid_output["collaborators"][-1]["name"] == "R. Ross"
