"""Shared test fixtures, and one guard on the suite itself."""

import pytest
from pathlib import Path


# A strict xfail that fails for the wrong reason is worse than no marker at
# all: it reads as a finding about labdata and is really a broken test, and
# it keeps reading that way until somebody runs the suite with --runxfail and
# looks. A NameError, an AttributeError or a missing key means the test never
# reached its own assertion, so the marker is reporting nothing. Those are
# turned back into failures rather than counted as expected.
#
# A raised TypeError is here for the same reason: a test whose real finding
# is "this raises TypeError" writes `pytest.raises(TypeError)`, which passes,
# so one reaching the report is always a test that broke on the way.
SETUP_FAILURES = (NameError, AttributeError, KeyError, TypeError, ImportError,
                  IndexError)


def is_setup_failure(exception):
    """True when an exception means the test never reached its own assertion."""
    return isinstance(exception, SETUP_FAILURES)


def _strictly_xfailed(item):
    return any(mark.kwargs.get("strict")
               for mark in item.iter_markers(name="xfail"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or call.excinfo is None:
        return
    if not _strictly_xfailed(item) or not is_setup_failure(call.excinfo.value):
        return
    report.outcome = "failed"
    report.longrepr = (
        "strict xfail broke on %s before reaching its own assertion, so the "
        "marker establishes nothing: %s" % (call.excinfo.typename, call.excinfo.value))
    if hasattr(report, "wasxfail"):
        del report.wasxfail


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_bib_path(fixtures_dir):
    """Path to sample BibTeX file."""
    return fixtures_dir / "sample.bib"
