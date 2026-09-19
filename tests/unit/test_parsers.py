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


class TestLatexFallback:
    """A field pylatexenc cannot read costs that field's markup, never the entry."""

    def test_keeps_the_raw_text_and_says_where(self, capsys):
        value = r"Speed: {\verb"
        assert _convert(value, "papers.bib:someone2024:title") == r"Speed: \verb"
        assert "papers.bib:someone2024:title" in capsys.readouterr().err


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


KEPT_ENTRY = ("@article{kept,\n"
              "  title   = {A Fictional Title},\n"
              "  author  = {Adams, Alice},\n"
              "  journal = {Journal of Fictional Robots},\n"
              "  year    = {2024}\n"
              "}\n")

# Inputs around the @comment preprocessing. None of them may cost an entry:
# the scan only blanks a balanced @comment group found where a command can be.
COMMENT_HAZARDS = [
    ("a % comment line that mentions the command",
     "% Documentation mentions @comment{ syntax here\n" + KEPT_ENTRY),
    ("an @comment that never closes",
     "@comment{never closes\n" + KEPT_ENTRY),
    ("an @comment written inside a field value",
     "@article{host, title = {Using @comment{ safely}, year = {2024}}\n" + KEPT_ENTRY),
    ("an @ that starts no command",
     "@ not a command at all\n" + KEPT_ENTRY),
    ("a bare @ at the end of the file", KEPT_ENTRY + "\n@"),
    ("@comment spelled with space before its brace",
     "@comment {@article{hidden, title = {H}}}\n" + KEPT_ENTRY),
]


class TestCommentPreprocessing:
    """No input may make the @comment scan drop a valid entry."""

    @pytest.mark.parametrize("label, source",
                             COMMENT_HAZARDS,
                             ids=[label for label, _ in COMMENT_HAZARDS])
    def test_entry_survives(self, tmp_path, label, source):
        (tmp_path / "hazard.bib").write_text(source, encoding="utf-8")
        pubs = parse_all_publications(
            bib_dir=str(tmp_path),
            bib_files=[{"name": "hazard.bib", "category": "Test Papers"}],
        )
        assert "kept" in [p.bib_id for p in pubs], label

    def test_a_commented_out_entry_stays_commented_out(self, tmp_path):
        (tmp_path / "commented.bib").write_text(
            "@comment{not a publication: @article{hidden, title = {H}}}\n" + KEPT_ENTRY,
            encoding="utf-8")
        pubs = parse_all_publications(
            bib_dir=str(tmp_path),
            bib_files=[{"name": "commented.bib", "category": "Test Papers"}],
        )
        assert [p.bib_id for p in pubs] == ["kept"]
