"""Smoke test: the package's public names import."""


def test_core_classes_importable():
    """Verify core classes are importable from the package."""
    from sslabdata import (
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

