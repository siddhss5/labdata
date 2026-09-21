"""
Main pipeline orchestrator.

Assembles the complete LabData output from configuration:
config → parse BibTeX → load people/projects → resolve links → back-link.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import hashlib
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .config import LabDataConfig, reject_absolute_name
from .models import Author, Collaborator, LabData, Work
from .parsers.bibtex import parse_all_works
from .loaders import load_people, load_projects
from .resolver import (
    compute_backlinks, normalize_name, resolve_authors, resolve_projects,
)


# The policy that built a collaborator key. It is a declared, open string, so
# #25 can emit `explicit` or `orcid` without a schema version bump.
GROUPED_BY_NORMALIZED_NAME = "normalized_name"

# Whether the name was written as one brace-protected unit. Not
# `person`/`organization`: braces in BibTeX mean "do not parse this", which
# covers organisations but also mononyms, so the document must not assert
# corporate-ness.
PERSONAL, LITERAL = "personal", "literal"

# The digest is always present, never conditional on a collision, so adding
# an unrelated collaborator can never change an existing key. Eight hex
# characters of SHA-256 over the name kind and the normalised name.
_DIGEST_LENGTH = 8

# A slug long enough to stay readable and short enough to stay a key.
_SLUG_LENGTH = 60

_NOT_SLUG = re.compile(r"-+")

# Two ways a grouping key can be wrong that the document would otherwise keep
# to itself. Neither is an error: an external co-author is never an error
# (SPEC.md section 1), and the grouping policy itself is #24's.
GROUPING_SPANS_SPELLINGS = "ID-GROUPING-SPANS-SPELLINGS"
GROUPING_INITIALS_AMBIGUOUS = "ID-GROUPING-INITIALS-AMBIGUOUS"

# One part of a given name that is an initial rather than a name: a letter,
# its period optional, and a hyphenated run of them -- `A.`, `A`, `G.-A.`,
# `J-P`. A Unicode letter, so `Ç.` is read as an initial and a name outside
# ASCII is not silently exempt. A part that is anything else is read as a
# name, which is the safe direction for a warning: it reports one grouping
# key too few rather than one too many.
_INITIAL = re.compile(r"^[^\W\d_]\.?(?:-[^\W\d_]\.?)*$", re.UNICODE)


def _given_parts(given: Optional[str]) -> List[str]:
    return [part for part in (given or "").split() if part]


def initials_only(given: Optional[str]) -> bool:
    """True when every part of a given name is an initial rather than a name."""
    parts = _given_parts(given)
    return bool(parts) and all(_INITIAL.match(part) for part in parts)


def given_initials(given: Optional[str]) -> Tuple[str, ...]:
    """The initial of each part of a given name, normalised.

    ``Alice Jane`` and ``A. J.`` both give ``("a", "j")``; ``Grace-Ann`` and
    ``G.-A.`` both give ``("g-a",)``, because both halves of a hyphenated
    given name carry an initial.
    """
    return tuple("-".join(normalize_name(piece)[:1]
                          for piece in part.split("-") if piece)
                 for part in _given_parts(given))

# A document needs a header, and a header with no name is one a renderer
# cannot title a page from.
LAB_NAME_MISSING = "CONFIG-LAB-NAME-MISSING"


@dataclass
class AssemblyResult:
    """Result of assembling lab data, including diagnostics.

    Three buckets, because three severities are already in use and severity
    is carried by the run rather than by the code (SPEC.md, *Diagnostic
    codes*): ``fatal_errors`` fail every mode, ``bibliography_errors`` fail
    ``--validate``, and ``warnings`` never fail anything.
    """
    data: LabData
    unresolved_authors: List[str] = field(default_factory=list)
    unknown_projects: List[str] = field(default_factory=list)
    bibliography_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fatal_errors: List[str] = field(default_factory=list)


def collaborator_key(name_kind: str, normalized: str) -> str:
    """A lookup key for one grouping of unresolved authorships.

    A readable slug of the normalised name plus a short digest of the name
    kind and that same normalised name. It is explicitly **not** an assertion
    about a human: a name-derived value used as an id is an identity claim
    however it is described, because that is how consumers use it.

    The digest is always present rather than added on collision, so an
    unrelated collaborator arriving later can never change an existing key.
    A name that leaves no slug behind -- one written entirely in punctuation,
    or the corpus name with a newline in it -- is keyed on the digest alone.
    """
    digest = hashlib.sha256(
        (name_kind + "\x00" + normalized).encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    slug = "".join(c if c.isalnum() else "-" for c in normalized)
    slug = _NOT_SLUG.sub("-", slug).strip("-")[:_SLUG_LENGTH].strip("-")
    return f"{slug}-{digest}" if slug else digest


class _Grouping:
    """One collaborator under construction, in the order the works are read."""

    def __init__(self, key: str, author: Author, normalized: str):
        self.key = key
        self.normalized = normalized
        self.name_kind = LITERAL if author.literal else PERSONAL
        self.author = author            # the first spelling, in document order
        # Read from the structured parts rather than from the key, so a
        # particle, a second initial, a hyphenated family name and a name
        # outside ASCII are all visible. Used by the diagnostics below and by
        # nothing else: they decide nothing about grouping or matching.
        self.family = normalize_name(author.family or "")
        self.von = normalize_name(author.von or "")
        self.suffix = normalize_name(author.suffix or "")
        self.initials = given_initials(author.given)
        self.initials_only = initials_only(author.given)
        self.variants: List[str] = []
        self.authorships: List[Dict[str, object]] = []
        self.work_ids: List[str] = []
        self.last_year: Optional[int] = None
        self.where: str = ""

    def add(self, work: Work, author: Author, where: str) -> None:
        if not self.authorships:
            self.where = where
        if author.name not in self.variants:
            self.variants.append(author.name)
        self.authorships.append({"work_id": work.bib_id,
                                 "position": author.position})
        if work.bib_id not in self.work_ids:
            self.work_ids.append(work.bib_id)
        if work.year is not None:
            self.last_year = max(self.last_year or work.year, work.year)

    def could_be(self, other: "_Grouping") -> bool:
        """True when this initials-only key could be that fuller one.

        Same family and same particles, and one set of initials a prefix of
        the other, in whichever direction is shorter: `A. Smith` could be
        `Alice Smith` or `Alice Jane Smith`, and `A. J. Smith` could be
        either as well. A name written as one brace-protected unit has no
        parts to compare and takes part in neither side.

        Two lineage suffixes that disagree are two people: `J. Smith, Jr.` is
        not `John Smith, Sr.`, and saying so would be a warning about a
        merge that cannot happen. One suffix against none is not a
        disagreement -- an entry that omits it has said nothing -- so those
        still pair.
        """
        if other.key == self.key or not self.initials_only:
            return False
        if self.name_kind != PERSONAL or other.name_kind != PERSONAL:
            return False
        if other.initials_only or not other.initials:
            return False
        if not self.family or self.family != other.family:
            return False
        if self.von != other.von:
            return False
        if self.suffix and other.suffix and self.suffix != other.suffix:
            return False
        shorter, longer = sorted((self.initials, other.initials), key=len)
        return longer[:len(shorter)] == shorter

    def build(self) -> Collaborator:
        return Collaborator(
            key=self.key,
            name=self.author.name,
            grouped_by=GROUPED_BY_NORMALIZED_NAME,
            name_kind=self.name_kind,
            given=self.author.given,
            von=self.author.von,
            family=self.author.family,
            suffix=self.author.suffix,
            literal=self.author.literal,
            name_variants=sorted(self.variants),
            authorships=self.authorships,
            work_ids=self.work_ids,
            work_count=len(self.work_ids),
            authorship_count=len(self.authorships),
            last_year=self.last_year,
        )


def group_collaborators(works: List[Work], bib_dir: str,
                        warnings: List[str]) -> List[Collaborator]:
    """Group every unresolved authorship, and say where the grouping is risky.

    The grouping is keyed on the normalised full name, which is today's
    policy against the new key rather than a new policy: tuning it -- joining
    two spellings of one person, splitting two people who write alike -- is
    #24's. What this does add is the two diagnostics that make the remaining
    merge risk visible instead of silent.

    Mutates ``author.collaborator_key`` in place, so every authorship
    references exactly one contributor.
    """
    groups: Dict[str, _Grouping] = {}
    for work in works:
        for author in work.authors:
            if author.person_id:
                continue
            normalized = normalize_name(author.name)
            kind = LITERAL if author.literal else PERSONAL
            key = collaborator_key(kind, normalized)
            author.collaborator_key = key
            group = groups.get(key)
            if group is None:
                group = groups[key] = _Grouping(key, author, normalized)
            group.add(work, author, f"{bib_dir}/{work.source_file}:{work.bib_id}:author")

    warnings.extend(_grouping_warnings(groups))

    # `name` stays the tie-break it was, with `key` appended after it: two
    # keys can carry the same readable name -- a parsed and a brace-protected
    # spelling of one string are two keys -- so the name alone is no longer
    # total, but it is still what a reader sees and it still decides.
    ordered = sorted(groups.values(),
                     key=lambda g: (g.last_year is None, -(g.last_year or 0),
                                    -len(g.work_ids), g.author.name, g.key))
    return [group.build() for group in ordered]


def _grouping_warnings(groups: Dict[str, "_Grouping"]) -> List[str]:
    """The two ways a key over- or under-groups, reported against a work.

    Both are located at the first authorship the key grouped, which is where
    a human goes to fix the spelling.
    """
    reported = []
    for group in sorted(groups.values(), key=lambda g: g.key):
        if len(group.variants) > 1:
            spellings = ", ".join(repr(v) for v in sorted(group.variants))
            reported.append(
                f"{GROUPING_SPANS_SPELLINGS} {group.where}: collaborator key "
                f"'{group.key}' groups {len(group.variants)} spellings of one "
                f"name: {spellings}")
        fuller = sorted(other.key for other in groups.values()
                        if group.could_be(other))
        if fuller:
            reported.append(
                f"{GROUPING_INITIALS_AMBIGUOUS} {group.where}: collaborator key "
                f"'{group.key}' is initials only and could be any of: "
                + ", ".join(repr(k) for k in fuller))
    return reported


def assemble(config: LabDataConfig, diagnostics: bool = False):
    """Main entry point: config → fully resolved LabData.

    1. Parse all BibTeX files into Works
    2. Load people and projects from YAML
    3. Resolve contributor names → person IDs
    4. Validate project IDs
    5. Group the authorships that resolved to nobody
    6. Compute back-links (people→works, projects→works, projects→people)

    Args:
        config: Lab data configuration
        diagnostics: If True, return AssemblyResult with diagnostics.
                     If False (default), return LabData directly.
    """
    # Every configured name, checked here rather than only where it was
    # built. `BibFile` is a public, mutable dataclass, so a name can be set
    # after construction, and `work.source.file` is promised never to be
    # absolute however the configuration was assembled (SPEC.md section 5).
    # The CLI never reaches this: `LabDataConfig.from_yaml()` rejects the
    # same thing first, with the file the user would edit named. This is for
    # a caller who built the configuration in Python, who gets the exception.
    for bib_file in config.bib_files:
        reject_absolute_name(getattr(bib_file, 'name', None), "bib_files:name")

    # Parse works
    bib_files = [{'name': bf.name, 'category': bf.category} for bf in config.bib_files]
    bibliography_errors: List[str] = []
    warnings: List[str] = []
    fatal_errors: List[str] = []
    works = parse_all_works(
        bib_dir=config.bib_dir,
        bib_files=bib_files,
        pdf_base_url=config.pdf_base_url,
        diagnostics=bibliography_errors,
        warnings=warnings,
        errors=fatal_errors,
    )

    # Load people and projects
    people = load_people(config.people_file) if config.people_file else []
    projects = load_projects(config.projects_file) if config.projects_file else []

    # Resolve
    unresolved_authors = resolve_authors(works, people)
    unknown_projects = resolve_projects(works, projects)

    # Group the authorships that resolved to nobody
    collaborators = group_collaborators(works, config.bib_dir, warnings)

    # A header a renderer cannot title a page from. A `lab` that is not a
    # mapping at all is a different condition -- the header is malformed
    # rather than unnamed -- and reporting this one against it would be a
    # diagnostic that named the wrong defect, so it is left to #26.
    if config.lab is None or isinstance(config.lab, dict):
        if not (config.lab or {}).get("name"):
            warnings.append(
                f"{LAB_NAME_MISSING} {config.path or 'lab.yaml'}:lab:name: "
                "the lab header declares no name")

    # Assemble
    data = LabData(
        works=works,
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
            warnings=warnings,
            fatal_errors=fatal_errors,
        )

    # Without a caller to hand them to, every diagnostic still reaches the
    # user: nothing labdata found is dropped because of how it was called.
    for message in fatal_errors + bibliography_errors + warnings:
        print(f"Warning: {message}", file=sys.stderr)
    return data
