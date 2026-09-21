"""Smoke tests to verify the package loads and basic functionality works."""

import labdata


def test_package_imports():
    """Verify the package can be imported and has expected attributes."""
    assert hasattr(labdata, '__version__')
    assert labdata.__version__ == "3.0.0"


def test_core_classes_importable():
    """Verify core classes are importable from the package."""
    from labdata import (
        LabDataConfig,
        BibFile,
        LabData,
        Work,
        Author,
        Contributor,
        Venue,
        Link,
        Person,
        Project,
        Collaborator,
        assemble,
        export_to_yaml,
        export_to_json,
    )


def test_work_dataclass():
    """Verify Work dataclass works."""
    from labdata import Author, Venue, Work

    work = Work(
        bib_id="test2024",
        entry_type="article",
        year=2024,
        title="Test Paper",
        authors=[Author(name="Bob Brown", position=1),
                 Author(name="Alice Adams", position=2)],
        venue=Venue(kind="journal", name="Test Journal"),
        category="Journal Papers",
        project_ids=["test_project"],
    )
    assert work.year == 2024
    assert work.title == "Test Paper"
    assert work.project_ids == ["test_project"]

    d = work.to_dict()
    assert d["title"] == "Test Paper"
    assert d["year"] == 2024
    assert d["authors"][0]["name"] == "Bob Brown"
    assert d["venue"] == {"kind": "journal", "name": "Test Journal"}
