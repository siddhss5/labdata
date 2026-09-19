"""Tests for the CLI."""

import json
import shutil
import yaml
import pytest
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from labdata.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def run_cli(capsys):
    """Run the labdata CLI in-process; return its exit code and captured output."""
    def run(*args):
        try:
            main(list(args))
            returncode = 0
        except SystemExit as e:
            returncode = e.code if isinstance(e.code, int) else 1
        out, err = capsys.readouterr()
        return SimpleNamespace(returncode=returncode, stdout=out, stderr=err)
    return run


def test_installed_command_smoke():
    """The installed `labdata` console script runs end to end."""
    exe = shutil.which("labdata", path=str(Path(sys.executable).parent)) or shutil.which("labdata")
    assert exe, "labdata console script is not installed"
    result = subprocess.run(
        [exe, "--config", str(FIXTURES / "lab.yaml"), "--validate"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Validation passed" in result.stdout


class TestCLIOutput:
    def test_yaml_output(self, run_cli, tmp_path):
        out = str(tmp_path / "lab.yml")
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--output", out,
        )
        assert result.returncode == 0
        assert Path(out).exists()
        with open(out, 'r') as f:
            data = yaml.safe_load(f)
        assert len(data["publications"]) == 3
        assert "Wrote" in result.stdout

    def test_json_output(self, run_cli, tmp_path):
        out = str(tmp_path / "lab.json")
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--format", "json",
            "--output", out,
        )
        assert result.returncode == 0
        with open(out, 'r') as f:
            data = json.load(f)
        assert "publications" in data
        assert "people" in data
        assert "projects" in data

    def test_missing_config(self, run_cli):
        result = run_cli("--config", "/nonexistent/lab.yaml", "--output", "/tmp/out.yml")
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_no_output_arg(self, run_cli):
        result = run_cli("--config", str(FIXTURES / "lab.yaml"))
        assert result.returncode != 0


class TestCLIValidate:
    def test_validate_passes(self, run_cli):
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--validate",
        )
        assert result.returncode == 0
        assert "Publications: 3" in result.stdout
        assert "People: 3" in result.stdout
        assert "Projects: 2" in result.stdout
        assert "Validation passed" in result.stdout

    def test_validate_shows_unresolved(self, run_cli):
        """The fixture has an external author (E. E. Jones) who is unresolved."""
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--validate",
        )
        # E. E. Jones is in sample.bib but not in people.yaml
        assert "Unresolved authors" in result.stdout


class TestCLIUnresolved:
    def test_unresolved_list(self, run_cli):
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--unresolved",
        )
        assert result.returncode == 0
        assert "E. E. Jones" in result.stdout

    def test_unresolved_without_people(self, run_cli, tmp_path):
        """Without people_file, no authors can be resolved, but unresolved list is empty
        (no people to match against → nothing to report)."""
        config_data = {
            "bib_dir": str(FIXTURES),
            "bib_files": [{"name": "sample.bib", "category": "Test"}],
        }
        config_path = tmp_path / "minimal.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        result = run_cli("--config", str(config_path), "--unresolved")
        assert result.returncode == 0
        assert "All authors resolved" in result.stdout
