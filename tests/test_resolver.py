"""Tests for the resolver: author matching, project resolution, back-linking."""

import pytest
from pathlib import Path

from labdata.models import Author, Publication, Person, Project, LabData
from labdata.loaders import load_people, load_projects
from labdata.resolver import (
    normalize_name,
    is_abbreviated,
    build_alias_index,
    fuzzy_match,
    resolve_authors,
    resolve_projects,
    compute_backlinks,
)
from labdata.assembler import assemble
from labdata.config import LabDataConfig, BibFile


FIXTURES = Path(__file__).parent / "fixtures"


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("J. Smith") == "j smith"

    def test_accents(self):
        assert normalize_name("H. Müller") == "h muller"

    def test_periods(self):
        assert normalize_name("J.A. Smith") == "ja smith"

    def test_whitespace(self):
        assert normalize_name("  J.  Smith  ") == "j smith"

    def test_superscript(self):
        assert normalize_name("J. Smith<sup>*</sup>") == "j smith"


class TestIsAbbreviated:
    def test_single_initial_surname(self):
        assert is_abbreviated("a kim") is True
        assert is_abbreviated("h zhang") is True

    def test_multi_initial(self):
        assert is_abbreviated("a j kim") is False

    def test_full_name(self):
        assert is_abbreviated("john smith") is False

    def test_single_word(self):
        assert is_abbreviated("kim") is False


class TestBuildAliasIndex:
    def test_indexes_name_and_aliases(self):
        people = [
            Person(id="jsmith", name="John Smith", aliases=["J. Smith"]),
        ]
        index = build_alias_index(people)
        assert "john smith" in index
        assert "j smith" in index
        assert index["john smith"] == "jsmith"
        assert index["j smith"] == "jsmith"

    def test_multiple_people(self):
        people = [
            Person(id="jsmith", name="John Smith", aliases=["J. Smith"]),
            Person(id="jdoe", name="Jane Doe", aliases=["J. Doe"]),
        ]
        index = build_alias_index(people)
        assert index["j smith"] == "jsmith"
        assert index["j doe"] == "jdoe"

    def test_collision_detection(self):
        """Ambiguous aliases shared by multiple people are excluded."""
        people = [
            Person(id="akim", name="Alex Kim", aliases=["A. Kim"]),
            Person(id="alankim", name="Alan Kim", aliases=["A. Kim"]),
        ]
        index = build_alias_index(people)
        # "a kim" is ambiguous — should NOT be in the index
        assert "a kim" not in index
        # Canonical names are still indexed (they're unique)
        assert index["alex kim"] == "akim"
        assert index["alan kim"] == "alankim"

    @pytest.mark.xfail(strict=True, reason="#24")
    def test_same_initial_collision_without_alias(self):
        """An alias shared implicitly with another person's initials is ambiguous.

        Alan Kim declares no aliases, but "A. Kim" fits him as well as Alex Kim,
        so it must not resolve to Alex.
        """
        people = [
            Person(id="akim", name="Alex Kim", aliases=["A. Kim"]),
            Person(id="alankim", name="Alan Kim", aliases=[]),
        ]
        pub = Publication(
            bib_id="kim2024", title="Test", authors=[Author(name="A. Kim")],
            year=2024, venue="Test", category="Test", entry_type="article",
        )
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id is None
        assert "A. Kim" in unresolved


class TestFuzzyMatch:
    def test_abbreviated_name_skipped(self):
        """Single-initial names should NOT fuzzy match — too ambiguous."""
        index = {"y zhang": "yzhang"}
        assert fuzzy_match("H. Zhang", index) is None

    def test_close_match(self):
        index = {"john smith": "jsmith"}
        # "john a smith" is close to "john smith"
        result = fuzzy_match("John A. Smith", index, threshold=0.75)
        assert result == "jsmith"

    def test_no_match(self):
        index = {"john smith": "jsmith"}
        result = fuzzy_match("Completely Different Name", index)
        assert result is None


class TestResolveAuthors:
    def _make_pub(self, author_names):
        return Publication(
            bib_id="test",
            title="Test",
            authors=[Author(name=n) for n in author_names],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
        )

    def test_exact_alias_match(self):
        people = [
            Person(id="jsmith", name="John Smith", aliases=["J. Smith"]),
        ]
        pub = self._make_pub(["J. Smith"])
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id == "jsmith"
        assert unresolved == []

    def test_unresolved_external(self):
        people = [
            Person(id="jsmith", name="John Smith", aliases=["J. Smith"]),
        ]
        pub = self._make_pub(["E. E. Jones"])
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id is None
        assert "E. E. Jones" in unresolved

    def test_mixed_resolved_and_unresolved(self):
        people = [
            Person(id="jsmith", name="John Smith", aliases=["J. Smith"]),
            Person(id="jdoe", name="Jane Doe", aliases=["J. A. Doe"]),
        ]
        pub = self._make_pub(["J. Smith", "E. External", "J. A. Doe"])
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id == "jsmith"
        assert pub.authors[1].person_id is None
        assert pub.authors[2].person_id == "jdoe"
        assert "E. External" in unresolved

    def test_empty_people(self):
        pub = self._make_pub(["J. Smith"])
        unresolved = resolve_authors([pub], [])
        assert unresolved == []
        assert pub.authors[0].person_id is None


