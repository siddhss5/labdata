"""Tests for the resolver: author matching, project resolution, back-linking."""

import pytest
from pathlib import Path

from labdata.models import Author, Contributor, Work, Person, Project, LabData
from labdata.loaders import load_people, load_projects
from labdata.resolver import (
    normalize_name,
    is_abbreviated,
    build_alias_index,
    fuzzy_match,
    match_form,
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

    @pytest.mark.xfail(strict=True, reason="#24", raises=AssertionError)
    def test_same_initial_collision_without_alias(self):
        """An alias shared implicitly with another person's initials is ambiguous.

        Alan Kim declares no aliases, but "A. Kim" fits him as well as Alex Kim,
        so it must not resolve to Alex.
        """
        people = [
            Person(id="akim", name="Alex Kim", aliases=["A. Kim"]),
            Person(id="alankim", name="Alan Kim", aliases=[]),
        ]
        work = Work(
            bib_id="kim2024", title="Test", category="Test",
            entry_type="article", year=2024,
            authors=[Author(name="A. Kim", position=1, given="A.", family="Kim")],
        )
        unresolved = resolve_authors([work], people)
        assert work.authors[0].person_id is None
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


class TestMatchForm:
    """The private form the resolver matches on, which the document never shows.

    Splitting it from `Contributor.name` is what lets the emitted name become
    the full name without changing who resolves to whom (#56 section 7).
    """

    def test_given_names_are_abbreviated(self):
        assert match_form(Author(name="Alice Jane Adams", given="Alice Jane",
                                 family="Adams")) == "A. J. Adams"

    def test_a_hyphenated_given_name_keeps_both_initials(self):
        assert match_form(Author(name="Grace-Ann Green", given="Grace-Ann",
                                 family="Green")) == "G.-A. Green"

    def test_particles_and_suffixes(self):
        assert match_form(Author(name="Victor van den Berg", given="Victor",
                                 von="van den", family="Berg")) == \
            "V. van den Berg"
        assert match_form(Author(name="John Smith Jr.", given="John",
                                 family="Smith", suffix="Jr.")) == "J. Smith, Jr."

    def test_a_brace_protected_name_has_nothing_to_abbreviate(self):
        assert match_form(Author(name="Example Robotics Consortium",
                                 literal="Example Robotics Consortium")) == \
            "Example Robotics Consortium"

    def test_it_is_not_the_emitted_name(self):
        """The two are independent, which is the whole point of the split."""
        author = Author(name="Alice Adams", given="Alice", family="Adams")
        assert match_form(author) == "A. Adams"
        assert author.name == "Alice Adams"


class TestResolveAuthors:
    def _make_work(self, authors, editors=()):
        return Work(
            bib_id="test",
            title="Test",
            authors=list(authors),
            editors=list(editors),
            year=2024,
            category="Test",
            entry_type="article",
        )

    def _author(self, given, family, position=1):
        return Author(name=f"{given} {family}", position=position,
                      given=given, family=family)

    def test_exact_alias_match(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
        ]
        work = self._make_work([self._author("Alice", "Adams")])
        unresolved = resolve_authors([work], people)
        assert work.authors[0].person_id == "aadams"
        assert work.authors[0].resolution_status == "resolved"
        assert work.authors[0].resolution_method == "exact"
        assert unresolved == []

    def test_unresolved_external(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
        ]
        work = self._make_work([self._author("Erin E.", "Jones")])
        unresolved = resolve_authors([work], people)
        assert work.authors[0].person_id is None
        assert work.authors[0].resolution_status == "unresolved"
        assert work.authors[0].resolution_method is None
        # The readable name is what a human is asked to add to people.yaml,
        # not the private form the matcher compared.
        assert "Erin E. Jones" in unresolved

    def test_mixed_resolved_and_unresolved(self):
        people = [
            Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
            Person(id="bbrown", name="Bob Brown", aliases=["B. A. Brown"]),
        ]
        work = self._make_work([
            self._author("Alice", "Adams", 1),
            self._author("Erin", "External", 2),
            self._author("Bob A.", "Brown", 3),
        ])
        unresolved = resolve_authors([work], people)
        assert work.authors[0].person_id == "aadams"
        assert work.authors[1].person_id is None
        assert work.authors[2].person_id == "bbrown"
        assert "Erin External" in unresolved

    def test_editors_resolve_but_are_never_reported_as_unresolved(self):
        """Editing a volume is not an authorship, so an editor nobody matches
        is not an author labdata could not resolve."""
        people = [Person(id="aadams", name="Alice Adams", aliases=["A. Adams"])]
        editors = [Contributor(name="Alice Adams", position=1, given="Alice",
                               family="Adams"),
                   Contributor(name="Quentin Quinn", position=2, given="Quentin",
                               family="Quinn")]
        work = self._make_work([], editors)
        unresolved = resolve_authors([work], people)
        assert [e.person_id for e in work.editors] == ["aadams", None]
        assert unresolved == []

    def test_empty_people(self):
        work = self._make_work([self._author("Alice", "Adams")])
        unresolved = resolve_authors([work], [])
        assert unresolved == []
        assert work.authors[0].person_id is None


class TestResolveProjects:
    def _make_pub(self, project_ids):
        return Work(
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
    def _work(self, **changes):
        fields = dict(
            bib_id="adams2024",
            title="Test",
            authors=[Author(name="Alice Adams", position=1, person_id="aadams")],
            year=2024,
            category="Test",
            entry_type="article",
        )
        fields.update(changes)
        return Work(**fields)

    def test_people_backlinks(self):
        work = self._work()
        person = Person(id="aadams", name="Alice Adams")
        data = LabData(works=[work], people=[person], projects=[])
        compute_backlinks(data)
        assert "adams2024" in person.work_ids
        assert person.work_count == 1

    def test_project_backlinks(self):
        work = self._work(project_ids=["gardenbot"])
        person = Person(id="aadams", name="Alice Adams")
        project = Project(id="gardenbot", title="Robot Gardening")
        data = LabData(works=[work], people=[person], projects=[project])
        compute_backlinks(data)
        assert "adams2024" in project.work_ids
        assert "aadams" in project.people_ids

    def test_editors_are_not_authorships(self):
        """An editor back-links nothing: not the person, not the project."""
        work = self._work(
            authors=[],
            editors=[Contributor(name="Alice Adams", position=1,
                                 person_id="aadams")],
            project_ids=["gardenbot"])
        person = Person(id="aadams", name="Alice Adams")
        project = Project(id="gardenbot", title="Robot Gardening")
        data = LabData(works=[work], people=[person], projects=[project])
        compute_backlinks(data)
        assert person.work_ids == [] and person.work_count == 0
        assert project.work_ids == ["adams2024"]
        assert project.people_ids == []

    def test_no_duplicate_backlinks(self):
        """Running compute_backlinks twice should not duplicate entries."""
        work = self._work()
        person = Person(id="aadams", name="Alice Adams")
        data = LabData(works=[work], people=[person], projects=[])
        compute_backlinks(data)
        compute_backlinks(data)
        assert person.work_ids.count("adams2024") == 1


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

        # Works parsed
        assert len(data.works) == 3

        # Authors resolved for lab members
        adams_work = next(w for w in data.works if w.bib_id == "adams2024robot")
        adams_author = next(a for a in adams_work.authors if "Adams" in a.name)
        assert adams_author.person_id == "aadams"

        # External author NOT resolved, and grouped under a collaborator key
        jones_work = next(w for w in data.works if w.bib_id == "jones2023preprint")
        jones_author = jones_work.authors[0]
        assert jones_author.person_id is None
        assert jones_author.collaborator_key
        assert jones_author.collaborator_key in {c.key for c in data.collaborators}

        # Projects resolved
        assert "gardenbot" in adams_work.project_ids

        # Back-links computed
        aadams = next(p for p in data.people if p.id == "aadams")
        assert aadams.work_count > 0
        assert "adams2024robot" in aadams.work_ids

        rf = next(p for p in data.projects if p.id == "gardenbot")
        assert len(rf.work_ids) > 0
        assert "aadams" in rf.people_ids

    def test_without_people_or_projects(self):
        """Should work with just bib files, no people/projects."""
        config = LabDataConfig(
            bib_dir=str(FIXTURES),
            bib_files=[BibFile(name="sample.bib", category="Test Papers")],
        )
        data = assemble(config)
        assert len(data.works) == 3
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
        assert "works" in d
        assert "people" in d
        assert "projects" in d
        assert len(d["works"]) == 3
        # Check structured author format
        first_work = d["works"][0]
        assert isinstance(first_work["authors"], list)
        assert "name" in first_work["authors"][0]
