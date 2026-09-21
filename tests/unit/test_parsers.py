"""Tests for the BibTeX parsing pipeline."""

import pytest
from pathlib import Path

from labdata.parsers.bibtex import (
    CROSSREF_UNSUPPORTED,
    DUPLICATE_CITATION_KEY,
    YEAR_MISSING,
    _Parser,
    _convert,
    bare_doi,
    build_identifiers,
    build_links,
    build_venue,
    extract_note,
    is_video_url,
    parse_project_ids,
    parse_all_works,
    pdf_link,
)
from labdata.models import Author


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestBuildVenue:
    def test_article(self):
        venue = build_venue({"ENTRYTYPE": "article",
                             "journal": "IEEE Transactions on Robotics"})
        assert venue.to_dict() == {"kind": "journal",
                                   "name": "IEEE Transactions on Robotics"}

    def test_inproceedings(self):
        venue = build_venue({
            "ENTRYTYPE": "inproceedings",
            "booktitle": "Proceedings of Robotics: Science and Systems"})
        assert venue.to_dict() == {
            "kind": "conference",
            "name": "Proceedings of Robotics: Science and Systems"}

    def test_incollection_is_a_book_not_a_conference(self):
        """One field name, two kinds of container: the entry type decides."""
        venue = build_venue({"ENTRYTYPE": "incollection",
                             "booktitle": "Handbook of Robots"})
        assert venue.to_dict() == {"kind": "book", "name": "Handbook of Robots"}

    def test_phdthesis(self):
        venue = build_venue({"ENTRYTYPE": "phdthesis", "school": "MIT"})
        assert venue.to_dict() == {"kind": "institution", "name": "MIT"}

    def test_techreport(self):
        venue = build_venue({"ENTRYTYPE": "techreport",
                             "institution": "Example University"})
        assert venue.to_dict() == {"kind": "institution",
                                   "name": "Example University"}

    def test_misc_arxiv(self):
        """A preprint's container is the repository archivePrefix names."""
        venue = build_venue({"ENTRYTYPE": "misc", "eprint": "2301.12345",
                             "archivePrefix": "arXiv"})
        assert venue.to_dict() == {"kind": "repository", "name": "arXiv"}

    def test_misc_arxiv_without_a_prefix(self):
        venue = build_venue({"ENTRYTYPE": "misc", "eprint": "2301.12345"})
        assert venue.to_dict() == {"kind": "repository", "name": "arXiv"}

    def test_no_container_field(self):
        assert build_venue({"ENTRYTYPE": "book", "year": "2024"}) is None

    def test_journal_wins_over_booktitle(self):
        """The precedence is the field order, so one entry gets one venue."""
        venue = build_venue({"ENTRYTYPE": "article", "journal": "J",
                             "booktitle": "B"})
        assert venue.name == "J"


class TestBareDoi:
    def test_already_bare(self):
        assert bare_doi("10.1109/TRO.2024.1234567") == "10.1109/TRO.2024.1234567"

    def test_written_as_a_resolver_url(self):
        assert bare_doi("https://doi.org/10.1109/TRO.2024.1234567") == \
            "10.1109/TRO.2024.1234567"

    def test_written_as_a_dx_resolver_url(self):
        assert bare_doi("http://dx.doi.org/10.1/x") == "10.1/x"

    def test_some_other_url_is_left_alone(self):
        """Only the registered resolvers are stripped; nothing else is guessed."""
        assert bare_doi("https://example.org/10.1/x") == "https://example.org/10.1/x"


class TestBuildIdentifiers:
    def test_each_scheme(self):
        assert build_identifiers({
            "doi": "10.1/x", "isbn": "978-1", "issn": "2999-0001",
            "eprint": "2301.12345", "archivePrefix": "arXiv",
        }) == {"doi": ["10.1/x"], "isbn": ["978-1"], "issn": ["2999-0001"],
               "arxiv": ["2301.12345"]}

    def test_the_prefix_is_the_scheme(self):
        """archivePrefix names the repository, which is what the scheme says."""
        assert build_identifiers({"eprint": "hal-1", "archivePrefix": "HAL"}) == \
            {"hal": ["hal-1"]}

    def test_a_doi_url_is_recorded_as_an_identifier(self):
        assert build_identifiers({"doi": "https://doi.org/10.1/x"}) == \
            {"doi": ["10.1/x"]}

    def test_nothing_to_read(self):
        assert build_identifiers({"ENTRYTYPE": "misc"}) == {}


