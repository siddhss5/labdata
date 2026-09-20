"""
Main pipeline orchestrator.

Assembles the complete LabData output from configuration:
config → parse BibTeX → load people/projects → resolve links → back-link.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .config import LabDataConfig
from .models import LabData, Collaborator, Publication
from .parsers.bibtex import parse_all_publications
from .loaders import load_people, load_projects
from .resolver import resolve_authors, resolve_projects, compute_backlinks


@dataclass
class AssemblyResult:
    """Result of assembling lab data, including diagnostics."""
    data: LabData
    unresolved_authors: List[str] = field(default_factory=list)
    unknown_projects: List[str] = field(default_factory=list)
    bibliography_errors: List[str] = field(default_factory=list)


def assemble(config: LabDataConfig, diagnostics: bool = False):
    """Main entry point: config → fully resolved LabData.

    1. Parse all BibTeX files into Publications
    2. Load people and projects from YAML
    3. Resolve author names → person IDs
    4. Validate project IDs
    5. Compute back-links (people→pubs, projects→pubs, projects→people)

    Args:
        config: Lab data configuration
        diagnostics: If True, return AssemblyResult with diagnostics.
                     If False (default), return LabData directly.
    """
    # Parse publications
    bib_files = [{'name': bf.name, 'category': bf.category} for bf in config.bib_files]
    bibliography_errors: List[str] = []
    publications = parse_all_publications(
        bib_dir=config.bib_dir,
        bib_files=bib_files,
        pdf_base_url=config.pdf_base_url,
        duplicate_errors=bibliography_errors if diagnostics else None,
    )

    # Load people and projects
    people = load_people(config.people_file) if config.people_file else []
    projects = load_projects(config.projects_file) if config.projects_file else []

    # Resolve
    unresolved_authors = resolve_authors(publications, people)
    unknown_projects = resolve_projects(publications, projects)

    # Compute collaborators (external co-authors not in people.yaml)
    collab_counts: dict = {}
    collab_years: dict = {}
    for pub in publications:
        for author in pub.authors:
            if author.person_id is None:
                collab_counts[author.name] = collab_counts.get(author.name, 0) + 1
                collab_years[author.name] = max(collab_years.get(author.name, 0), pub.year)
    collaborators = sorted(
        [Collaborator(name=name, publication_count=collab_counts[name],
                      last_year=collab_years[name])
         for name in collab_counts],
        key=lambda c: (-c.last_year, -c.publication_count, c.name),
    )

    # Assemble
    data = LabData(
        publications=publications,
        people=people,
        projects=projects,
        collaborators=collaborators,
        lab=config.lab,
    )

    # Back-link
    compute_backlinks(data)

    if diagnostics:
        return AssemblyResult(
            data=data,
            unresolved_authors=unresolved_authors,
            unknown_projects=unknown_projects,
            bibliography_errors=bibliography_errors,
        )
    return data
