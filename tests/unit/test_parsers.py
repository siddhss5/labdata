"""Tests for the BibTeX parsing pipeline."""

import pytest
from pathlib import Path

from labdata.parsers.bibtex import (
    parse_bibtex_file,
    parse_author_list,
    format_authors_string,
    format_venue,
    extract_note,
    extract_video_url,
    construct_doi_url,
    construct_arxiv_url,
    parse_project_ids,
    entry_to_publication,
    parse_all_publications,
)
from labdata.models import Author


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestParseBibtexFile:
    def test_parse_sample(self):
        entries = parse_bibtex_file(str(FIXTURES / "sample.bib"))
        assert len(entries) == 3
        ids = {e["ID"] for e in entries}
        assert "adams2024robot" in ids
        assert "brown2023planning" in ids


class TestParseAuthorList:
    def test_single_author(self):
        authors = parse_author_list("Adams, Alice")
        assert len(authors) == 1
        assert authors[0].name == "A. Adams"
        assert authors[0].person_id is None

    def test_multiple_authors(self):
        authors = parse_author_list("Adams, Alice and Brown, Bob A.")
        assert len(authors) == 2
        assert authors[0].name == "A. Adams"
        assert "B." in authors[1].name

    def test_three_authors(self):
        authors = parse_author_list(
            "Adams, Alice and Brown, Bob A. and M{\\\"u}ller, Hans"
        )
        assert len(authors) == 3
        assert "Müller" in authors[2].name

    def test_empty_field(self):
        assert parse_author_list("") == []
        assert parse_author_list("   ") == []

    def test_malformed_field(self):
        # Should not crash, return something reasonable
        authors = parse_author_list("Just A Name")
        assert len(authors) >= 1


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
        entry = {"note": "\\textbf{Best Paper Award}"}
        result = extract_note(entry)
        assert result == "**Best Paper Award**"

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


class TestEntryToPublication:
    def test_basic(self):
        entry = {
            "ID": "adams2024",
            "ENTRYTYPE": "article",
            "title": "A \\textbf{Great} Paper",
            "author": "Adams, Alice",
            "journal": "Test Journal",
            "year": "2024",
            "doi": "10.1234/test",
        }
        pub = entry_to_publication(entry, "Journal Papers")
        assert pub.bib_id == "adams2024"
        assert len(pub.authors) == 1
        assert pub.authors[0].name == "A. Adams"
        assert pub.year == 2024
        assert pub.category == "Journal Papers"
        assert pub.entry_type == "article"
        assert pub.doi_url == "https://doi.org/10.1234/test"

    @pytest.mark.xfail(strict=True, reason="#18")
    def test_title_is_plain_text(self):
        """Titles come out as plain text, without Markdown ``**`` for \\textbf."""
        entry = {
            "ID": "adams2024",
            "ENTRYTYPE": "article",
            "title": "A \\textbf{Great} Paper",
            "author": "Adams, Alice",
            "year": "2024",
        }
        pub = entry_to_publication(entry, "Journal Papers")
        assert pub.title == "A Great Paper"

    def test_with_video_url(self):
        entry = {
            "ID": "test2024",
            "ENTRYTYPE": "misc",
            "title": "Test",
            "author": "Test, A.",
            "year": "2024",
            "url": "https://youtube.com/watch?v=abc",
        }
        pub = entry_to_publication(entry, "Other")
        assert pub.video_url == "https://youtube.com/watch?v=abc"
        assert pub.url is None  # Not duplicated


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
