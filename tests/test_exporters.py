"""Tests for the exporters: YAML and JSON output."""

import json
import yaml
import pytest
from pathlib import Path

from labdata import (
    Author, ConfigurationError, LabData, Person, Project, Venue, Work,
    export_to_json, export_to_yaml,
)


@pytest.fixture
def sample_data():
    """A small LabData instance for testing exports."""
    work = Work(
        bib_id="adams2024robot",
        title="Robot Gardening",
        authors=[
            Author(name="Alice Adams", position=1, person_id="aadams",
                   equal_contribution=True),
            Author(name="Erin External", position=2,
                   collaborator_key="erin-external-00000000"),
        ],
        year=2024,
        venue=Venue(kind="conference", name="HRI"),
        category="Conference Papers",
        entry_type="inproceedings",
        identifiers={"doi": ["10.1234/test"]},
        project_ids=["gardenbot"],
    )
    person = Person(
        id="aadams", name="Alice Adams", role="pi", status="current",
        work_count=1, work_ids=["adams2024robot"],
    )
    project = Project(
        id="gardenbot", title="Robot-Assisted Gardening", status="active",
        work_ids=["adams2024robot"], people_ids=["aadams"],
    )
    return LabData(works=[work], people=[person], projects=[project])


class TestExportToYaml:
    def test_creates_file(self, tmp_path, sample_data):
        out = str(tmp_path / "output.yml")
        export_to_yaml(sample_data, out)
        assert Path(out).exists()

    def test_round_trip(self, tmp_path, sample_data):
        out = str(tmp_path / "output.yml")
        export_to_yaml(sample_data, out)
        with open(out, 'r') as f:
            loaded = yaml.safe_load(f)
        assert len(loaded["works"]) == 1
        assert loaded["works"][0]["bib_id"] == "adams2024robot"
        assert len(loaded["people"]) == 1
        assert loaded["people"][0]["id"] == "aadams"
        assert len(loaded["projects"]) == 1
        assert loaded["projects"][0]["id"] == "gardenbot"

    def test_creates_parent_dirs(self, tmp_path, sample_data):
        out = str(tmp_path / "nested" / "dir" / "output.yml")
        export_to_yaml(sample_data, out)
        assert Path(out).exists()

    def test_structured_authors(self, tmp_path, sample_data):
        out = str(tmp_path / "output.yml")
        export_to_yaml(sample_data, out)
        with open(out, 'r') as f:
            loaded = yaml.safe_load(f)
        authors = loaded["works"][0]["authors"]
        assert authors[0]["name"] == "Alice Adams"
        assert authors[0]["person_id"] == "aadams"
        assert authors[1]["name"] == "Erin External"
        assert authors[1]["person_id"] is None
        assert authors[0]["equal_contribution"] is True
        assert authors[1]["equal_contribution"] is False

    def test_unicode_preserved(self, tmp_path):
        """Unicode characters should survive round-trip."""
        work = Work(
            bib_id="muller2024", title="Uber die Forschung",
            authors=[Author(name="Heidi Muller", position=1)],
            year=2024, category="Test", entry_type="article",
        )
        data = LabData(works=[work])
        out = str(tmp_path / "output.yml")
        export_to_yaml(data, out)
        with open(out, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)
        assert loaded["works"][0]["title"] == "Uber die Forschung"


class TestExportToJson:
    def test_creates_file(self, tmp_path, sample_data):
        out = str(tmp_path / "output.json")
        export_to_json(sample_data, out)
        assert Path(out).exists()

    def test_round_trip(self, tmp_path, sample_data):
        out = str(tmp_path / "output.json")
        export_to_json(sample_data, out)
        with open(out, 'r') as f:
            loaded = json.load(f)
        assert len(loaded["works"]) == 1
        assert loaded["works"][0]["bib_id"] == "adams2024robot"
        assert loaded["people"][0]["work_count"] == 1
        assert loaded["projects"][0]["people_ids"] == ["aadams"]
        authors = loaded["works"][0]["authors"]
        assert [a["equal_contribution"] for a in authors] == [True, False]

    def test_creates_parent_dirs(self, tmp_path, sample_data):
        out = str(tmp_path / "nested" / "dir" / "output.json")
        export_to_json(sample_data, out)
        assert Path(out).exists()

    def test_empty_data(self, tmp_path):
        import labdata

        data = LabData()
        out = str(tmp_path / "empty.json")
        export_to_json(data, out)
        with open(out, 'r') as f:
            loaded = json.load(f)
        assert loaded == {
            "schema_version": 4,
            "generator": {"name": "labdata", "version": labdata.__version__,
                          "schema_version": 4},
            "lab": {}, "works": [], "people": [], "projects": [],
            "collaborators": [],
        }


class TestARefusedDocumentLeavesTheOutputAlone:
    """A document labdata will not emit must not destroy the last one.

    The exporters build the whole document before opening the file. Opening
    first truncates it, so a run that then refuses to serialize -- a `Work`
    whose `source_file` is absolute is the case that exists today, and any
    later invariant would behave the same -- would leave the user with an
    empty file where a good document had been.
    """

    SENTINEL = "# the document from the last good run\n"

    @pytest.fixture
    def refused(self):
        work = Work(bib_id="a2024", title="A Title", authors=[], year=2024,
                    category="Journal Papers", entry_type="article",
                    source_file="/private/source.bib")
        return LabData(works=[work])

    @pytest.mark.parametrize("export, name",
                             [(export_to_json, "lab.json"),
                              (export_to_yaml, "lab.yml")],
                             ids=["json", "yaml"])
    def test_an_existing_file_is_not_truncated(self, tmp_path, refused, export,
                                               name):
        out = tmp_path / name
        out.write_text(self.SENTINEL, encoding="utf-8")
        with pytest.raises(ConfigurationError):
            export(refused, str(out))
        assert out.read_text(encoding="utf-8") == self.SENTINEL

    @pytest.mark.parametrize("export, name",
                             [(export_to_json, "lab.json"),
                              (export_to_yaml, "lab.yml")],
                             ids=["json", "yaml"])
    def test_no_file_is_created_where_there_was_none(self, tmp_path, refused,
                                                     export, name):
        out = tmp_path / "nested" / name
        with pytest.raises(ConfigurationError):
            export(refused, str(out))
        assert not out.exists()

    @pytest.mark.parametrize("export, name",
                             [(export_to_json, "lab.json"),
                              (export_to_yaml, "lab.yml")],
                             ids=["json", "yaml"])
    def test_a_document_it_will_emit_still_replaces_the_old_one(self, tmp_path,
                                                                sample_data,
                                                                export, name):
        """The guard above must not be a refusal to write at all."""
        out = tmp_path / name
        out.write_text(self.SENTINEL, encoding="utf-8")
        export(sample_data, str(out))
        assert out.read_text(encoding="utf-8") != self.SENTINEL
        assert "adams2024robot" in out.read_text(encoding="utf-8")
