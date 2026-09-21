"""
Configuration for labdata.

Single-layer configuration loaded from a YAML file (lab.yaml).
Replaces the old two-layer LibraryConfig → PublicationsConfig system.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class BibFile:
    """A single BibTeX file and its category label."""
    name: str
    category: str


@dataclass
class LabDataConfig:
    """Configuration for labdata, loadable from YAML.

    Example lab.yaml:
        lab:
          name: "My Lab"
          description: "What our lab does"
          website: "https://mylab.edu"

        bib_dir: "data/bib"
        bib_files:
          - name: "journal.bib"
            category: "Journal Papers"
          - name: "conference.bib"
            category: "Conference Papers"

        pdf_base_url: "https://lab.edu/pdfs"
        people_file: "data/people.yaml"
        projects_file: "data/projects.yaml"
    """
    bib_dir: str
    bib_files: List[BibFile]
    pdf_base_url: Optional[str] = None
    people_file: Optional[str] = None
    projects_file: Optional[str] = None
    lab: Optional[Dict[str, str]] = None

    # Where this configuration was read from, so a diagnostic about it can
    # name the file the user would edit. Never emitted.
    path: Optional[str] = None

    @classmethod
    def from_yaml(cls, path: str) -> 'LabDataConfig':
        """Load configuration from a YAML file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        bib_files = [
            BibFile(**bf) for bf in data.get('bib_files', [])
        ]

        return cls(
            bib_dir=data['bib_dir'],
            bib_files=bib_files,
            pdf_base_url=data.get('pdf_base_url'),
            people_file=data.get('people_file'),
            projects_file=data.get('projects_file'),
            lab=data.get('lab'),
            path=str(path),
        )
