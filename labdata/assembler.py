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
from .models import Author, Collaborator, LabData, Person, Work
from .parsers.bibtex import parse_all_works
from .loaders import (
    DeclaredCollaborator, load_collaborators, load_people, load_projects,
)
from .resolver import (
    AMBIGUOUS, AMBIGUOUS_NAME, RESOLVED, Candidates, compute_backlinks, given_initials,
    initials_only, match, match_key, normalize_name, person_candidates,
    resolve_authors, resolve_projects,
)


# The policy that built a collaborator key. It is a declared, open string, so
# #25 can emit `explicit` or `orcid` without a schema version bump.
# `declared` is a grouping `collaborators_file` asked for: its name and
# aliases joined the spellings, and it is still a grouping, never a person.
GROUPED_BY_NORMALIZED_NAME = "normalized_name"
GROUPED_BY_DECLARED = "declared"

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
# (SPEC.md section 1).
GROUPING_SPANS_SPELLINGS = "ID-GROUPING-SPANS-SPELLINGS"
GROUPING_INITIALS_AMBIGUOUS = "ID-GROUPING-INITIALS-AMBIGUOUS"

# A `collaborators_file` name or alias that a lab member already declares.
# Resolving to the member wins, because the collaborator file never produces
# a `person_id`, and the collaborator entry is not used for that spelling;
# saying so is what keeps the choice from being silent.
COLLABORATOR_ALIAS_IS_MEMBER = "RESOLVE-COLLABORATOR-ALIAS-IS-MEMBER"

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

    def __init__(self, key: str, author: Author, normalized: str,
                 grouped_by: str = GROUPED_BY_NORMALIZED_NAME):
        self.key = key
        self.grouped_by = grouped_by
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
            grouped_by=self.grouped_by,
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


def declared_collaborators(declared: List[DeclaredCollaborator],
                           people: List[Person], source: str,
                           warnings: List[str]) -> List[Tuple[str, List[str]]]:
    """The `collaborators_file` entries as ``(normalised name, spellings)``,
    minus any spelling a lab member already declares.

    The normalised name is what the entry's collaborator key is built from. A
    name or alias equal to a member's name or alias is reported under
    `COLLABORATOR_ALIAS_IS_MEMBER` and left out, so the member is never
    shadowed and the collaborator never silently chosen.
    """
    members = person_candidates(people)
    entries = []
    for collaborator in declared:
        kept = []
        for field_name, name in [("name", collaborator.name)] + [
                ("aliases", alias) for alias in collaborator.aliases]:
            owners = members.ids_for(match_key(name))
            if owners:
                warnings.append(
                    f"{COLLABORATOR_ALIAS_IS_MEMBER} {source}:"
                    f"{collaborator.name}:{field_name}: '{name}' is also "
                    f"declared by {', '.join(sorted(owners))}; the member keeps "
                    "it and the collaborator entry is not used for it")
            else:
                kept.append(name)
        entries.append((normalize_name(collaborator.name), kept))
    return entries


def group_collaborators(works: List[Work], bib_dir: str,
                        warnings: List[str],
                        declared: Optional[List[Tuple[str, List[str]]]] = None,
                        people: Optional[List[Person]] = None) -> List[Collaborator]:
    """Group every unresolved authorship, and say where the grouping is risky.

    The grouping is keyed on the normalised full name. An authorship that
    matches exactly one `collaborators_file` entry -- by the same rules a
    person is matched by, with the lab members competing -- is grouped under
    that entry's key instead, which is what joins `Patel, Priya` and
    `Patel, P.` once `P. Patel` is declared. A name that fits a declared
    collaborator and anyone else is reported and grouped by name.

    Mutates ``author.collaborator_key`` in place, so every authorship
    references exactly one contributor.
    """
    rivals = None
    if declared:
        rivals = Candidates(
            [(f"collaborator:{name}", spellings) for name, spellings in declared]
            + [(f"person:{p.id}", [p.name] + list(p.aliases))
               for p in (people or [])])
    groups: Dict[str, _Grouping] = {}
    for work in works:
        where = f"{bib_dir}/{work.source_file}:{work.bib_id}:author"
        for author in work.authors:
            if author.person_id:
                continue
            normalized = normalize_name(author.name)
            kind = LITERAL if author.literal else PERSONAL
            grouped_by = GROUPED_BY_NORMALIZED_NAME
            if rivals is not None:
                found = match(author, rivals)
                ids = found.ids
                if found.status == RESOLVED and ids[0].startswith("collaborator:"):
                    normalized = ids[0].split(":", 1)[1]
                    kind, grouped_by = PERSONAL, GROUPED_BY_DECLARED
                elif found.status == AMBIGUOUS and any(
                        i.startswith("collaborator:") for i in ids):
                    warnings.append(
                        f"{AMBIGUOUS_NAME} {where}: position {author.position}, "
                        f"'{author.name}', fits more than one declared "
                        f"collaborator or member and is grouped by its own "
                        f"name: {', '.join(ids)}")
            key = collaborator_key(kind, normalized)
            author.collaborator_key = key
            group = groups.get(key)
            if group is None:
                group = groups[key] = _Grouping(key, author, normalized, grouped_by)
            group.add(work, author, where)

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
    a human goes to fix the spelling. A grouping `collaborators_file`
    declared spans its spellings because a human said it should, so neither
    is reported against it.
    """
    reported = []
    for group in sorted(groups.values(), key=lambda g: g.key):
        if group.grouped_by == GROUPED_BY_DECLARED:
            continue
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
    # Every configured name, checked before anything is parsed, so a
    # configuration labdata will not compile from fails here rather than
    # after the work of reading every file. This is not the check that holds
    # -- `Work.to_dict()` is, at the boundary every emitted document passes
    # through -- it is the one that fails soonest. The CLI never reaches it:
    # `LabDataConfig.from_yaml()` rejects the same thing first, with the file
    # the user would edit named.
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
    unresolved_authors = resolve_authors(works, people, warnings=warnings,
                                         bib_dir=config.bib_dir)
    unknown_projects = resolve_projects(works, projects)

    # Group the authorships that resolved to nobody, joining the spellings
    # `collaborators_file` declares
    declared = None
    if config.collaborators_file:
        declared = declared_collaborators(
            load_collaborators(config.collaborators_file), people,
            config.collaborators_file, warnings)
    collaborators = group_collaborators(works, config.bib_dir, warnings,
                                        declared, people)

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
