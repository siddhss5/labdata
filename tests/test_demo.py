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
        assert 17 <= len(data.works) <= 21
        assert 2 <= len(data.projects) <= 3
        assert demo_result.unknown_projects == []
        # crossref is rejected, and the demo uses none, so nothing is fatal.
        assert demo_result.fatal_errors == []

    def test_every_person_is_linked_to_a_work(self, demo_result):
        for person in demo_result.data.people:
            assert person.work_count > 0, person.id

    def test_every_project_has_works(self, demo_result):
        for project in demo_result.data.projects:
            assert project.work_ids, project.id

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

    def test_shows_each_work_feature(self, demo_result):
        works = demo_result.data.works
        assert any(w.abstract for w in works)
        assert any("doi" in w.identifiers for w in works)
        assert any("arxiv" in w.identifiers for w in works)
        assert any("video" in w.links for w in works)
        assert any(w.note and "Award" in w.note for w in works)
        assert any(len(w.project_ids) > 1 for w in works)
        assert len({w.entry_type for w in works}) >= 5
        assert len({w.year for w in works}) >= 5
        # The structured bibliography, which is what v4 added.
        assert any(w.venue and w.venue.kind == "journal" for w in works)
        assert any(w.pages and w.volume and w.number for w in works)
        assert any(w.editors for w in works)

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
        work = next(w for w in demo_result.data.works
                    if w.bib_id == "brown2025tidy")
        marked = [a for a in work.authors if a.equal_contribution]
        assert [a.name for a in marked] == ["Bob Brown", "Carol Côté"]
        assert [a.person_id for a in marked] == ["bbrown", "ccote"]
        assert [a.family for a in marked] == ["Brown", "Côté"]
        assert work.authors[-1].equal_contribution is False

    def test_only_outside_collaborators_are_unresolved(self, demo_result):
        """Every unresolved name is an outside co-author, not a marked member.

        The names are the readable form of what each entry wrote, so the
        identity fixture #69 added shows up as three Patels rather than one:
        `Priya Patel` on two works, `P. Patel` on a third and `Pradeep Patel`
        on a fourth. Two of those three are the same person, which no key
        built from a name can tell, and joining them is #24's. `Lin Lee` is
        one name written twice on `nolan2020stairs` by two different people,
        which is why the authorship rather than the grouping is the record a
        consumer falls back to.
        """
        assert demo_result.unresolved_authors == [
            "Lin Lee", "Olivia Ortiz", "P. Park", "P. Patel", "Pradeep Patel",
            "Priya Patel", "R. Reed", "Sybil Stone", "Trent Turner"]


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
