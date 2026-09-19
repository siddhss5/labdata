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


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("A. Adams") == "a adams"

    def test_accents(self):
        assert normalize_name("H. Müller") == "h muller"

    def test_periods(self):
        assert normalize_name("A.J. Adams") == "aj adams"

    def test_whitespace(self):
        assert normalize_name("  A.  Adams  ") == "a adams"

    def test_superscript(self):
        assert normalize_name("A. Adams<sup>*</sup>") == "a adams"


class TestIsAbbreviated:
    def test_single_initial_surname(self):
        assert is_abbreviated("a kim") is True
        assert is_abbreviated("h zhang") is True

    def test_multi_initial(self):
        assert is_abbreviated("a j kim") is False

    def test_full_name(self):
        assert is_abbreviated("alice adams") is False

    def test_single_word(self):
        assert is_abbreviated("kim") is False


class TestBuildAliasIndex:
    def test_indexes_name_and_aliases(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
        ]
        index = build_alias_index(people)
        assert "alice adams" in index
        assert "a adams" in index
        assert index["alice adams"] == "aadams"
        assert index["a adams"] == "aadams"

    def test_multiple_people(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
            Person(id="bbrown", name="Bob Brown", aliases=["B. Brown"]),
        ]
        index = build_alias_index(people)
        assert index["a adams"] == "aadams"
        assert index["b brown"] == "bbrown"

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
        index = {"alice adams": "aadams"}
        # "alice a adams" is close to "alice adams"
        result = fuzzy_match("Alice A. Adams", index, threshold=0.75)
        assert result == "aadams"

    def test_no_match(self):
        index = {"alice adams": "aadams"}
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
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
        ]
        pub = self._make_pub(["A. Adams"])
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id == "aadams"
        assert unresolved == []

    def test_unresolved_external(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
        ]
        pub = self._make_pub(["E. E. Jones"])
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id is None
        assert "E. E. Jones" in unresolved

    def test_mixed_resolved_and_unresolved(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
            Person(id="bbrown", name="Bob Brown", aliases=["B. A. Brown"]),
        ]
        pub = self._make_pub(["A. Adams", "E. External", "B. A. Brown"])
        unresolved = resolve_authors([pub], people)
        assert pub.authors[0].person_id == "aadams"
        assert pub.authors[1].person_id is None
        assert pub.authors[2].person_id == "bbrown"
        assert "E. External" in unresolved

    def test_empty_people(self):
        pub = self._make_pub(["A. Adams"])
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
            bib_id="adams2024",
            title="Test",
            authors=[Author(name="A. Adams", person_id="aadams")],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
        )
        person = Person(id="aadams", name="Alice Adams")
        data = LabData(publications=[pub], people=[person], projects=[])
        compute_backlinks(data)
        assert "adams2024" in person.publication_ids
        assert person.publication_count == 1

    def test_project_backlinks(self):
        pub = Publication(
            bib_id="adams2024",
            title="Test",
            authors=[Author(name="A. Adams", person_id="aadams")],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
            project_ids=["gardenbot"],
        )
        person = Person(id="aadams", name="Alice Adams")
        project = Project(id="gardenbot", title="Robot Gardening")
        data = LabData(publications=[pub], people=[person], projects=[project])
        compute_backlinks(data)
        assert "adams2024" in project.publication_ids
        assert "aadams" in project.people_ids

    def test_no_duplicate_backlinks(self):
        """Running compute_backlinks twice should not duplicate entries."""
        pub = Publication(
            bib_id="adams2024",
            title="Test",
            authors=[Author(name="A. Adams", person_id="aadams")],
            year=2024,
            venue="Test",
            category="Test",
            entry_type="article",
        )
        person = Person(id="aadams", name="Alice Adams")
        data = LabData(publications=[pub], people=[person], projects=[])
        compute_backlinks(data)
        compute_backlinks(data)
        assert person.publication_ids.count("adams2024") == 1


class TestLoadPeople:
    def test_load_fixtures(self):
        people = load_people(str(FIXTURES / "people.yaml"))
        assert len(people) == 3
        pi = next(p for p in people if p.id == "aadams")
        assert pi.role == "pi"
        assert pi.status == "current"
        assert "A. Adams" in pi.aliases

        alumni = next(p for p in people if p.id == "bbrown")
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
        adams_pub = next(p for p in data.publications if p.bib_id == "adams2024robot")
        adams_author = next(a for a in adams_pub.authors if "Adams" in a.name)
        assert adams_author.person_id == "aadams"

        # External author NOT resolved
        jones_pub = next(p for p in data.publications if p.bib_id == "jones2023preprint")
        jones_author = jones_pub.authors[0]
        assert jones_author.person_id is None

        # Projects resolved
        assert "gardenbot" in adams_pub.project_ids

        # Back-links computed
        aadams = next(p for p in data.people if p.id == "aadams")
        assert aadams.publication_count > 0
        assert "adams2024robot" in aadams.publication_ids

        rf = next(p for p in data.projects if p.id == "gardenbot")
        assert len(rf.publication_ids) > 0
        assert "aadams" in rf.people_ids

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