class TestIsVideoUrl:
    def test_youtube(self):
        assert is_video_url("https://www.youtube.com/watch?v=abc")

    def test_vimeo(self):
        assert is_video_url("https://vimeo.com/123")

    def test_non_video(self):
        assert not is_video_url("https://example.com/paper.pdf")


class TestBuildLinks:
    def test_the_entrys_own_url_comes_from_the_input(self):
        links = build_links({"url": "https://example.org/p"}, "k", {}, None)
        assert [l.to_dict() for l in links["url"]] == [{
            "url": "https://example.org/p", "label": None, "origin": "input",
            "verification": {"status": "unchecked", "checked_at": None}}]

    def test_a_video_host_is_filed_as_a_video(self):
        links = build_links({"url": "https://vimeo.com/1"}, "k", {}, None)
        assert "url" not in links
        assert links["video"][0].url == "https://vimeo.com/1"

    def test_links_built_from_identifiers_say_they_are_derived(self):
        identifiers = {"doi": ["10.1/x"], "arxiv": ["2301.12345"]}
        links = build_links({}, "k", identifiers, None)
        assert links["doi"][0].url == "https://doi.org/10.1/x"
        assert links["arxiv"][0].url == "https://arxiv.org/abs/2301.12345"
        assert {l[0].origin for l in (links["doi"], links["arxiv"])} == {"derived"}

    def test_no_base_and_no_fields(self):
        assert build_links({}, "k", {}, None) == {}


class TestPdfLink:
    def test_no_base_configured(self):
        assert pdf_link("k", None) is None

    def test_a_remote_base_is_never_fetched(self):
        link = pdf_link("k", "https://example.org/pdfs")
        assert link.url == "https://example.org/pdfs/k.pdf"
        assert link.status == "unchecked"

    def test_a_local_file_that_is_there(self, tmp_path):
        (tmp_path / "k.pdf").write_bytes(b"%PDF-1.4\n")
        assert pdf_link("k", str(tmp_path)).status == "verified"

    def test_a_local_file_that_is_not_there_is_kept_and_labelled(self, tmp_path):
        """The link is not deleted: `missing` and `unchecked` are different
        answers, and so is having no base at all."""
        link = pdf_link("k", str(tmp_path))
        assert link.url == f"{tmp_path}/k.pdf"
        assert link.status == "missing"


class TestExtractNote:
    def test_with_note(self):
        entry = {"note": "Best Paper Award."}
        assert extract_note(entry) == "Best Paper Award"

    def test_no_note(self):
        assert extract_note({}) is None
        assert extract_note({"note": ""}) is None
        assert extract_note({"note": "   "}) is None


class TestParseProjectIds:
    def test_single(self):
        assert parse_project_ids({"project": "gardenbot"}) == ["gardenbot"]

    def test_multiple(self):
        assert parse_project_ids({"project": "gardenbot, planning"}) == [
            "gardenbot", "planning"
        ]

    def test_braces(self):
        assert parse_project_ids({"project": "{gardenbot, planning}"}) == [
            "gardenbot", "planning"
        ]

    def test_empty(self):
        assert parse_project_ids({}) == []
        assert parse_project_ids({"project": ""}) == []


class TestParseAllWorks:
    def test_parse_fixtures(self):
        bib_files = [
            {"name": "sample.bib", "category": "Test Papers"},
        ]
        works = parse_all_works(
            bib_dir=str(FIXTURES),
            bib_files=bib_files,
        )
        assert len(works) == 3
        # Should be sorted by year descending
        assert works[0].year >= works[-1].year
        # Check first work has structured authors
        assert all(isinstance(a, Author) for a in works[0].authors)

    def test_a_work_with_no_year_sorts_last_and_says_so(self, tmp_path):
        """Null rather than 0: the position is the same, the meaning is not."""
        (tmp_path / "y.bib").write_text(
            "@article{no-year,\n  title = {No Year},\n"
            "  author = {Adams, Alice},\n  journal = {J}\n}\n"
            "@article{old,\n  title = {Old},\n"
            "  author = {Adams, Alice},\n  journal = {J},\n  year = {1999}\n}\n",
            encoding="utf-8")
        warnings = []
        works = parse_all_works(bib_dir=str(tmp_path),
                                bib_files=[{"name": "y.bib", "category": "T"}],
                                warnings=warnings)
        assert [w.bib_id for w in works] == ["old", "no-year"]
        assert works[-1].year is None
        assert len(warnings) == 1
        assert warnings[0].startswith(YEAR_MISSING)
        assert "y.bib:no-year:year" in warnings[0]


