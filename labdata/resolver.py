"""
Entity resolution: link works to people and projects.

Matches contributor names in works to people in people.yaml using
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
from typing import Dict, List, Optional, Sequence, Set

from .models import Contributor, Work, Person, Project, LabData


# Default fuzzy match threshold (0.0 to 1.0)
FUZZY_THRESHOLD = 0.85

# Pattern for abbreviated names: single initial + surname (e.g., "A. Kim")
# After normalization (no periods): "a kim", "h zhang", etc.
_ABBREVIATED_NAME_RE = re.compile(r'^[a-z] [a-z]+$')

# How a contributor's `resolution.status` reads, and how it resolved. Both are
# open strings: #24 adds `ambiguous` to the first and #25 fills the second
# with an explicit override or an ORCID, and neither is a breaking change.
RESOLVED, UNRESOLVED = "resolved", "unresolved"
BY_NAME, BY_FUZZY = "exact", "fuzzy"


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


def _initials(given: str) -> str:
    """Abbreviate one given name: ``Alice`` → ``A.``, ``Grace-Ann`` → ``G.-A.``"""
    parts = [part for part in given.split("-") if part]
    return "-".join(f"{part[0]}." for part in parts)


def match_form(contributor: Contributor) -> str:
    """The private form a contributor's name is matched on: ``A. J. van Last, Jr.``

    This is the form `format_name()` used to produce and the document used to
    display, before #56 separated the two. It stays the matching form so that
    making `contributor.name` the full name changes nothing about who resolves
    to whom: the emitted name and the matched name are now independent, which
    is what lets #24 change matching later without touching the schema.

    A name written as one brace-protected unit has nothing to abbreviate and
    is matched as written.
    """
    if contributor.literal:
        return contributor.literal
    given = contributor.given or ""
    initials = " ".join(_initials(part) for part in given.split())
    name = " ".join(part for part in (initials, contributor.von,
                                      contributor.family) if part)
    suffix = contributor.suffix
    return f"{name}, {suffix}" if suffix and name else (name or suffix or "")


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

    Skips matching for single-initial abbreviated names (e.g. "S. Zhang")
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


def _resolve(contributors: Sequence[Contributor], index: Dict[str, str],
             fuzzy_threshold: float) -> List[str]:
    """Resolve one list of contributors in place; return the names left over."""
    unresolved: List[str] = []
    for contributor in contributors:
        matched = match_form(contributor)
        normalized = normalize_name(matched)

        # Try exact match first
        if normalized in index:
            contributor.person_id = index[normalized]
            contributor.resolution_status = RESOLVED
            contributor.resolution_method = BY_NAME
            continue

        # Try fuzzy match
        person_id = fuzzy_match(matched, index, fuzzy_threshold)
        if person_id:
            contributor.person_id = person_id
            contributor.resolution_status = RESOLVED
            contributor.resolution_method = BY_FUZZY
            continue

        unresolved.append(contributor.name)
    return unresolved


def resolve_authors(
    works: List[Work],
    people: List[Person],
    fuzzy_threshold: float = FUZZY_THRESHOLD,
) -> List[str]:
    """Resolve contributor names in works to person IDs.

    Strategy:
    1. Exact match against aliases (fast, reliable)
    2. Fuzzy match with threshold (fallback)

    Matching reads the private form of `match_form()`, never the name the
    document emits, so what a consumer sees and what the resolver compares
    are independent.

    Editors are resolved by the same machinery. They are not authorships, so
    an editor that matches nobody is simply left unresolved and is not
    reported as an unresolved author.

    Mutates ``person_id`` and ``resolution`` in place.

    Returns:
        The readable names of authorships that matched no person, sorted.
    """
    if not people:
        return []

    index = build_alias_index(people)
    unresolved: Set[str] = set()

    for work in works:
        unresolved |= set(_resolve(work.authors, index, fuzzy_threshold))
        _resolve(work.editors, index, fuzzy_threshold)

    return sorted(unresolved)


def resolve_projects(
    works: List[Work],
    projects: List[Project],
) -> List[str]:
    """Validate project IDs in works against known projects.

    Returns list of unknown project IDs found in works.
    Does NOT remove unknown project IDs from works (they're kept
    for debugging visibility).
    """
    known_ids = {p.id for p in projects}
    unknown: Set[str] = set()

    for work in works:
        for pid in work.project_ids:
            if pid not in known_ids:
                unknown.add(pid)

    return sorted(unknown)


def compute_backlinks(data: LabData) -> None:
    """Populate back-references on people and projects.

    Editing a volume is not an authorship, so `work.editors` contribute to
    none of these: not to a person's works, not to their count, and not to a
    project's people.

    Mutates data in place:
    - Person.work_ids, Person.work_count
    - Project.work_ids, Project.people_ids
    """
    people_by_id = {p.id: p for p in data.people}
    projects_by_id = {p.id: p for p in data.projects}

    for work in data.works:
        # Back-link people
        for author in work.authors:
            if author.person_id and author.person_id in people_by_id:
                person = people_by_id[author.person_id]
                if work.bib_id not in person.work_ids:
                    person.work_ids.append(work.bib_id)

        # Back-link projects
        for pid in work.project_ids:
            if pid in projects_by_id:
                project = projects_by_id[pid]
                if work.bib_id not in project.work_ids:
                    project.work_ids.append(work.bib_id)

    # Update work counts
    for person in data.people:
        person.work_count = len(person.work_ids)

    # Infer project people from works
    for project in data.projects:
        people_set: Set[str] = set()
        for work_id in project.work_ids:
            work = next((w for w in data.works if w.bib_id == work_id), None)
            if work:
                for author in work.authors:
                    if author.person_id:
                        people_set.add(author.person_id)
        project.people_ids = sorted(people_set)
