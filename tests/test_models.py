"""Tests for sslabdata data models."""

from sslabdata import (
    Author, Collaborator, Contributor, LabData, Link, Person, Project, Venue,
    Work,
)


class TestAuthor:
    def test_basic(self):
        a = Author(name="Bob Brown")
        assert a.name == "Bob Brown"
        assert a.person_id is None

    def test_resolved(self):
        a = Author(name="Bob Brown", person_id="bbrown")
        assert a.person_id == "bbrown"

    def test_equal_contribution(self):
        assert Author(name="Bob Brown").equal_contribution is False
        marked = Author(name="Bob Brown", equal_contribution=True)
        assert marked.to_dict()["equal_contribution"] is True

    def test_contributor_reference_and_resolution(self):
        """An authorship carries both references and its resolution record."""
        d = Author(name="Bob Brown", position=1, person_id="bbrown",
                   resolution_status="resolved", resolution_method="exact").to_dict()
        assert d["position"] == 1
        assert d["person_id"] == "bbrown"
        assert d["collaborator_key"] is None
        assert d["resolution"] == {"status": "resolved", "method": "exact"}
        assert d["derived"] == {}

    def test_unresolved_authorship_references_a_grouping(self):
        d = Author(name="Trent Turner", position=2,
                   collaborator_key="trent-turner-9d9cc45d").to_dict()
        assert d["person_id"] is None
        assert d["collaborator_key"] == "trent-turner-9d9cc45d"
        assert d["resolution"] == {"status": "unresolved", "method": None}


class TestContributor:
    def test_editor_has_no_authorship_fields(self):
        """An editor is not an authorship: no grouping key, no marker."""
        d = Contributor(name="Quentin Quinn", position=1, family="Quinn").to_dict()
        assert "collaborator_key" not in d
        assert "equal_contribution" not in d
        assert d["family"] == "Quinn"


class TestWork:
    def test_minimal(self):
        work = Work(
            bib_id="brown2024",
            title="A Paper",
            authors=[Author(name="Bob Brown")],
            year=2024,
            category="Conference Papers",
            entry_type="inproceedings",
        )
        assert work.bib_id == "brown2024"
        assert work.venue is None
        assert work.project_ids == []
        assert work.links == {}

    def test_to_dict(self):
        work = Work(
            bib_id="brown2024",
            title="A Paper",
            authors=[
                Author(name="Bob Brown", position=1, person_id="bbrown"),
                Author(name="Erin External", position=2,
                       collaborator_key="erin-external-00000000"),
            ],
            year=2024,
            category="Conference Papers",
            entry_type="inproceedings",
            source_file="conference.bib",
            venue=Venue(kind="conference", name="RSS"),
            pages="1--10",
            identifiers={"doi": ["10.1234/test"]},
            links={"doi": [Link(url="https://doi.org/10.1234/test",
                                origin="derived")]},
            project_ids=["robotics"],
        )
        d = work.to_dict()
        assert d["bib_id"] == "brown2024"
        assert d["source"] == {"file": "conference.bib", "key": "brown2024"}
        assert d["authors"][0]["person_id"] == "bbrown"
        assert d["authors"][1]["person_id"] is None
        assert d["authors"][1]["collaborator_key"] == "erin-external-00000000"
        assert d["venue"] == {"kind": "conference", "name": "RSS"}
        assert d["pages"] == "1--10"
        assert d["identifiers"] == {"doi": ["10.1234/test"]}
        assert d["links"]["doi"] == [{
            "url": "https://doi.org/10.1234/test", "label": None,
            "origin": "derived",
            "verification": {"status": "unchecked", "checked_at": None},
        }]
        assert d["project_ids"] == ["robotics"]

    def test_every_declared_property_is_present_and_null_when_it_does_not_apply(self):
        """The closed-object policy: nothing is omitted, absent values are null."""
        d = Work(bib_id="x", title="", authors=[], year=None, category="C",
                 entry_type="misc").to_dict()
        for key in ("venue", "volume", "number", "pages", "series", "edition",
                    "publisher", "address", "organization", "chapter", "month",
                    "howpublished", "type", "abstract", "note", "bibtex",
                    "year"):
            assert key in d and d[key] is None, key
        assert d["editors"] == []
        assert d["identifiers"] == {} and d["links"] == {}
        assert d["derived"] == {}