class TestCrossref:
    """An entry carrying a crossref is rejected rather than resolved (#65)."""

    CHILD = ("@proceedings{a-parent,\n"
             "  title  = {Proceedings of the Fictional Workshop},\n"
             "  author = {Adams, Alice},\n"
             "  year   = {2024}\n"
             "}\n"
             "@inproceedings{a-child,\n"
             "  title    = {A Child Paper},\n"
             "  crossref = {a-parent}\n"
             "}\n")

    def parse(self, tmp_path, text, errors):
        (tmp_path / "child.bib").write_text(text, encoding="utf-8")
        return parse_all_works(
            bib_dir=str(tmp_path),
            bib_files=[{"name": "child.bib", "category": "Test Papers"}],
            errors=errors)

    def test_the_child_is_rejected_and_the_parent_still_compiles(self, tmp_path):
        errors = []
        works = self.parse(tmp_path, self.CHILD, errors)
        assert [w.bib_id for w in works] == ["a-parent"]
        assert len(errors) == 1
        assert errors[0].startswith(CROSSREF_UNSUPPORTED)
        assert "child.bib:a-child:crossref" in errors[0]
        assert "a-parent" in errors[0]

    def test_a_missing_parent_is_the_same_error_not_a_warning(self, tmp_path):
        errors = []
        works = self.parse(
            tmp_path,
            "@inproceedings{a-child,\n"
            "  title    = {A Child Paper},\n"
            "  author   = {Adams, Alice},\n"
            "  crossref = {no-such-parent}\n"
            "}\n", errors)
        assert works == []
        assert len(errors) == 1
        assert errors[0].startswith(CROSSREF_UNSUPPORTED)
        assert "no-such-parent" in errors[0]

    EMPTY = ("@inproceedings{empty-child,\n"
             "  title    = {A Child With an Empty Crossref},\n"
             "  author   = {Adams, Alice},\n"
             "  year     = {2024},\n"
             "  crossref = {}\n"
             "}\n")

    @pytest.mark.parametrize("field", ["crossref = {}", "crossref = {   }",
                                       "CROSSREF = {}"])
    def test_the_field_is_rejected_on_its_presence_not_on_its_value(self, tmp_path,
                                                                    field):
        """An empty crossref is a field the entry carries, so it is an error.

        pybtex keeps `crossref = {}` as a present field whose value is the
        empty string. Rejecting on the value would let it through and put the
        silent path back under a different spelling.
        """
        errors = []
        works = self.parse(tmp_path, self.EMPTY.replace("crossref = {}", field),
                           errors)
        assert works == []
        assert len(errors) == 1, errors
        assert errors[0].startswith(CROSSREF_UNSUPPORTED)
        assert "child.bib:empty-child:crossref" in errors[0]

    def test_an_empty_crossref_is_not_reported_as_a_blank_parent(self, tmp_path):
        """The diagnostic says the entry names no parent rather than quoting one.

        Asserted on shape rather than on wording: a pair of empty quotes is a
        diagnostic that reads as though it had found a parent called "".
        """
        errors = []
        self.parse(tmp_path, self.EMPTY, errors)
        assert "''" not in errors[0] and '""' not in errors[0], errors[0]
        # A named parent is still quoted, so the check above is about the
        # empty case and not about quoting in general.
        named = []
        self.parse(tmp_path, self.CHILD, named)
        assert "'a-parent'" in named[0], named[0]

    def test_no_work_can_be_emitted_with_an_empty_author_list(self, tmp_path):
        """The failure crossref caused: a child with no author of its own.

        Rejecting the entry removes the path rather than patching it, so
        there is no code path left that emits a work with no authors because
        of a crossref.
        """
        errors = []
        works = self.parse(tmp_path, self.CHILD, errors)
        assert [w.bib_id for w in works if not w.authors] == []


