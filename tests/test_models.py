"""Tests for labdata data models."""

from labdata.models import Author, Publication, Person, Project, LabData


class TestAuthor:
    def test_basic(self):
        a = Author(name="B. Brown")
        assert a.name == "B. Brown"
        assert a.person_id is None

    def test_resolved(self):
        a = Author(name="B. Brown", person_id="bbrown")
        assert a.person_id == "bbrown"


class TestPublication:
    def test_minimal(self):
        pub = Publication(
            bib_id="brown2024",
            title="A Paper",
            authors=[Author(name="B. Brown")],
            year=2024,
            venue="*RSS*, 2024",
            category="Conference Papers",
            entry_type="inproceedings",
        )
        assert pub.bib_id == "brown2024"
        assert pub.pdf_url is None
        assert pub.project_ids == []

    def test_to_dict(self):
        pub = Publication(
            bib_id="brown2024",
            title="A Paper",
            authors=[
                Author(name="B. Brown", person_id="bbrown"),
                Author(name="E. External"),
            ],
            year=2024,
            venue="*RSS*, 2024",
            category="Conference Papers",
            entry_type="inproceedings",
            doi_url="https://doi.org/10.1234/test",
            project_ids=["robotics"],
        )
        d = pub.to_dict()
        assert d["bib_id"] == "brown2024"
        assert d["authors"][0]["person_id"] == "bbrown"
        assert d["authors"][1]["person_id"] is None
        assert d["doi_url"] == "https://doi.org/10.1234/test"
        assert d["project_ids"] == ["robotics"]


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
        assert "end_year" not in d
        assert "degree" not in d

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
            current_position="Research Scientist at Google",
        )
        d = p.to_dict()
        assert d["status"] == "alumni"
        assert d["end_year"] == 2023
        assert d["degree"] == "PhD"
        assert d["current_position"] == "Research Scientist at Google"


class TestProject:
    def test_basic(self):
        p = Project(id="gardenbot", title="Robot-Assisted Gardening")
        assert p.status == "active"
        assert p.publication_ids == []
        assert p.people_ids == []

    def test_to_dict(self):
        p = Project(
            id="gardenbot",
            title="Robot-Assisted Gardening",
            description="Autonomous gardening systems",
            website="https://gardenbot.example.org",
            status="active",
            publication_ids=["brown2024", "adams2023"],
            people_ids=["bbrown", "aadams"],
        )
        d = p.to_dict()
        assert d["id"] == "gardenbot"
        assert len(d["publication_ids"]) == 2
        assert len(d["people_ids"]) == 2


class TestLabData:
    def test_empty(self):
        data = LabData()
        d = data.to_dict()
        assert d["publications"] == []
        assert d["people"] == []
        assert d["projects"] == []

    def test_to_dict(self):
        data = LabData(
            publications=[
                Publication(
                    bib_id="brown2024",
                    title="A Paper",
                    authors=[Author(name="B. Brown")],
                    year=2024,
                    venue="RSS",
                    category="Conference Papers",
                    entry_type="inproceedings",
                )
            ],
            people=[Person(id="bbrown", name="Bob Brown")],
            projects=[Project(id="test", title="Test Project")],
        )
        d = data.to_dict()
        assert len(d["publications"]) == 1
        assert len(d["people"]) == 1
        assert len(d["projects"]) == 1
        assert d["publications"][0]["bib_id"] == "brown2024"
