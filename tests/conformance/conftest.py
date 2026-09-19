"""Fixtures for the conformance tests: the valid corpus, run once per session."""

import pytest

from .support import VALID, export, run_labdata


@pytest.fixture(scope="session")
def valid_export(tmp_path_factory):
    """(run, output) for the valid corpus exported as JSON."""
    run, data = export(VALID, tmp_path_factory.mktemp("valid"))
    assert run.crash is None, run.crash
    assert run.code == 0, run.output
    return run, data


@pytest.fixture(scope="session")
def valid_output(valid_export):
    """The valid corpus's exported output, parsed."""
    return valid_export[1]


@pytest.fixture(scope="session")
def valid_validate():
    """The result of ``labdata --validate`` on the valid corpus."""
    return run_labdata(["--config", "lab.yaml", "--validate"], VALID)


@pytest.fixture(scope="session")
def valid_unresolved():
    """The result of ``labdata --unresolved`` on the valid corpus."""
    return run_labdata(["--config", "lab.yaml", "--unresolved"], VALID)
