"""Checks on the Jekyll templates in site/, rendered with the demo's own data.

The templates are Liquid and the site is built by Jekyll. These tests render
the author-list include and the projects page against the data
``labdata --output`` writes, so a template that stops showing something fails
here rather than on the deployed site. Rendering is done by python-liquid with
stand-ins for the two Jekyll filters the templates use; checks on the whole
built site are #18.
"""

import os
import re
from pathlib import Path

import liquid
import pytest

from labdata.assembler import assemble
from labdata.config import LabDataConfig


REPO_ROOT = Path(__file__).parent.parent
SITE = REPO_ROOT / "site"
DEMO_CONFIG = "examples/demo/lab.yaml"

# The demo entry whose BibTeX marks two of its three authors with $^{*}$.
MARKED_PUB = "brown2025tidy"
UNMARKED_PUB = "jones2023intent"
NOTE = "<sup>*</sup> equal contribution"

FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


@pytest.fixture(scope="module")
def environment():
    env = liquid.Environment()
    # Jekyll's own filters. The site is built by Jekyll, so these only have to
    # stand in for them closely enough to render the page here.
    env.add_filter("relative_url", lambda value: "/" + str(value).lstrip("/"))
    env.add_filter("markdownify", lambda value: f"<p>{value}</p>")
    return env


@pytest.fixture(scope="module")
def demo_data():
    """The demo assembled from the repo root, where its relative paths point."""
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        return assemble(LabDataConfig.from_yaml(DEMO_CONFIG)).to_dict()
    finally:
        os.chdir(cwd)


def render(environment, path, **variables):
    """One template rendered, with any Jekyll front matter taken off first."""
    source = FRONT_MATTER.sub("", Path(path).read_text(encoding="utf-8"))
    return environment.from_string(source).render(**variables)


def publication(data, bib_id):
    matches = [p for p in data["publications"] if p["bib_id"] == bib_id]
    assert len(matches) == 1, f"expected one publication {bib_id!r}"
    return matches[0]


def author_list(environment, authors):
    return render(environment, SITE / "_includes" / "author_list.html",
                  include={"authors": authors})


def test_demo_marks_equal_contributors(demo_data):
    """The demo data this file renders really does carry the markers."""
    pub = publication(demo_data, MARKED_PUB)
    assert [a["name"] for a in pub["authors"] if a["equal_contribution"]] \
        == ["B. Brown", "C. Côté"]
    assert [a["person_id"] for a in pub["authors"]] == ["bbrown", "ccote", "aadams"]


def test_author_list_stars_the_marked_authors(environment, demo_data):
    html = author_list(environment, publication(demo_data, MARKED_PUB)["authors"])
    assert ">B. Brown</a><sup>*</sup>" in html, html
    assert ">C. Côté</a><sup>*</sup>" in html, html
    assert ">A. Adams</a><sup>" not in html, html
    assert NOTE in html, html


def test_author_list_says_nothing_when_nobody_is_marked(environment, demo_data):
    html = author_list(environment, publication(demo_data, UNMARKED_PUB)["authors"])
    assert "<sup>" not in html, html
    assert "equal contribution" not in html, html


def test_projects_page_stars_the_marked_authors(environment, demo_data):
    html = render(environment, SITE / "_pages" / "projects.md",
                  site={"data": {"lab": demo_data}})
    assert "B. Brown<sup>*</sup>, C. Côté<sup>*</sup>, A. Adams" in html, html
    # The note appears on the one publication that has marked authors, and
    # only there: the demo lists six other papers on the same page.
    assert html.count(NOTE) == 1, html
