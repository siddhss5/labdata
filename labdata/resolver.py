"""
Entity resolution: link publications to people and projects.

Matches author names in publications to people in people.yaml using
explicit aliases (exact match) with fuzzy fallback (difflib).
Resolves project tags and computes back-links.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import re
import sys
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from .models import Author, Publication, Person, Project, LabData


# Default fuzzy match threshold (0.0 to 1.0)
FUZZY_THRESHOLD = 0.85

# Pattern for abbreviated names: single initial + surname (e.g., "A. Kim")
# After normalization (no periods): "a kim", "h zhang", etc.
_ABBREVIATED_NAME_RE = re.compile(r'^[a-z] [a-z]+$')


def normalize_name(name: str) -> str:
    """Normalize a name for matching.

    Lowercases, strips accents, removes periods and extra whitespace,
    and standardizes initial formats.
    """
    # Lowercase
    name = name.lower().strip()
    # Remove accents (é → e, ü → u, etc.)
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    # Remove periods
    name = name.replace('.', '')
    # Remove superscript HTML tags
    name = re.sub(r'<sup>.*?</sup>', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def is_abbreviated(name: str) -> bool:
    """Check if a normalized name is a single-initial abbreviation.

    Returns True for names like "a kim" or "h zhang" — these have
    too little information for reliable fuzzy matching.
    """
    return bool(_ABBREVIATED_NAME_RE.match(name))


def build_alias_index(people: List[Person]) -> Dict[str, str]:
    """Build a normalized name → person_id lookup from people data.

    Indexes both the canonical name and all explicit aliases.
    Detects and skips ambiguous aliases (same normalized form for different people),
    printing a warning to stderr.
    """
    index = {}
    # Track which aliases are ambiguous (map to multiple people)
    ambiguous: Dict[str, List[str]] = {}

    for person in people:
        # Index the canonical name
        normalized = normalize_name(person.name)
        if normalized in index and index[normalized] != person.id:
            ambiguous.setdefault(normalized, [index.pop(normalized)]).append(person.id)
        elif normalized not in ambiguous:
            index[normalized] = person.id

        # Index all aliases
        for alias in person.aliases:
            normalized_alias = normalize_name(alias)
            if normalized_alias in index and index[normalized_alias] != person.id:
                ambiguous.setdefault(normalized_alias, [index.pop(normalized_alias)]).append(person.id)
            elif normalized_alias in ambiguous:
                ambiguous[normalized_alias].append(person.id)
            else:
                index[normalized_alias] = person.id

    for name, ids in ambiguous.items():
        print(f"Warning: ambiguous alias '{name}' matches multiple people: {ids}", file=sys.stderr)

    return index


def fuzzy_match(name: str, index: Dict[str, str], threshold: float = FUZZY_THRESHOLD) -> Optional[str]:
    """Try fuzzy matching a name against the alias index.

    Skips matching for single-initial abbreviated names (e.g., "S. Zhang")
    since they lack enough information for reliable fuzzy matching.

    Returns the person_id of the best match above the threshold, or None.
    """
    normalized = normalize_name(name)

    # Don't fuzzy-match abbreviated names — too ambiguous
    if is_abbreviated(normalized):
        return None

    best_ratio = 0.0
    best_id = None

    for indexed_name, person_id in index.items():
        ratio = SequenceMatcher(None, normalized, indexed_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = person_id

    if best_ratio >= threshold:
        return best_id
    return None


def resolve_authors(
    publications: List[Publication],
    people: List[Person],
    fuzzy_threshold: float = FUZZY_THRESHOLD,
) -> List[str]:
    """Resolve author names in publications to person IDs.

    Strategy:
    1. Exact match against aliases (fast, reliable)
    2. Fuzzy match with threshold (fallback)

    Mutates Author.person_id in place.

    Returns:
        List of unresolved author names (for debugging/reporting)
    """
    if not people:
        return []

    index = build_alias_index(people)
    unresolved: Set[str] = set()

    for pub in publications:
        for author in pub.authors:
            normalized = normalize_name(author.name)

            # Try exact match first
            if normalized in index:
                author.person_id = index[normalized]
                continue

            # Try fuzzy match
            person_id = fuzzy_match(author.name, index, fuzzy_threshold)
            if person_id:
                author.person_id = person_id
                continue

            # Unresolved
            unresolved.add(author.name)

    return sorted(unresolved)


def resolve_projects(
    publications: List[Publication],
    projects: List[Project],
) -> List[str]:
    """Validate project IDs in publications against known projects.

    Returns list of unknown project IDs found in publications.
    Does NOT remove unknown project IDs from publications (they're kept
    for debugging visibility).
    """
    known_ids = {p.id for p in projects}
    unknown: Set[str] = set()

    for pub in publications:
        for pid in pub.project_ids:
            if pid not in known_ids:
                unknown.add(pid)

    return sorted(unknown)


def compute_backlinks(data: LabData) -> None:
    """Populate back-references on people and projects.

    Mutates data in place:
    - Person.publication_ids, Person.publication_count
    - Project.publication_ids, Project.people_ids
    """
    people_by_id = {p.id: p for p in data.people}
    projects_by_id = {p.id: p for p in data.projects}

    for pub in data.publications:
        # Back-link people
        for author in pub.authors:
            if author.person_id and author.person_id in people_by_id:
                person = people_by_id[author.person_id]
                if pub.bib_id not in person.publication_ids:
                    person.publication_ids.append(pub.bib_id)

        # Back-link projects
        for pid in pub.project_ids:
            if pid in projects_by_id:
                project = projects_by_id[pid]
                if pub.bib_id not in project.publication_ids:
                    project.publication_ids.append(pub.bib_id)

    # Update publication counts
    for person in data.people:
        person.publication_count = len(person.publication_ids)

    # Infer project people from publications
    for project in data.projects:
        people_set: Set[str] = set()
        for pub_id in project.publication_ids:
            pub = next((p for p in data.publications if p.bib_id == pub_id), None)
            if pub:
                for author in pub.authors:
                    if author.person_id:
                        people_set.add(author.person_id)
        project.people_ids = sorted(people_set)
