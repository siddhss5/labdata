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
from pathlib import Path, PureWindowsPath


# A configured `.bib` name reaches the document as `work.source.file`, where
# it is promised never to be an absolute path (SPEC.md section 5): a document
# is shared, and one carrying a compiling machine's directory layout leaks it
# to every consumer. Rejecting the input is what makes the promise true;
# rewriting the name would quietly discard a relative directory the user
# meant. Both path flavours are checked, so the same configuration is
# accepted or rejected wherever it is compiled.
BIB_FILE_ABSOLUTE = "CONFIG-BIB-FILE-ABSOLUTE"


def is_absolute_path(name: str) -> bool:
    """True when ``name`` is rooted rather than relative to ``bib_dir``.

    Both path flavours, and a leading separator on its own: ``/x.bib`` is
    absolute on POSIX, ``C:\\x.bib`` and ``\\\\server\\share\\x.bib`` are absolute
    on Windows, and ``\\x.bib`` is rooted on Windows even though Python does
    not call it absolute without a drive. All four escape ``bib_dir``, which
    is the thing being ruled out.
    """
    return name.startswith(("/", "\\")) or PureWindowsPath(name).is_absolute()


@dataclass
class BibFile:
    """A single BibTeX file and its category label.

    ``name`` is a name under ``bib_dir``, not a path of its own: it is
    emitted as ``work.source.file`` and must never be absolute.
    """
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

        for bf in data.get('bib_files', []):
            name = bf.get('name') if isinstance(bf, dict) else None
            if isinstance(name, str) and is_absolute_path(name):
                raise ValueError(
                    f"{BIB_FILE_ABSOLUTE} {path}:bib_files:name: '{name}' is an "
                    "absolute path; a bib_files name is a name under bib_dir, "
                    "and it is emitted as the work's source.file, which is "
                    "never absolute")

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
