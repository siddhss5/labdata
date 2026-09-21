"""Tests for the resolver: author matching, project resolution, back-linking."""

import pytest
from pathlib import Path

from labdata.models import Author, Contributor, Work, Person, Project, LabData
from labdata.loaders import load_collaborators, load_people, load_projects
from labdata.resolver import (
    normalize_name,
    is_abbreviated,
    build_alias_index,
    shared_declarations,
    fuzzy_match,
    fuzzy_matches,
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

    def test_ties_are_all_returned_sorted(self):
        index = {"dina lee": "zlee", "dena lee": "alee", "alice adams": "aadams"}
        assert fuzzy_matches("Dana Lee", index, threshold=0.8) == ["alee", "zlee"]
        assert fuzzy_match("Dana Lee", index, threshold=0.8) == "alee"
        assert fuzzy_matches("H. Zhang", {"h zhang": "hz"}) == []


class TestMatchForm:
    """The abbreviated form, which the document never shows.

    The resolver reads it only where the input is itself abbreviated, and
    only against a declared name or alias (#24).
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


# The three corpus authorships #56 section 7 predicted would move once
# matching read the full name rather than the abbreviated form:
# (given, von, family, who the abbreviated form found, who they resolve to
# now). The first two are rows #24 owned (`identity.full_name` and
# `names.same_initial_alan`). The third is the one #56 predicted would move
# through a fuzzy match on the full name; a fuzzy match now links nothing, so
# it stays unresolved and is reported as a suggestion instead.
MATCHED_ON_THE_FULL_NAME = [
    ("Frank", None, "Fischer", None, "ffischer"),
    ("Alan", None, "Kim", "akim", "alankim"),
    ("Grace-Ann", None, "Green$^*$", None, None),
]


class TestTheResolverMatchesTheFullName:
    """#24: a full name is matched as written, and never abbreviated to find
    someone who declared the abbreviation."""

    PEOPLE = [
        Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
        Person(id="akim", name="Alex Kim", aliases=["A. Kim"]),
        Person(id="alankim", name="Alan Kim"),
        Person(id="ffischer", name="Frank Fischer"),
        Person(id="ggreen", name="Grace-Ann Green", aliases=["G.-A. Green"]),
    ]

    def resolve(self, author):
        work = Work(bib_id="w", title="T", category="C", entry_type="article",
                    year=2024, authors=[author])
        resolve_authors([work], self.PEOPLE)
        return work.authors[0].person_id

    @pytest.mark.parametrize(
        "given,von,family,on_match_form,on_full_name",
        MATCHED_ON_THE_FULL_NAME,
        ids=[row[2] for row in MATCHED_ON_THE_FULL_NAME])
    def test_each_predicted_authorship_resolves_on_the_full_name(
            self, given, von, family, on_match_form, on_full_name):
        author = Author(name=" ".join(p for p in (given, von, family) if p),
                        position=1, given=given, von=von, family=family)
        assert self.resolve(author) == on_full_name

    def test_the_abbreviated_form_would_have_answered_differently(self):
        """So the rows above are about which form is matched, not a coincidence."""
        index = build_alias_index(self.PEOPLE)
        moved = [row for row in MATCHED_ON_THE_FULL_NAME if row[3] != row[4]]
        assert len(moved) == 2
        for given, von, family, on_match_form, _ in moved:
            author = Author(name=f"{given} {family}", given=given, family=family)
            assert index.get(normalize_name(match_form(author))) == on_match_form

    @pytest.mark.parametrize(
        "given,von,family,on_match_form,on_full_name",
        MATCHED_ON_THE_FULL_NAME,
        ids=[row[2] for row in MATCHED_ON_THE_FULL_NAME])
    @pytest.mark.parametrize("display", [
        "Alice Adams", "Alex Kim", "A. Kim", "Somebody Else", ""])
    def test_the_display_name_never_decides(
            self, given, von, family, on_match_form, on_full_name, display):
        """`name` is display-only: a name that disagrees with the parts --
        including one that is another member's name -- resolves as the parts
        say, whatever it is."""
        author = Author(name=display, position=1, given=given, von=von,
                        family=family)
        assert self.resolve(author) == on_full_name

    def test_parts_that_are_nobody_stay_nobody_under_a_members_name(self):
        author = Author(name="Alice Adams", position=1, given="Quentin",
                        family="Quinn")
        assert self.resolve(author) is None

    def test_an_abbreviated_name_still_reaches_its_declared_alias(self):
        author = Author(name="A. Adams", position=1, given="A.", family="Adams")
        assert self.resolve(author) == "aadams"


class TestMatchingPolicy:
    """The order `match()` applies, and what it reports instead of guessing."""

    def run(self, people, *authors, editors=()):
        work = Work(bib_id="k1", title="T", category="C", entry_type="article",
                    year=2024, source_file="w.bib", authors=list(authors),
                    editors=list(editors))
        warnings = []
        unresolved = resolve_authors([work], people, warnings=warnings,
                                     bib_dir="bib")
        return work, unresolved, warnings

    def test_an_ambiguous_initial_is_reported_with_its_location(self):
        people = [Person(id="akim", name="Alex Kim", aliases=["A. Kim"]),
                  Person(id="alankim", name="Alan Kim")]
        work, unresolved, warnings = self.run(
            people, Author(name="Bob Brown", position=1, given="Bob", family="Brown"),
            Author(name="A. Kim", position=2, given="A.", family="Kim"))
        author = work.authors[1]
        assert author.person_id is None
        assert author.resolution_status == "ambiguous"
        assert author.resolution_method is None
        assert unresolved == ["A. Kim", "Bob Brown"]
        assert warnings == [
            "RESOLVE-AMBIGUOUS-NAME bib/w.bib:k1:author: position 2, 'A. Kim', "
            "fits more than one person and is left unresolved: akim, alankim"]

    def test_two_people_declaring_one_full_name_is_ambiguous(self):
        people = [Person(id="lee1", name="Lin Lee"), Person(id="lee2", name="Lin Lee")]
        work, _, warnings = self.run(
            people, Author(name="Lin Lee", position=1, given="Lin", family="Lee"))
        assert work.authors[0].person_id is None
        assert work.authors[0].resolution_status == "ambiguous"
        assert [w.split()[0] for w in warnings] == ["RESOLVE-AMBIGUOUS-NAME"]

    def test_a_near_miss_is_suggested_and_not_linked(self):
        people = [Person(id="ddavis", name="Dave Davis", aliases=["D. Davis"])]
        work, unresolved, warnings = self.run(
            people, Author(name="Dave M. Davis", position=1, given="Dave M.",
                           family="Davis"))
        assert work.authors[0].person_id is None
        assert work.authors[0].resolution_status == "unresolved"
        assert unresolved == ["Dave M. Davis"]
        assert warnings == [
            "RESOLVE-SUGGESTION bib/w.bib:k1:author: position 1, 'Dave M. Davis', "
            "matched no person but may be ddavis; not linked, declare an alias "
            "if it is"]

    def test_a_fuller_name_is_not_folded_into_a_declared_initial(self):
        """`Alan Kim` is not the Kim who declared `A. Kim`: a suggestion only."""
        people = [Person(id="akim", name="Alex Kim", aliases=["A. Kim"])]
        work, _, warnings = self.run(
            people, Author(name="Alan Kim", position=1, given="Alan", family="Kim"))
        assert work.authors[0].person_id is None
        assert [w.split()[0] for w in warnings] == ["RESOLVE-SUGGESTION"]
        assert "may be akim" in warnings[0]

    def test_an_initial_nobody_declared_is_suggested_and_not_linked(self):
        people = [Person(id="ffischer", name="Frank Fischer")]
        work, _, warnings = self.run(
            people, Author(name="F. Fischer", position=1, given="F.", family="Fischer"))
        assert work.authors[0].person_id is None
        assert "may be ffischer" in warnings[0]

    def test_an_external_name_is_reported_by_nothing(self):
        people = [Person(id="aadams", name="Alice Adams", aliases=["A. Adams"])]
        _, unresolved, warnings = self.run(
            people, Author(name="Quentin Quinn", position=1, given="Quentin",
                           family="Quinn"))
        assert unresolved == ["Quentin Quinn"] and warnings == []

    def test_a_partly_abbreviated_name_reaches_its_declared_alias(self):
        people = [Person(id="bbrown", name="Bob Brown", aliases=["B. A. Brown"]),
                  Person(id="bbrown2", name="Bill A. Brown")]
        work, _, warnings = self.run(
            people, Author(name="Bob A. Brown", position=1, given="Bob A.",
                           family="Brown"))
        assert work.authors[0].person_id == "bbrown" and warnings == []

    def test_particles_suffixes_and_hyphens_are_compared_as_parts(self):
        people = [Person(id="vvdb", name="Victor van den Berg",
                         aliases=["V. van den Berg"]),
                  Person(id="jsmith", name="John Smith, Jr.", aliases=["J. Smith, Jr."]),
                  Person(id="jsmithsr", name="James Smith, Sr."),
                  Person(id="gagreen", name="Grace-Ann Green", aliases=["G.-A. Green"]),
                  Person(id="gbgreen", name="Grace-Beth Green")]
        work, _, warnings = self.run(
            people,
            Author(name="V. van den Berg", position=1, given="V.",
                   von="van den", family="Berg"),
            Author(name="J. Smith Jr.", position=2, given="J.", family="Smith",
                   suffix="Jr."),
            Author(name="John Smith Jr.", position=3, given="John", family="Smith",
                   suffix="Jr."),
            Author(name="G.-A. Green", position=4, given="G.-A.", family="Green"))
        assert [a.person_id for a in work.authors] == [
            "vvdb", "jsmith", "jsmith", "gagreen"]
        assert warnings == []

    def test_a_brace_protected_name_matches_only_as_written(self):
        people = [Person(id="acme", name="Acme Robotics")]
        work, _, warnings = self.run(
            people, Author(name="Acme Robotics", position=1, literal="Acme Robotics"),
            Author(name="Acme Robots", position=2, literal="Acme Robots"))
        assert [a.person_id for a in work.authors] == ["acme", None]

    def test_a_star_in_a_name_is_a_near_miss_and_not_linked(self):
        """A star that is not a marker is part of the name, and a name with a
        star in it is not the person's name."""
        people = [Person(id="astar", name="Alice Star")]
        work, unresolved, warnings = self.run(
            people, Author(name="Alice Star*", position=1, given="Alice",
                           family="Star*"))
        author = work.authors[0]
        assert author.person_id is None
        assert (author.resolution_status, author.resolution_method) == ("unresolved", None)
        assert unresolved == ["Alice Star*"]
        assert warnings == [
            "RESOLVE-SUGGESTION bib/w.bib:k1:author: position 1, 'Alice Star*', "
            "matched no person but may be astar; not linked, declare an alias "
            "if it is"]

    def test_tied_near_misses_are_all_suggested_in_sorted_order(self):
        """Two people equally close are both suggested, whatever their order
        in `people.yaml`."""
        author = dict(name="Dana Lee", position=1, given="Dana", family="Lee")
        for people in ([Person(id="zlee", name="Dina Lee"),
                        Person(id="alee", name="Dena Lee")],
                       [Person(id="alee", name="Dena Lee"),
                        Person(id="zlee", name="Dina Lee")]):
            _, _, warnings = self.run(people, Author(**author))
            assert len(warnings) == 1
            assert "may be alee, zlee;" in warnings[0]

    def test_editors_are_matched_and_reported_the_same_way(self):
        people = [Person(id="akim", name="Alex Kim", aliases=["A. Kim"]),
                  Person(id="alankim", name="Alan Kim")]
        work, unresolved, warnings = self.run(
            people, editors=[Contributor(name="A. Kim", position=1, given="A.",
                                         family="Kim")])
        assert work.editors[0].person_id is None
        assert unresolved == []
        assert warnings[0].startswith(
            "RESOLVE-AMBIGUOUS-NAME bib/w.bib:k1:editor: position 1")


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


class TestLoadCollaborators:
    def test_load(self, tmp_path):
        path = tmp_path / "collaborators.yaml"
        path.write_text('- name: "Priya Patel"\n  aliases: ["P. Patel"]\n'
                        '- name: "Quentin Quinn"\n', encoding="utf-8")
        loaded = load_collaborators(str(path))
        assert [(c.name, c.aliases) for c in loaded] == [
            ("Priya Patel", ["P. Patel"]), ("Quentin Quinn", [])]

    def test_missing_or_empty_file(self, tmp_path):
        assert load_collaborators("/nonexistent/path.yaml") == []
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        assert load_collaborators(str(empty)) == []


class TestDeclaredCollaboratorGrouping:
    """`collaborators_file` groups spellings; it never produces a person."""

    def assemble(self, people, declared, *authors_by_work):
        from labdata.assembler import declared_collaborators, group_collaborators
        works = [Work(bib_id=f"w{i}", title="T", category="C", entry_type="article",
                      year=2020 + i, source_file="w.bib", authors=list(authors))
                 for i, authors in enumerate(authors_by_work)]
        warnings = []
        resolve_authors(works, people, warnings=warnings, bib_dir="bib")
        entries = declared_collaborators(declared, people, "c.yaml", warnings)
        return works, group_collaborators(works, "bib", warnings, entries, people), warnings

    def test_a_declared_alias_joins_one_person_and_not_another(self):
        from labdata.loaders import DeclaredCollaborator
        works, collaborators, warnings = self.assemble(
            [], [DeclaredCollaborator("Priya Patel", ["P. Patel"])],
            [Author(name="Priya Patel", position=1, given="Priya", family="Patel")],
            [Author(name="P. Patel", position=1, given="P.", family="Patel")],
            [Author(name="Pradeep Patel", position=1, given="Pradeep", family="Patel")])
        grouped = {c.name: (c.grouped_by, c.work_ids) for c in collaborators}
        assert grouped == {"Priya Patel": ("declared", ["w0", "w1"]),
                           "Pradeep Patel": ("normalized_name", ["w2"])}
        assert [a.person_id for w in works for a in w.authors] == [None] * 3
        assert warnings == []

    def test_a_name_fitting_two_declared_collaborators_is_reported(self):
        from labdata.loaders import DeclaredCollaborator
        _, collaborators, warnings = self.assemble(
            [], [DeclaredCollaborator("Priya Patel", ["P. Patel"]),
                           DeclaredCollaborator("Pradeep Patel")],
            [Author(name="P. Patel", position=2, given="P.", family="Patel")])
        assert [(c.name, c.grouped_by) for c in collaborators] == [
            ("P. Patel", "normalized_name")]
        assert warnings == [
            "RESOLVE-AMBIGUOUS-NAME bib/w.bib:w0:author: position 2, 'P. Patel', "
            "fits more than one declared collaborator or member and is grouped "
            "by its own name: collaborator:pradeep patel, collaborator:priya patel"]

    def test_a_member_competes_with_a_declared_collaborator(self):
        """`P. Patel` could be the member as well, so it joins neither."""
        from labdata.loaders import DeclaredCollaborator
        people = [Person(id="ppatel", name="Paul Patel")]
        works, collaborators, warnings = self.assemble(
            people, [DeclaredCollaborator("Priya Patel", ["P. Patel"])],
            [Author(name="P. Patel", position=1, given="P.", family="Patel")])
        assert works[0].authors[0].person_id is None
        assert [c.grouped_by for c in collaborators] == ["normalized_name"]
        assert any(w.startswith("RESOLVE-AMBIGUOUS-NAME") and "person:ppatel" in w
                   for w in warnings)

    def test_a_declared_name_that_is_a_member_is_left_to_the_member(self):
        from labdata.loaders import DeclaredCollaborator
        people = [Person(id="aadams", name="Alice Adams", aliases=["A. Adams"])]
        works, collaborators, warnings = self.assemble(
            people, [DeclaredCollaborator("Alice Adams")],
            [Author(name="Alice Adams", position=1, given="Alice", family="Adams")])
        assert works[0].authors[0].person_id == "aadams"
        assert collaborators == []
        assert warnings == [
            "RESOLVE-COLLABORATOR-ALIAS-IS-MEMBER c.yaml:Alice Adams:name: "
            "'Alice Adams' is also declared by aadams; the member keeps it and "
            "the collaborator entry is not used for it"]


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



class TestPeopleAndProjectsFiles:
    """What is wrong with a people or projects file, in its three classes."""

    def load(self, tmp_path, loader, text):
        path = tmp_path / "records.yaml"
        path.write_text(text, encoding="utf-8")
        errors, diagnostics, warnings = [], [], []
        records = loader(str(path), errors, diagnostics, warnings)
        strip = lambda lines: [l.replace(str(path), "f.yaml") for l in lines]
        return records, strip(errors), strip(diagnostics), strip(warnings)

    def test_an_empty_file_is_no_records(self, tmp_path):
        assert self.load(tmp_path, load_people, "") == ([], [], [], [])

    def test_a_person_that_is_not_a_mapping(self, tmp_path):
        records, errors, _, _ = self.load(
            tmp_path, load_people, "- just a string\n- {id: p, name: P, role: r}\n")
        assert [r.id for r in records] == ["p"]
        assert errors == ["PEOPLE-NOT-A-LIST f.yaml::: entry 1 is not a mapping"]

    def test_missing_id_and_name(self, tmp_path):
        records, errors, _, _ = self.load(
            tmp_path, load_people, "- {name: N}\n- {id: p, name: ' '}\n")
        assert records == []
        assert errors == ["PEOPLE-FIELD-MISSING f.yaml::id: entry 1 has no id",
                          "PEOPLE-FIELD-MISSING f.yaml:p:name: entry 2 has no name"]

    def test_a_projects_file_that_is_not_a_list_is_no_projects(self, tmp_path):
        assert self.load(tmp_path, load_projects, "p: {title: T}\n") == ([], [], [], [])

    def test_duplicate_ids_are_kept_and_reported(self, tmp_path):
        records, _, diagnostics, _ = self.load(
            tmp_path, load_projects,
            "- {id: p, title: A}\n- {id: p, title: B}\n")
        assert [r.title for r in records] == ["A", "B"]
        assert diagnostics == [
            "PROJECTS-ID-DUPLICATE f.yaml:p:id: the id 'p' is declared more than once"]

    @pytest.mark.parametrize("status, reported", [
        ("active", False), ("completed", False), ("paused", True)])
    def test_project_status(self, tmp_path, status, reported):
        _, _, _, warnings = self.load(
            tmp_path, load_projects, f"- {{id: p, title: A, status: {status}}}\n")
        assert bool(warnings) is reported

    def test_a_missing_project_status_is_active_and_not_reported(self, tmp_path):
        records, _, _, warnings = self.load(tmp_path, load_projects,
                                            "- {id: p, title: A}\n")
        assert records[0].status == "active" and warnings == []

    @pytest.mark.parametrize("role, reported", [
        ("'research scientist'", False), ("visitor", False),
        ("''", True), ("7", True), ("[a]", True), (None, True)])
    def test_any_nonempty_role_is_accepted(self, tmp_path, role, reported):
        entry = "- {id: p, name: P" + (f", role: {role}" if role else "") + "}\n"
        _, _, _, warnings = self.load(tmp_path, load_people, entry)
        assert [w.startswith("PEOPLE-ROLE-INVALID f.yaml:p:role:")
                for w in warnings] == ([True] if reported else [])

    @pytest.mark.parametrize("status, reported", [
        ("current", False), ("alumni", False), ("retired", True)])
    def test_person_status(self, tmp_path, status, reported):
        _, _, _, warnings = self.load(
            tmp_path, load_people, f"- {{id: p, name: P, role: r, status: {status}}}\n")
        assert [w.startswith("PEOPLE-STATUS-INVALID f.yaml:p:status:")
                for w in warnings] == ([True] if reported else [])

    def test_without_lists_problems_go_to_standard_error(self, tmp_path, capsys):
        path = tmp_path / "people.yaml"
        path.write_text("- {id: p}\n", encoding="utf-8")
        assert load_people(str(path)) == []
        assert "Warning: PEOPLE-FIELD-MISSING" in capsys.readouterr().err


class TestSharedDeclarations:
    def test_a_name_shared_with_an_alias_is_reported_once(self):
        people = [Person(id="aadams", name="Alice Adams", aliases=["A. Adams"]),
                  Person(id="aadamson", name="A. Adams", aliases=[]),
                  Person(id="adup", name="A Adams", aliases=["a. adams"])]
        [line] = shared_declarations(people, "people.yaml")
        assert line.startswith("PEOPLE-ALIAS-AMBIGUOUS people.yaml:aadamson:name: ")
        assert "aadams, aadamson, adup" in line

    def test_a_person_repeating_their_own_spelling_is_not_reported(self):
        people = [Person(id="aadams", name="Alice Adams",
                         aliases=["Alice Adams", "A. Adams", "A Adams"])]
        assert shared_declarations(people, "people.yaml") == []
