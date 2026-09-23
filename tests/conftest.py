"""Shared test fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_bib_path(fixtures_dir):
    """Path to sample BibTeX file."""
    return fixtures_dir / "sample.bib"
