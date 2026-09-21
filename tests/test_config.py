"""Tests for the new LabDataConfig."""

import pytest
import yaml
import tempfile
from pathlib import Path, PureWindowsPath

from labdata import BibFile, LabDataConfig, assemble


class TestLabDataConfig:
    def test_from_yaml(self, tmp_path):
        config_data = {
            "bib_dir": "data/bib",
            "bib_files": [
                {"name": "journal.bib", "category": "Journal Papers"},
                {"name": "conf.bib", "category": "Conference Papers"},
            ],
            "pdf_base_url": "https://example.com/pdfs",
            "people_file": "data/people.yaml",
            "projects_file": "data/projects.yaml",
        }
        config_path = tmp_path / "lab.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        config = LabDataConfig.from_yaml(str(config_path))
        assert config.bib_dir == "data/bib"
        assert len(config.bib_files) == 2
        assert config.bib_files[0].name == "journal.bib"
        assert config.bib_files[0].category == "Journal Papers"
        assert config.pdf_base_url == "https://example.com/pdfs"
        assert config.people_file == "data/people.yaml"
        assert config.projects_file == "data/projects.yaml"

    def test_minimal_config(self, tmp_path):
        config_data = {
            "bib_dir": "bib",
            "bib_files": [
                {"name": "pubs.bib", "category": "Publications"},
            ],
        }
        config_path = tmp_path / "lab.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        config = LabDataConfig.from_yaml(str(config_path))
        assert config.bib_dir == "bib"
        assert config.pdf_base_url is None
        assert config.people_file is None
        assert config.projects_file is None

    def test_lab_metadata(self, tmp_path):
        config_data = {
            "bib_dir": "bib",
            "bib_files": [
                {"name": "pubs.bib", "category": "Publications"},
            ],
            "lab": {
                "name": "Test Lab",
                "description": "A test lab",
                "website": "https://testlab.edu",
            },
        }
        config_path = tmp_path / "lab.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        config = LabDataConfig.from_yaml(str(config_path))
        assert config.lab is not None
        assert config.lab["name"] == "Test Lab"
        assert config.lab["website"] == "https://testlab.edu"

    def test_lab_metadata_optional(self, tmp_path):
        config_data = {
            "bib_dir": "bib",
            "bib_files": [
                {"name": "pubs.bib", "category": "Publications"},
            ],
        }
        config_path = tmp_path / "lab.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        config = LabDataConfig.from_yaml(str(config_path))
        assert config.lab is None

    def test_bib_file_dataclass(self):
        bf = BibFile(name="test.bib", category="Test")
        assert bf.name == "test.bib"
        assert bf.category == "Test"


def is_absolute(name):
    """Rooted under either flavour. Restated rather than imported: outside
    tests/unit/ the suite uses only labdata's public names."""
    return name.startswith(("/", "\\")) or PureWindowsPath(name).is_absolute()


class TestBibFileNameIsNeverAbsolute:
    """`bib_files[].name` is emitted as `work.source.file`, which SPEC.md
    section 5 promises is never an absolute path.

    The guarantee is kept by rejecting the input rather than by rewriting it:
    rewriting would quietly drop a relative directory the user meant. Checked
    through `from_yaml()` rather than against the predicate behind it, because
    outside `tests/unit/` the suite uses only labdata's public names.
    """

    # Both path flavours, so the same configuration is accepted or rejected
    # wherever it is compiled -- a document is shared, and one carrying a
    # compiling machine's directory layout leaks it to every consumer.
    ABSOLUTE = ["/data/journal.bib", "//srv/journal.bib",
                "C:\\data\\journal.bib", "C:/data/journal.bib",
                "\\\\server\\share\\journal.bib", "\\journal.bib"]
    RELATIVE = ["journal.bib", "sub/journal.bib", "sub\\journal.bib",
                "../shared/journal.bib", "./journal.bib"]

    # The code, restated here rather than imported: it is a published,
    # permanent interface (SPEC.md, "Diagnostic codes"), so a test may depend
    # on it without depending on the wording around it.
    CODE = "CONFIG-BIB-FILE-ABSOLUTE"

    def write(self, tmp_path, name):
        config_path = tmp_path / "lab.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"bib_dir": ".",
                            "bib_files": [{"name": name,
                                           "category": "Journal Papers"}]}, f)
        return config_path

    @pytest.mark.parametrize("name", ABSOLUTE)
    def test_an_absolute_name_is_rejected_at_load(self, tmp_path, name):
        config_path = self.write(tmp_path, name)
        with pytest.raises(ValueError) as raised:
            LabDataConfig.from_yaml(str(config_path))
        message = str(raised.value)
        assert message.startswith(self.CODE), message
        # It locates itself the way every coded diagnostic does, and names
        # the value it objected to.
        assert f"{config_path}:bib_files:name" in message
        assert name in message

    @pytest.mark.parametrize("name", RELATIVE)
    def test_a_relative_name_still_loads(self, tmp_path, name):
        config = LabDataConfig.from_yaml(str(self.write(tmp_path, name)))
        # Passed through as written: the relative directory is the user's.
        assert config.bib_files[0].name == name

    @pytest.mark.parametrize("name", ABSOLUTE)
    def test_an_absolute_name_is_rejected_when_built_by_hand(self, name):
        """`BibFile` and `LabDataConfig` are public, so a caller can assemble
        a configuration without going near YAML.

        A guarantee about the emitted document has to hold however the
        configuration was built, so the check is in the constructor and not
        only in `from_yaml()`. Without it, `assemble()` emits an absolute
        `work.source.file` and no diagnostic at all.
        """
        with pytest.raises(ValueError) as raised:
            BibFile(name=name, category="Journal Papers")
        message = str(raised.value)
        assert message.startswith(self.CODE), message
        assert "bib_files:name" in message
        assert name in message

    @pytest.mark.parametrize("name", RELATIVE)
    def test_a_relative_name_is_built_by_hand_unchanged(self, name):
        assert BibFile(name=name, category="Journal Papers").name == name

    @pytest.mark.parametrize("name", ABSOLUTE)
    def test_an_absolute_name_set_after_construction_is_rejected(self, tmp_path, name):
        """`BibFile` is a plain, mutable dataclass, which is public API.

        Checking only in the constructor leaves the guarantee one assignment
        away from being false, and `assemble()` would emit the absolute path
        with no diagnostic at all. The check that holds is the one made on
        every name about to be compiled.
        """
        bib_file = BibFile(name="journal.bib", category="Journal Papers")
        bib_file.name = name
        with pytest.raises(ValueError) as raised:
            assemble(LabDataConfig(bib_dir=str(tmp_path), bib_files=[bib_file]))
        message = str(raised.value)
        assert message.startswith(self.CODE), message
        assert name in message

    def test_a_document_built_by_hand_never_carries_an_absolute_source(self, tmp_path):
        """End to end through the public API, with no YAML anywhere."""
        (tmp_path / "journal.bib").write_text(
            "@article{a2024,\n  title   = {A Title},\n"
            "  author  = {Adams, Alice},\n  journal = {J},\n  year    = {2024}\n}\n",
            encoding="utf-8")
        config = LabDataConfig(
            bib_dir=str(tmp_path),
            bib_files=[BibFile(name="journal.bib", category="Journal Papers")])
        document = assemble(config).to_dict()
        assert document["works"][0]["source"]["file"] == "journal.bib"
        assert not is_absolute(document["works"][0]["source"]["file"])
