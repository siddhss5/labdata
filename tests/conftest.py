"""Shared test fixtures.

``pytest_plugins`` enables pytest's own ``pytester`` fixture, which
``tests/conformance/test_coverage_table.py`` uses to run a throwaway suite in
an isolated subprocess. It ships with pytest; nothing new is installed.
"""

import pytest
from pathlib import Path

pytest_plugins = ["pytester"]


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_bib_path(fixtures_dir):
    """Path to sample BibTeX file."""
    return fixtures_dir / "sample.bib"
