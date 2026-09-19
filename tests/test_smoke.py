"""Smoke tests to verify the package loads and basic functionality works."""

import labdata


def test_package_imports():
    """Verify the package can be imported and has expected attributes."""
    assert hasattr(labdata, '__version__')
    assert labdata.__version__ == "2.0.0"


def test_core_classes_importable():
    """Verify core classes are importable from the package."""
    from labdata import (
        LabDataConfig,
        BibFile,
        LabData,
        Publication,
        Author,
        Person,
        Project,
        assemble,
        export_to_yaml,
        export_to_json,
    )


def test_publication_dataclass():
    """Verify Publication dataclass works."""
    from labdata import Publication, Author

    pub = Publication(
        bib_id="test2024",
        entry_type="article",
        year=2024,
        title="Test Paper",
        authors=[Author(name="B. Brown"), Author(name="A. Adams")],
        venue="Test Journal, 2024",
        category="Journal Papers",
        project_ids=["test_project"],
    )
    assert pub.year == 2024
    assert pub.title == "Test Paper"
    assert pub.project_ids == ["test_project"]

    d = pub.to_dict()
    assert d["title"] == "Test Paper"
    assert d["year"] == 2024
    assert d["authors"][0]["name"] == "B. Brown"