class TestDuplicateCitationKeys:
    def test_cross_file_duplicate_preserves_the_first_key_spelling(self, tmp_path):
        """Citation keys compare without case, but diagnostics retain both sources."""
        first = tmp_path / "first.bib"
        second = tmp_path / "second.bib"
        first.write_text(entry("FirstKey"), encoding="utf-8")
        second.write_text(entry("firstkey"), encoding="utf-8")

        errors = []
        parse_all_works(
            bib_dir=str(tmp_path),
            bib_files=[
                {"name": first.name, "category": "Test Papers"},
                {"name": second.name, "category": "Test Papers"},
            ],
            diagnostics=errors,
        )

        assert errors == [
            f"{DUPLICATE_CITATION_KEY} {second}:firstkey:citation_key: "
            f"duplicate citation key; first defined in "
            f"{first}:FirstKey:citation_key"
        ]


def entry(key: str, title: str = "A Fictional Title") -> str:
    return (f"@article{{{key},\n"
            f"  title   = {{{title}}},\n"
            "  author  = {Adams, Alice},\n"
            "  journal = {Journal of Fictional Robots},\n"
            "  year    = {2024}\n"
            "}\n")


# Inputs around @comment handling. Each case names every key the file defines,
# split into the ones that must be read and the ones that must not: "the entry
# I named survives" would pass just as happily while a neighbour vanished or a
# commented-out entry leaked, which is how the quoted-value defect got through.
#
# labdata differs from pybtex on exactly one thing: a balanced @comment group
# is a comment, so entries inside it are not works. Everywhere else the
# expectations below are pybtex's own reading of the file.
#
# (label, source, keys that must be read, keys that must not be)
COMMENT_HAZARDS = [
    ("a balanced @comment block hides what is inside it",
     "@comment{not a publication: @article{hidden, title = {H}}}\n" + entry("kept"),
     {"kept"}, {"hidden"}),
    ("@comment spelled with a space before its brace",
     "@comment {@article{hidden, title = {H}}}\n" + entry("kept"),
     {"kept"}, {"hidden"}),
    ("@comment written with parentheses",
     "@comment(not a publication: @article{hidden, title = {H}})\n" + entry("kept"),
     {"kept"}, {"hidden"}),
    ("a % comment line that only mentions the command",
     "% Documentation mentions @comment{ syntax here\n" + entry("real"),
     {"real"}, set()),
    ("an @comment that never closes",
     "@comment{never closes\n" + entry("kept"),
     {"kept"}, set()),
    ("an unclosed brace inside @comment at the end of the file",
     entry("kept") + "@comment{x {unclosed\n",
     {"kept"}, set()),
    ("an @comment inside a braced field value",
     "@article{host, title = {Braces around @comment{x} keep it text},"
     " year = {2024}}\n" + entry("kept"),
     {"host", "kept"}, set()),
    ("an @comment inside a quoted field value",
     '@article{host, title = "Quotes around @comment{x} keep it text",'
     ' year = {2024}}\n' + entry("kept"),
     {"host", "kept"}, set()),
    ("a paren-delimited entry whose quoted value holds ) and a command",
     '@article(host,title="Host ) @comment(unclosed", author="Adams, Alice",'
     ' journal="J", year=2024)\n' + entry("real"),
     {"host", "real"}, set()),
    ("a % comment inside an entry body",
     "@article{host,\n  title = {T},  % a note to self\n  year  = {2024}\n}\n"
     + entry("kept"),
     {"host", "kept"}, set()),
    ("an unterminated quote at the end of the file",
     entry("kept") + '@article{broken, title = "never closed\n',
     {"broken", "kept"}, set()),
    ("an unclosed brace inside a quote at the end of the file",
     entry("kept") + '@article{broken, title = "a {b\n',
     {"broken", "kept"}, set()),
    ("an @ that starts no command",
     "@ not a command at all\n" + entry("kept"),
     {"kept"}, set()),
    ("a bare @ at the end of the file",
     entry("kept") + "\n@",
     {"kept"}, set()),
    # Braces are counted as pybtex counts them, which is BibTeX's own rule: a
    # brace is a brace whether it is escaped or quoted. These three pin that,
    # because the group then ends earlier than a reader might expect and what
    # follows is exposed — matching the library rather than second-guessing it.
    ("an escaped brace ends the group, as pybtex counts it",
     "@comment{ignored \\} " + entry("fake") + "}\n" + entry("real"),
     {"fake", "real"}, set()),
    ("a quoted closing brace ends the group, as pybtex counts it",
     '@comment{note "}" @article{hidden, title={H}}}\n' + entry("kept"),
     {"hidden", "kept"}, set()),
    ("a quoted opening brace keeps the group open, as pybtex counts it",
     '@comment{note "{" ignored}\n' + entry("kept"),
     {"kept"}, set()),
]