class TestPerson:
    def test_current_member(self):
        p = Person(
            id="bbrown",
            name="Bob Brown",
            role="phd_student",
            status="current",
            start_year=2020,
        )
        d = p.to_dict()
        assert d["id"] == "bbrown"
        assert d["status"] == "current"
        # Declared, and null rather than absent, whatever the status.
        assert d["end_year"] is None
        assert d["degree"] is None

    def test_alumni(self):
        p = Person(
            id="bbrown",
            name="Bob Brown",
            role="phd_student",
            status="alumni",
            start_year=2018,
            end_year=2023,
            degree="PhD",
            thesis_title="Robot Manipulation",
            current_position="Research Scientist at Example Robotics",
        )
        d = p.to_dict()
        assert d["status"] == "alumni"
        assert d["end_year"] == 2023
        assert d["degree"] == "PhD"
        assert d["current_position"] == "Research Scientist at Example Robotics"

    def test_aliases_are_read_for_matching_and_never_emitted(self):
        d = Person(id="bbrown", name="Bob Brown", aliases=["B. Brown"]).to_dict()
        assert "aliases" not in d


class TestCollaborator:
    def test_to_dict(self):
        c = Collaborator(
            key="trent-turner-9d9cc45d", name="Trent Turner", family="Turner",
            given="Trent", name_variants=["Trent Turner"],
            authorships=[{"work_id": "brown2024", "position": 2}],
            work_ids=["brown2024"], work_count=1, authorship_count=1,
            last_year=2024,
        )
        d = c.to_dict()
        assert d["key"] == "trent-turner-9d9cc45d"
        assert d["grouped_by"] == "normalized_name"
        assert d["name_kind"] == "personal"
        assert d["authorships"] == [{"work_id": "brown2024", "position": 2}]
        assert d["work_count"] == 1 and d["authorship_count"] == 1


class TestProject:
    def test_basic(self):
        p = Project(id="gardenbot", title="Robot-Assisted Gardening")
        assert p.status == "active"
        assert p.work_ids == []
        assert p.people_ids == []

    def test_to_dict(self):
        p = Project(
            id="gardenbot",
            title="Robot-Assisted Gardening",
            description="Autonomous gardening systems",
            website="https://gardenbot.example.org",
            status="active",
            work_ids=["brown2024", "adams2023"],
            people_ids=["bbrown", "aadams"],
        )
        d = p.to_dict()
        assert d["id"] == "gardenbot"
        assert len(d["work_ids"]) == 2
        assert len(d["people_ids"]) == 2


class TestLabData:
    def test_empty(self):
        data = LabData()
        d = data.to_dict()
        assert d["works"] == []
        assert d["people"] == []
        assert d["projects"] == []
        # The header is always emitted, so no header and an empty header are
        # the same thing rather than one being invisible.
        assert d["lab"] == {}

    def test_generator_names_the_compiler_and_carries_no_timestamp(self):
        import sslabdata

        generator = LabData().to_dict()["generator"]
        assert generator == {"name": "sslabdata", "version": sslabdata.__version__,
                             "schema_version": 4}

    def test_to_dict(self):
        data = LabData(
            works=[
                Work(
                    bib_id="brown2024",
                    title="A Paper",
                    authors=[Author(name="Bob Brown")],
                    year=2024,
                    category="Conference Papers",
                    entry_type="inproceedings",
                )
            ],
            people=[Person(id="bbrown", name="Bob Brown")],
            projects=[Project(id="test", title="Test Project")],
        )
        d = data.to_dict()
        assert len(d["works"]) == 1
        assert len(d["people"]) == 1
        assert len(d["projects"]) == 1
        assert d["works"][0]["bib_id"] == "brown2024"
