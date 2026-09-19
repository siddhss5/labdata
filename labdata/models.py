"""
Data models for labdata.

Defines the core entity types: Publication, Author, Person, Project,
and the assembled LabData output.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List


# Version of the output format (see schema/output.schema.json). Bump it when
# a change to to_dict() output could break a consumer.
#
# 2: authors carry their structured name parts (#23). The schema is closed,
#    so a consumer validating against version 1 would reject the new keys.
SCHEMA_VERSION = 2


@dataclass
class Author:
    """A resolved or unresolved author reference in a publication.

    ``name`` is the display form. The four parts below it are the name as
    BibTeX splits it, kept rather than collapsed so that later work has the
    structure to go on and not only a display string. ``literal`` holds a
    corporate name written as one brace-protected unit, such as
    ``{Example Robotics Consortium}``, where the other parts do not apply.
    """
    name: str
    person_id: Optional[str] = None
    given: Optional[str] = None
    von: Optional[str] = None
    family: Optional[str] = None
    suffix: Optional[str] = None
    literal: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'person_id': self.person_id,
            'given': self.given,
            'von': self.von,
            'family': self.family,
            'suffix': self.suffix,
            'literal': self.literal,
        }


@dataclass
class Publication:
    """A single publication with structured, renderer-agnostic data."""
    bib_id: str
    title: str
    authors: List[Author]
    year: int
    venue: str
    category: str
    entry_type: str

    abstract: Optional[str] = None
    note: Optional[str] = None
    pdf_url: Optional[str] = None
    doi_url: Optional[str] = None
    arxiv_url: Optional[str] = None
    url: Optional[str] = None
    video_url: Optional[str] = None

    project_ids: List[str] = field(default_factory=list)
    bibtex: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        d = {
            'bib_id': self.bib_id,
            'title': self.title,
            'authors': [a.to_dict() for a in self.authors],
            'year': self.year,
            'venue': self.venue,
            'category': self.category,
            'entry_type': self.entry_type,
            'abstract': self.abstract,
            'note': self.note,
            'pdf_url': self.pdf_url,
            'doi_url': self.doi_url,
            'arxiv_url': self.arxiv_url,
            'url': self.url,
            'video_url': self.video_url,
            'project_ids': self.project_ids,
        }
        if self.bibtex:
            d['bibtex'] = self.bibtex
        return d


@dataclass
class Person:
    """A lab member (current or alumni)."""
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    role: Optional[str] = None
    status: str = "current"
    photo: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    co_advisor: Optional[str] = None
    start_year: Optional[int] = None

    # Alumni-specific
    end_year: Optional[int] = None
    degree: Optional[str] = None
    thesis_title: Optional[str] = None
    current_position: Optional[str] = None

    # Back-linked (computed, not from YAML input)
    publication_count: int = 0
    publication_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        d = {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'status': self.status,
            'website': self.website,
            'publication_count': self.publication_count,
        }
        if self.photo:
            d['photo'] = self.photo
        if self.email:
            d['email'] = self.email
        if self.co_advisor:
            d['co_advisor'] = self.co_advisor
        if self.start_year:
            d['start_year'] = self.start_year
        if self.status == 'alumni':
            if self.end_year:
                d['end_year'] = self.end_year
            if self.degree:
                d['degree'] = self.degree
            if self.thesis_title:
                d['thesis_title'] = self.thesis_title
            if self.current_position:
                d['current_position'] = self.current_position
        if self.publication_ids:
            d['publication_ids'] = self.publication_ids
        return d


@dataclass
class Collaborator:
    """An external co-author not listed in people.yaml."""
    name: str
    publication_count: int = 0
    last_year: int = 0

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'publication_count': self.publication_count,
            'last_year': self.last_year,
        }


@dataclass
class Project:
    """A research project."""
    id: str
    title: str
    description: Optional[str] = None
    website: Optional[str] = None
    status: str = "active"

    # Back-linked (computed)
    publication_ids: List[str] = field(default_factory=list)
    people_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'website': self.website,
            'status': self.status,
            'publication_ids': self.publication_ids,
            'people_ids': self.people_ids,
        }


@dataclass
class LabData:
    """The fully resolved output: all entities with cross-references."""
    publications: List[Publication] = field(default_factory=list)
    people: List[Person] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    collaborators: List[Collaborator] = field(default_factory=list)
    lab: Optional[Dict[str, str]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        d = {
            'schema_version': SCHEMA_VERSION,
            'publications': [p.to_dict() for p in self.publications],
            'people': [p.to_dict() for p in self.people],
            'projects': [p.to_dict() for p in self.projects],
            'collaborators': [c.to_dict() for c in self.collaborators],
        }
        if self.lab:
            d['lab'] = self.lab
        return d
