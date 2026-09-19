"""Tests for the Example Lab demo in examples/demo/ and the site config it feeds."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from labdata.assembler import assemble
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
    def test_validate_cli(self):
        result = subprocess.run(
            [sys.executable, "-m", "labdata.cli", "--config", DEMO_CONFIG, "--validate"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Validation passed" in result.stdout

    def test_assembles(self, demo_result):
        data = demo_result.data
        assert data.lab["name"] == "Example Lab"
        assert 13 <= len(data.publications) <= 17
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
        """The demo .bib input marks equal contribution with $^{*}$.

        This only checks the input: labdata currently deletes the markers,
        and keeping and rendering them is #46.
        """
        bib_text = "".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "examples/demo/bib").glob("*.bib")
        )
        assert "$^{*}$" in bib_text


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
