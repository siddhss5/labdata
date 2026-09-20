"""Tests for the BibTeX parsing pipeline."""

import pytest
from pathlib import Path

from labdata.parsers.bibtex import (
    _convert,
    format_authors_string,
    format_venue,
    extract_note,
    extract_video_url,
    construct_doi_url,
    construct_arxiv_url,
    parse_project_ids,
    parse_all_publications,
)
from labdata.models import Author


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestFormatAuthorsString:
    def test_single(self):
        assert format_authors_string([Author(name="A. Adams")]) == "A. Adams"

    def test_two(self):
        result = format_authors_string([
            Author(name="A. Adams"),
            Author(name="B. Brown"),
        ])
        assert result == "A. Adams and B. Brown"

    def test_three(self):
        result = format_authors_string([
            Author(name="A. Adams"),
            Author(name="B. Brown"),
            Author(name="H. Müller"),
        ])
        assert result == "A. Adams, B. Brown, and H. Müller"


class TestFormatVenue:
    def test_article(self):
        entry = {
            "ENTRYTYPE": "article",
            "journal": "IEEE Transactions on Robotics",
            "volume": "40",
            "number": "3",
            "year": "2024",
        }
        result = format_venue(entry)
        assert "*IEEE Transactions on Robotics*" in result
        assert "40" in result
        assert "(3)" in result
        assert "2024" in result

    def test_inproceedings(self):
        entry = {
            "ENTRYTYPE": "inproceedings",
            "booktitle": "Proceedings of Robotics: Science and Systems",
            "year": "2023",
        }
        result = format_venue(entry)
        assert "*Proceedings of Robotics: Science and Systems*" in result
        assert "2023" in result

    def test_phdthesis(self):
        entry = {
            "ENTRYTYPE": "phdthesis",
            "school": "MIT",
            "year": "2023",
        }
        assert format_venue(entry) == "PhD thesis, MIT, 2023"

    def test_misc_arxiv(self):
        entry = {
            "ENTRYTYPE": "misc",
            "eprint": "2301.12345",
            "year": "2023",
        }
        result = format_venue(entry)
        assert "*arXiv:2301.12345*" in result

    def test_unknown_type(self):
        entry = {"ENTRYTYPE": "unknown", "year": "2024"}
        assert format_venue(entry) == "2024"


class TestExtractNote:
    def test_with_note(self):
        entry = {"note": "Best Paper Award."}
        assert extract_note(entry) == "Best Paper Award"

    def test_no_note(self):
        assert extract_note({}) is None
        assert extract_note({"note": ""}) is None
        assert extract_note({"note": "   "}) is None


class TestExtractVideoUrl:
    def test_youtube(self):
        entry = {"url": "https://www.youtube.com/watch?v=abc"}
        assert extract_video_url(entry) == "https://www.youtube.com/watch?v=abc"

    def test_vimeo(self):
        entry = {"url": "https://vimeo.com/123"}
        assert extract_video_url(entry) == "https://vimeo.com/123"

    def test_non_video(self):
        entry = {"url": "https://example.com/paper.pdf"}
        assert extract_video_url(entry) is None

    def test_no_url(self):
        assert extract_video_url({}) is None


class TestConstructDoiUrl:
    def test_basic(self):
        entry = {"doi": "10.1109/TRO.2024.1234567"}
        assert construct_doi_url(entry) == "https://doi.org/10.1109/TRO.2024.1234567"

    def test_full_url(self):
        entry = {"doi": "https://doi.org/10.1109/TRO.2024.1234567"}
        assert construct_doi_url(entry) == "https://doi.org/10.1109/TRO.2024.1234567"

    def test_no_doi(self):
        assert construct_doi_url({}) is None


class TestConstructArxivUrl:
    def test_with_prefix(self):
        entry = {"eprint": "2301.12345", "archivePrefix": "arXiv"}
        assert construct_arxiv_url(entry) == "https://arxiv.org/abs/2301.12345"

    def test_without_prefix(self):
        entry = {"eprint": "2301.12345"}
        assert construct_arxiv_url(entry) == "https://arxiv.org/abs/2301.12345"

    def test_no_eprint(self):
        assert construct_arxiv_url({}) is None


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


class TestParseAllPublications:
    def test_parse_fixtures(self):
        bib_files = [
            {"name": "sample.bib", "category": "Test Papers"},
        ]
        pubs = parse_all_publications(
            bib_dir=str(FIXTURES),
            bib_files=bib_files,
        )
        assert len(pubs) == 3
        # Should be sorted by year descending
        assert pubs[0].year >= pubs[-1].year
        # Check first pub has structured authors
        assert all(isinstance(a, Author) for a in pubs[0].authors)


class TestCrossref:
    """A crossref that points nowhere is reported; the entry is still read."""

    def test_missing_parent_is_reported_and_the_entry_is_kept(self, tmp_path, capsys):
        (tmp_path / "child.bib").write_text(
            "@inproceedings{a-child,\n"
            "  title    = {A Child Paper},\n"
            "  author   = {Adams, Alice},\n"
            "  year     = {2024},\n"
            "  crossref = {no-such-parent}\n"
            "}\n", encoding="utf-8")
        pubs = parse_all_publications(
            bib_dir=str(tmp_path),
            bib_files=[{"name": "child.bib", "category": "Test Papers"}],
        )
        assert [p.bib_id for p in pubs] == ["a-child"]
        assert "no-such-parent" in capsys.readouterr().err


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
# is a comment, so entries inside it are not publications. Everywhere else the
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
    return parse_all_publications(
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
        pubs = {pub.bib_id: pub for pub in read_source(tmp_path, source)}
        assert sorted(pubs) == ["host", "real"]
        host = pubs["host"]
        assert host.title == "Host ) @comment(unclosed"
        assert host.year == 2024
        assert [a.name for a in host.authors] == ["A. Adams"]
        assert "J" in host.venue


class TestLatexFallback:
    """A field pylatexenc cannot read costs that field's markup, never the entry."""

    def test_keeps_the_raw_text_and_says_where(self, capsys):
        value = r"Speed: {\verb"
        assert _convert(value, "papers.bib:someone2024:title") == r"Speed: \verb"
        assert "papers.bib:someone2024:title" in capsys.readouterr().err

    def test_the_entry_is_still_published(self, tmp_path, capsys):
        """End to end: the entry is read, with the raw text of the bad field."""
        pubs = read_source(tmp_path, entry("kept", title=r"Speed: \verb"))
        assert [pub.bib_id for pub in pubs] == ["kept"]
        assert pubs[0].title == r"Speed: \verb"
        assert pubs[0].year == 2024
        assert [a.name for a in pubs[0].authors] == ["A. Adams"]
        assert "hazard.bib:kept:title" in capsys.readouterr().err
