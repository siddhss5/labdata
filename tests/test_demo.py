"""Tests for the Example Lab demo in examples/demo/ and the site config it feeds."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from labdata.assembler import assemble
from labdata.cli import main
from labdata.config import LabDataConfig


REPO_ROOT = Path(__file__).parent.parent
DEMO_CONFIG = "examples/demo/lab.yaml"


@pytest.fixture
def demo_result(monkeypatch):
    """Assemble the demo from the repo root, where its relative paths point."""
    monkeypatch.chdir(REPO_ROOT)
    config = LabDataConfig.from_yaml(DEMO_CONFIG)
    return assemble(config, diagnostics=True)


class TestDemoLab:
    def test_validate_cli(self, monkeypatch, capsys):
        monkeypatch.chdir(REPO_ROOT)
        main(["--config", DEMO_CONFIG, "--validate"])
        out = capsys.readouterr().out
        assert "Validation passed" in out
        # External collaborators stay unresolved; that must not fail validation.
        assert "Unresolved authors" in out

    def test_assembles(self, demo_result):
        data = demo_result.data
        assert data.lab["name"] == "Example Lab"
        assert 17 <= len(data.publications) <= 21
        assert 2 <= len(data.projects) <= 3
        assert demo_result.unknown_projects == []

    def test_every_person_is_linked_to_a_publication(self, demo_result):
        for person in demo_result.data.people:
            assert person.publication_count > 0, person.id

    def test_every_project_has_publications(self, demo_result):
        for project in demo_result.data.projects:
            assert project.publication_ids, project.id

    def test_covers_template_roles(self, demo_result):
        roles = {(p.role, p.status) for p in demo_result.data.people}
        assert ("professor", "current") in roles
        assert ("phd_student", "current") in roles
        assert ("ms_student", "current") in roles
        assert ("postdoc", "alumni") in roles
        assert ("phd_student", "alumni") in roles
        assert ("ms_student", "alumni") in roles

    def test_has_external_collaborators(self, demo_result):
        assert demo_result.data.collaborators

    def test_shows_each_publication_feature(self, demo_result):
        pubs = demo_result.data.publications
        assert any(p.abstract for p in pubs)
        assert any(p.doi_url for p in pubs)
        assert any(p.arxiv_url for p in pubs)
        assert any(p.video_url for p in pubs)
        assert any(p.note and "Award" in p.note for p in pubs)
        assert any(len(p.project_ids) > 1 for p in pubs)
        assert len({p.entry_type for p in pubs}) >= 5
        assert len({p.year for p in pubs}) >= 5

    def test_bib_input_has_equal_contribution_markers(self):
        """The demo .bib input marks equal contribution with $^{*}$."""
        bib_text = "".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "examples/demo/bib").glob("*.bib")
        )
        assert "$^{*}$" in bib_text

    def test_equal_contribution_markers_are_read_not_left_on_the_name(self, demo_result):
        """The marked authors are recorded as such, and still resolve (#46).

        The demo writes the marker on the surname, which is what stopped Bob
        Brown and Carol Côté resolving until #46.
        """
        pub = next(p for p in demo_result.data.publications
                   if p.bib_id == "brown2025tidy")
        marked = [a for a in pub.authors if a.equal_contribution]
        assert [a.name for a in marked] == ["B. Brown", "C. Côté"]
        assert [a.person_id for a in marked] == ["bbrown", "ccote"]
        assert [a.family for a in marked] == ["Brown", "Côté"]
        assert pub.authors[-1].equal_contribution is False

    def test_only_outside_collaborators_are_unresolved(self, demo_result):
        """Every unresolved name is an outside co-author, not a marked member.

        Two of these names are each shared by more than one person, which is
        the identity fixture #69 added: `P. Patel` is Priya Patel on three
        works and Pradeep Patel on a fourth, and `L. Lee` is the two
        different people `nolan2020stairs` lists under one written name.
        """
        assert demo_result.unresolved_authors == [
            "L. Lee", "O. Ortiz", "P. Park", "P. Patel", "R. Reed",
            "S. Stone", "T. Turner"]


class TestGenerateSiteConfig:
    def _run(self, lab_yaml, tmp_path):
        out = tmp_path / "_config.generated.yml"
        result = subprocess.run(
            [sys.executable, "scripts/generate_site_config.py", str(lab_yaml), str(out)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        with open(out, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_demo(self, tmp_path):
        with open(REPO_ROOT / DEMO_CONFIG, 'r', encoding='utf-8') as f:
            lab_config = yaml.safe_load(f)
        config = self._run(DEMO_CONFIG, tmp_path)
        assert config["title"] == "Example Lab"
        assert config["description"] == lab_config["lab"]["description"]
        assert config["url"] == lab_config["site"]["url"]
        assert config["baseurl"] == lab_config["site"]["baseurl"]

    def test_values_follow_lab_yaml(self, tmp_path):
        lab_yaml = tmp_path / "lab.yaml"
        lab_yaml.write_text(yaml.safe_dump({
            "lab": {"name": "Other Lab", "description": "Something else"},
            "site": {"url": "https://other.example.org", "baseurl": "/other"},
            "bib_dir": "bib",
            "bib_files": [],
        }))
        config = self._run(lab_yaml, tmp_path)
        assert config == {
            "title": "Other Lab",
            "description": "Something else",
            "url": "https://other.example.org",
            "baseurl": "/other",
        }

    def test_without_site_section(self, tmp_path):
        lab_yaml = tmp_path / "lab.yaml"
        lab_yaml.write_text(yaml.safe_dump({
            "lab": {"name": "Root Lab"},
            "bib_dir": "bib",
            "bib_files": [],
        }))
        config = self._run(lab_yaml, tmp_path)
        assert config == {"title": "Root Lab", "baseurl": ""}
