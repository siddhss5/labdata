"""Tests for the exporters: YAML and JSON output."""

import json
import yaml
import pytest
from pathlib import Path

from labdata.models import Author, Publication, Person, Project, LabData
from labdata.exporters import export_to_yaml, export_to_json


@pytest.fixture
def sample_data():
    """A small LabData instance for testing exports."""
    pub = Publication(
        bib_id="smith2024robot",
        title="Robot Gardening",
        authors=[
            Author(name="J. Smith", person_id="jsmith"),
            Author(name="E. External"),
        ],
        year=2024,
        venue="*HRI*, 2024",
        category="Conference Papers",
        entry_type="inproceedings",
        doi_url="https://doi.org/10.1234/test",
        project_ids=["gardenbot"],
    )
    person = Person(
        id="jsmith", name="John Smith", role="pi", status="current",
        publication_count=1, publication_ids=["smith2024robot"],
    )
    project = Project(
        id="gardenbot", title="Robot-Assisted Gardening", status="active",
        publication_ids=["smith2024robot"], people_ids=["jsmith"],
    )
    return LabData(publications=[pub], people=[person], projects=[project])


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
        assert len(loaded["publications"]) == 1
        assert loaded["publications"][0]["bib_id"] == "smith2024robot"
        assert len(loaded["people"]) == 1
        assert loaded["people"][0]["id"] == "jsmith"
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
        authors = loaded["publications"][0]["authors"]
        assert authors[0]["name"] == "J. Smith"
        assert authors[0]["person_id"] == "jsmith"
        assert authors[1]["name"] == "E. External"
        assert authors[1]["person_id"] is None

    def test_unicode_preserved(self, tmp_path):
        """Unicode characters should survive round-trip."""
        pub = Publication(
            bib_id="muller2024", title="Uber die Forschung",
            authors=[Author(name="H. Muller")],
            year=2024, venue="Test", category="Test", entry_type="article",
        )
        data = LabData(publications=[pub])
        out = str(tmp_path / "output.yml")
        export_to_yaml(data, out)
        with open(out, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)
        assert loaded["publications"][0]["title"] == "Uber die Forschung"


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
        assert len(loaded["publications"]) == 1
        assert loaded["publications"][0]["bib_id"] == "smith2024robot"
        assert loaded["people"][0]["publication_count"] == 1
        assert loaded["projects"][0]["people_ids"] == ["jsmith"]

    def test_creates_parent_dirs(self, tmp_path, sample_data):
        out = str(tmp_path / "nested" / "dir" / "output.json")
        export_to_json(sample_data, out)
        assert Path(out).exists()

    def test_empty_data(self, tmp_path):
        data = LabData()
        out = str(tmp_path / "empty.json")
        export_to_json(data, out)
        with open(out, 'r') as f:
            loaded = json.load(f)
        assert loaded == {"publications": [], "people": [], "projects": [], "collaborators": []}
