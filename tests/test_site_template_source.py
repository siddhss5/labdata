"""Source-level checks on the bundled Jekyll templates in site/.

These read the template text. They do not render Liquid and do not build the
site, so what they establish is that the templates ask for the star and for the
note, and that both are driven by the `equal_contribution` field rather than
being hard-coded — not that a built page shows them. Verifying rendered output
(HTML snapshots, internal links, accessibility) is #36.

labdata's product is the data file; site/ is an example renderer that consumes
it, which is why these checks stay at the source level and pull in nothing to
render with.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
AUTHOR_LIST = REPO_ROOT / "site" / "_includes" / "author_list.html"
PROJECTS = REPO_ROOT / "site" / "_pages" / "projects.md"

STAR = "{% if author.equal_contribution %}<sup>*</sup>{% endif %}"
MARKED = '| where: "equal_contribution", true'
NOTE = "equal contribution"


def test_author_list_source_stars_marked_authors():
    """The include stars an author whose `equal_contribution` is true."""
    source = AUTHOR_LIST.read_text(encoding="utf-8")
    assert STAR in source, source
    assert source.index("{{ author.name }}") < source.index(STAR), source


def test_author_list_source_notes_equal_contribution():
    """The note is written once per list, and only when somebody is marked."""
    source = AUTHOR_LIST.read_text(encoding="utf-8")
    assert MARKED in source, source
    assert "{% if equal_authors.size > 0 %}" in source, source
    assert source.count(NOTE) == 1, source


def test_projects_page_source_stars_and_notes_marked_authors():
    """The projects page repeats both in its own author loop."""
    source = PROJECTS.read_text(encoding="utf-8")
    assert STAR in source, source
    assert MARKED in source, source
    assert "{% if equal_authors.size > 0 %}" in source, source
    assert source.count(NOTE) == 1, source
