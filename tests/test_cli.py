"""Tests for the CLI."""

import json
import shutil
import yaml
import pytest
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from sslabdata.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def run_cli(capsys):
    """Run the sslabdata CLI in-process; return its exit code and captured output."""
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
    """The installed `sslabdata` console script runs end to end."""
    exe = shutil.which("sslabdata", path=str(Path(sys.executable).parent)) or shutil.which("sslabdata")
    assert exe, "sslabdata console script is not installed"
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
        assert len(data["works"]) == 3
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
        assert "works" in data
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
        assert "Works: 3" in result.stdout
        assert "People: 3" in result.stdout
        assert "Projects: 2" in result.stdout
        assert "Validation passed" in result.stdout

    def test_validate_shows_unresolved(self, run_cli):
        """The fixture has an external author (External E. Jones) who is unresolved."""
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--validate",
        )
        # External E. Jones is in sample.bib but not in people.yaml
        assert "Unresolved authors" in result.stdout


class TestCLIUnresolved:
    def test_unresolved_list(self, run_cli):
        result = run_cli(
            "--config", str(FIXTURES / "lab.yaml"),
            "--unresolved",
        )
        assert result.returncode == 0
        assert "External E. Jones" in result.stdout

    def test_unresolved_without_people(self, run_cli, tmp_path):
        """Without people_file, resolution never ran, so --unresolved must say so
        (naming people_file) instead of reporting every author as resolved."""
        config_data = {
            "bib_dir": str(FIXTURES),
            "bib_files": [{"name": "sample.bib", "category": "Test"}],
        }
        config_path = tmp_path / "minimal.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        result = run_cli("--config", str(config_path), "--unresolved")
        assert "All authors resolved" not in result.stdout
        assert "people_file" in result.stdout + result.stderr


INVALID = Path(__file__).parent / "corpus" / "invalid"


class TestDiagnosticClassesByMode:
    """Each new code behaves as its class in SPEC.md says, in every mode."""

    @pytest.mark.parametrize("folder, code", [
        ("undefined_project", "RESOLVE-PROJECT-UNKNOWN"),
        ("duplicate_person_id", "PEOPLE-ID-DUPLICATE"),
        ("duplicate_project_id", "PROJECTS-ID-DUPLICATE"),
    ])
    def test_a_validation_error_fails_only_validate(self, run_cli, monkeypatch,
                                                    tmp_path, folder, code):
        monkeypatch.chdir(INVALID / folder)
        validate = run_cli("--config", "lab.yaml", "--validate")
        assert validate.returncode == 1 and f"  - {code} " in validate.stdout

        out = tmp_path / "lab.json"
        export = run_cli("--config", "lab.yaml", "--format", "json", "--output", str(out))
        assert export.returncode == 0, export.stderr
        assert f"Warning: {code} " in export.stderr
        assert out.exists()

        unresolved = run_cli("--config", "lab.yaml", "--unresolved")
        assert unresolved.returncode == 0
        assert f"Warning: {code} " in unresolved.stderr

    @pytest.mark.parametrize("folder, code", [
        ("people_file_not_found", "CONFIG-FILE-NOT-FOUND"),
        ("projects_file_not_found", "CONFIG-FILE-NOT-FOUND"),
        ("bib_file_not_found", "CONFIG-FILE-NOT-FOUND"),
        ("people_missing_name", "PEOPLE-FIELD-MISSING"),
        ("people_not_a_list", "PEOPLE-NOT-A-LIST"),
    ])
    def test_a_fatal_error_fails_every_mode_and_writes_nothing(
            self, run_cli, monkeypatch, tmp_path, folder, code):
        monkeypatch.chdir(INVALID / folder)
        validate = run_cli("--config", "lab.yaml", "--validate")
        assert validate.returncode == 1 and f"  - {code} " in validate.stdout

        out = tmp_path / "lab.json"
        export = run_cli("--config", "lab.yaml", "--format", "json", "--output", str(out))
        assert export.returncode == 1
        assert any(line.startswith(f"{code} ") for line in export.stderr.splitlines())
        assert not out.exists()

        unresolved = run_cli("--config", "lab.yaml", "--unresolved")
        assert unresolved.returncode == 1

    @pytest.mark.parametrize("folder, code", [
        ("invalid_person_role", "PEOPLE-ROLE-INVALID"),
        ("invalid_person_status", "PEOPLE-STATUS-INVALID"),
        ("invalid_project_status", "PROJECTS-STATUS-INVALID"),
        ("ambiguous_alias", "PEOPLE-ALIAS-AMBIGUOUS"),
        ("config_unknown_key", "CONFIG-KEY-UNKNOWN"),
        ("config_bib_files_missing", "CONFIG-BIB-FILES-MISSING"),
        ("undefined_string", "BIB-STRING-UNDEFINED"),
        ("unclosed_brace", "BIB-SYNTAX-ERROR"),
        ("year_not_number", "BIB-YEAR-INVALID"),
        ("missing_journal", "BIB-VENUE-MISSING"),
        ("unsupported_entry_type", "BIB-ENTRY-TYPE-UNSUPPORTED"),
        ("unknown_macro", "LATEX-COMMAND-UNKNOWN"),
    ])
    def test_a_warning_fails_nothing(self, run_cli, monkeypatch, tmp_path,
                                     folder, code):
        monkeypatch.chdir(INVALID / folder)
        validate = run_cli("--config", "lab.yaml", "--validate")
        assert validate.returncode == 0, validate.stdout
        warnings = validate.stdout.split("\nWarnings (", 1)[1]
        assert f"  - {code} " in warnings

        out = tmp_path / "lab.json"
        export = run_cli("--config", "lab.yaml", "--format", "json", "--output", str(out))
        assert export.returncode == 0 and out.exists()
        assert f"Warning: {code} " in export.stderr
