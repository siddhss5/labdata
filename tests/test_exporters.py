"""Tests for the exporters: YAML and JSON output."""

import json
import yaml
import pytest
from pathlib import Path

from sslabdata import (
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


class TestExportToJson:
    def test_creates_parent_dirs(self, tmp_path, sample_data):
        out = str(tmp_path / "nested" / "dir" / "output.json")
        export_to_json(sample_data, out)
        assert Path(out).exists()

    def test_empty_data(self, tmp_path):
        import sslabdata

        data = LabData()
        out = str(tmp_path / "empty.json")
        export_to_json(data, out)
        with open(out, 'r') as f:
            loaded = json.load(f)
        assert loaded == {
            "schema_version": 4,
            "generator": {"name": "sslabdata", "version": sslabdata.__version__,
                          "schema_version": 4},
            "lab": {}, "works": [], "people": [], "projects": [],
            "collaborators": [],
        }


class TestARefusedDocumentLeavesTheOutputAlone:
    """A document sslabdata will not emit must not destroy the last one.

    The exporters build the whole document before opening the file. Opening
    first truncates it, so a run that then refuses to serialize -- a `Work`
    whose `source_file` is absolute is the case that exists today, and any
    later invariant would behave the same -- would leave the user with an
    empty file where a good document had been.
    """

    # Not a comment, on purpose. A `#` line is valid YAML anywhere in a
    # file, so a sentinel written that way would survive an append and still
    # let the document parse; this one leaves a file that is neither valid
    # JSON nor valid YAML if anything is appended after it.
    SENTINEL = "the document from the last good run\n"

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

    @pytest.mark.parametrize("export, name, load",
                             [(export_to_json, "lab.json", json.load),
                              (export_to_yaml, "lab.yml", yaml.safe_load)],
                             ids=["json", "yaml"])
    def test_a_document_it_will_emit_replaces_the_old_file_whole(self, tmp_path,
                                                                 sample_data,
                                                                 export, name,
                                                                 load):
        """The guard above must not be a refusal to write -- nor a write that
        leaves any of the old file behind.

        Asked two ways, because neither is enough on its own. Opening in
        append mode changes the contents and puts the new document in the
        file, so a test that asked only whether the text changed would pass
        while the old document was still sitting at the top; and reading the
        file back would catch that for JSON but not for every sentinel a
        YAML parser tolerates. So the sentinel must be gone, and the file
        must parse **in full** to the document that was written.
        """
        out = tmp_path / name
        out.write_text(self.SENTINEL, encoding="utf-8")
        export(sample_data, str(out))

        assert self.SENTINEL not in out.read_text(encoding="utf-8")
        with open(out, encoding="utf-8") as f:
            assert load(f) == sample_data.to_dict()
