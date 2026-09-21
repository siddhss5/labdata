"""
labdata - Renderer-agnostic academic lab data assembler.

Transforms BibTeX files and YAML configuration into structured data
(YAML/JSON) for academic lab websites. Framework-agnostic: works with
Jekyll, Hugo, Flask, or any other consumer.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

from .config import ConfigurationError, LabDataConfig, BibFile
from .models import (
    LabData, Work, Author, Contributor, Venue, Link, Person, Project,
    Collaborator,
)
from .assembler import assemble, AssemblyResult
from .exporters import export_to_yaml, export_to_json

__all__ = [
    # Config
    "LabDataConfig",
    "BibFile",
    "ConfigurationError",
    # Data model
    "LabData",
    "Work",
    "Author",
    "Contributor",
    "Venue",
    "Link",
    "Person",
    "Project",
    "Collaborator",
    # Pipeline
    "assemble",
    "AssemblyResult",
    # Export
    "export_to_yaml",
    "export_to_json",
]
__version__ = "3.0.0"
