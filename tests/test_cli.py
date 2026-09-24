"""Tests for the CLI."""

import shutil
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
        ("record_unknown_key", "RECORD-KEY-UNKNOWN"),
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