def read_source(tmp_path, source, name="hazard.bib"):
    (tmp_path / name).write_text(source, encoding="utf-8")
    return parse_all_works(
        bib_dir=str(tmp_path),
        bib_files=[{"name": name, "category": "Test Papers"}],
    )


class TestCommentHandling:
    """What a @comment group hides, and what it must never take with it."""

    @pytest.mark.parametrize("label, source, present, absent",
                             COMMENT_HAZARDS,
                             ids=[case[0] for case in COMMENT_HAZARDS])
    def test_exactly_the_expected_entries_are_read(self, tmp_path, label, source,
                                                   present, absent):
        read = {pub.bib_id for pub in read_source(tmp_path, source)}
        assert read == present, label
        assert not (read & absent), label

    def test_a_quoted_value_does_not_end_a_paren_entry(self, tmp_path):
        """Regression: a ) inside "..." used to end @article(...) early.

        labdata read the file itself to find @comment groups, so it could be
        wrong about where a value ended; the entry then lost every field and
        the entry after it disappeared. pybtex tokenizes the file now.
        """
        source = ('@article(host,title="Host ) @comment(unclosed",'
                  ' author="Adams, Alice", journal="J", year=2024)\n' + entry("real"))
        works = {work.bib_id: work for work in read_source(tmp_path, source)}
        assert sorted(works) == ["host", "real"]
        host = works["host"]
        assert host.title == "Host ) @comment(unclosed"
        assert host.year == 2024
        assert [a.name for a in host.authors] == ["Alice Adams"]
        assert host.venue.name == "J"


class TestLatexFallback:
    """A field pylatexenc cannot read costs that field's markup, never the entry."""

    def test_keeps_the_raw_text_and_says_where(self, capsys):
        value = r"Speed: {\verb"
        assert _convert(value, "papers.bib:someone2024:title") == r"Speed: \verb"
        assert "papers.bib:someone2024:title" in capsys.readouterr().err

    def test_the_entry_is_still_published(self, tmp_path, capsys):
        """End to end: the entry is read, with the raw text of the bad field."""
        works = read_source(tmp_path, entry("kept", title=r"Speed: \verb"))
        assert [work.bib_id for work in works] == ["kept"]
        assert works[0].title == r"Speed: \verb"
        assert works[0].year == 2024
        assert [a.name for a in works[0].authors] == ["Alice Adams"]
        assert "hazard.bib:kept:title" in capsys.readouterr().err


class TestEntryFiltering:
    """pybtex raises SkipEntry for a filtered entry too, not only for @comment.

    labdata passes ``wanted_entries`` straight through, so recovering from the
    wrong SkipEntry would corrupt a filtered read — and would do it silently,
    because the scanner is left somewhere quite different from a comment.
    """

    REJECTED = "@article{drop, title = {D}, year = {2024}}\n"
    WANTED = "@article{keep, title = {K}, year = {2024}}\n"

    def parse(self, text):
        return _Parser(wanted_entries=["keep"]).parse_string(text)

    def test_a_filtered_entry_does_not_swallow_the_next_one(self):
        data = self.parse(self.REJECTED + "@article(keep, title = {K}, year = {2024})\n")
        assert list(data.entries) == ["keep"]

    def test_a_filtered_entry_does_not_swallow_a_preamble(self):
        data = self.parse(self.REJECTED + '@preamble("a preamble")\n' + self.WANTED)
        assert list(data.entries) == ["keep"]
        assert data.preamble == "a preamble"