class TestResolveProjects:
    def _make_pub(self, project_ids):
        return Publication(
            bib_id="test",
            title="Test",
            authors=[],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
            project_ids=project_ids,
        )

    def test_valid_projects(self):
        projects = [Project(id="gardenbot", title="Robot Gardening")]
        pub = self._make_pub(["gardenbot"])
        unknown = resolve_projects([pub], projects)
        assert unknown == []

    def test_unknown_project(self):
        projects = [Project(id="gardenbot", title="Robot Gardening")]
        pub = self._make_pub(["gardenbot", "nonexistent"])
        unknown = resolve_projects([pub], projects)
        assert "nonexistent" in unknown


class TestComputeBacklinks:
    def test_people_backlinks(self):
        pub = Publication(
            bib_id="smith2024",
            title="Test",
            authors=[Author(name="J. Smith", person_id="jsmith")],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
        )
        person = Person(id="jsmith", name="John Smith")
        data = LabData(publications=[pub], people=[person], projects=[])
        compute_backlinks(data)
        assert "smith2024" in person.publication_ids
        assert person.publication_count == 1

    def test_project_backlinks(self):
        pub = Publication(
            bib_id="smith2024",
            title="Test",
            authors=[Author(name="J. Smith", person_id="jsmith")],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
            project_ids=["gardenbot"],
        )
        person = Person(id="jsmith", name="John Smith")
        project = Project(id="gardenbot", title="Robot Gardening")
        data = LabData(publications=[pub], people=[person], projects=[project])
        compute_backlinks(data)
        assert "smith2024" in project.publication_ids
        assert "jsmith" in project.people_ids

    def test_no_duplicate_backlinks(self):
        """Running compute_backlinks twice should not duplicate entries."""
        pub = Publication(
            bib_id="smith2024",
            title="Test",
            authors=[Author(name="J. Smith", person_id="jsmith")],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
        )
        person = Person(id="jsmith", name="John Smith")
        data = LabData(publications=[pub], people=[person], projects=[])
        compute_backlinks(data)
        compute_backlinks(data)
        assert person.publication_ids.count("smith2024") == 1


class TestLoadPeople:
    def test_load_fixtures(self):
        people = load_people(str(FIXTURES / "people.yaml"))
        assert len(people) == 3
        pi = next(p for p in people if p.id == "jsmith")
        assert pi.role == "pi"
        assert pi.status == "current"
        assert "J. Smith" in pi.aliases

        alumni = next(p for p in people if p.id == "jdoe")
        assert alumni.status == "alumni"
        assert alumni.degree == "PhD"
        assert alumni.end_year == 2023

    def test_missing_file(self):
        assert load_people("/nonexistent/path.yaml") == []


class TestLoadProjects:
    def test_load_fixtures(self):
        projects = load_projects(str(FIXTURES / "projects.yaml"))
        assert len(projects) == 2
        rf = next(p for p in projects if p.id == "gardenbot")
        assert rf.title == "Robot-Assisted Gardening"
        assert rf.status == "active"

    def test_missing_file(self):
        assert load_projects("/nonexistent/path.yaml") == []


class TestAssembleEndToEnd:
    def test_full_pipeline(self):
        """End-to-end test: config → LabData with resolved links."""
        config = LabDataConfig(
            bib_dir=str(FIXTURES),
            bib_files=[BibFile(name="sample.bib", category="Test Papers")],
            people_file=str(FIXTURES / "people.yaml"),
            projects_file=str(FIXTURES / "projects.yaml"),
        )
        data = assemble(config)

        # Publications parsed
        assert len(data.publications) == 3

        # Authors resolved for lab members
        smith_pub = next(p for p in data.publications if p.bib_id == "smith2024robot")
        smith_author = next(a for a in smith_pub.authors if "Smith" in a.name)
        assert smith_author.person_id == "jsmith"

        # External author NOT resolved
        jones_pub = next(p for p in data.publications if p.bib_id == "jones2023preprint")
        jones_author = jones_pub.authors[0]
        assert jones_author.person_id is None

        # Projects resolved
        assert "gardenbot" in smith_pub.project_ids

        # Back-links computed
        jsmith = next(p for p in data.people if p.id == "jsmith")
        assert jsmith.publication_count > 0
        assert "smith2024robot" in jsmith.publication_ids

        rf = next(p for p in data.projects if p.id == "gardenbot")
        assert len(rf.publication_ids) > 0
        assert "jsmith" in rf.people_ids

    def test_without_people_or_projects(self):
        """Should work with just bib files, no people/projects."""
        config = LabDataConfig(
            bib_dir=str(FIXTURES),
            bib_files=[BibFile(name="sample.bib", category="Test Papers")],
        )
        data = assemble(config)
        assert len(data.publications) == 3
        assert data.people == []
        assert data.projects == []

    def test_to_dict(self):
        """Verify the full output serializes cleanly."""
        config = LabDataConfig(
            bib_dir=str(FIXTURES),
            bib_files=[BibFile(name="sample.bib", category="Test Papers")],
            people_file=str(FIXTURES / "people.yaml"),
            projects_file=str(FIXTURES / "projects.yaml"),
        )
        data = assemble(config)
        d = data.to_dict()
        assert "publications" in d
        assert "people" in d
        assert "projects" in d
        assert len(d["publications"]) == 3
        # Check structured author format
        first_pub = d["publications"][0]
        assert isinstance(first_pub["authors"], list)
        assert "name" in first_pub["authors"][0]
