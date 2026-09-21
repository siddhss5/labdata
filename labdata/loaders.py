"""
YAML data loaders for people and projects.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import sys
import yaml
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from pathlib import Path

from .diagnostics import diagnostic
from .models import Person, Project


# What can be wrong with a people or projects file, one code per condition
# and file. A file that is not a list of records, and a record with no id or
# no name, cannot be emitted at all, so they fail every mode; a repeated id
# fails `--validate`, as a repeated citation key does; the rest are warnings.
PEOPLE_NOT_A_LIST = "PEOPLE-NOT-A-LIST"
PEOPLE_FIELD_MISSING = "PEOPLE-FIELD-MISSING"
PEOPLE_ID_DUPLICATE = "PEOPLE-ID-DUPLICATE"
PEOPLE_ROLE_INVALID = "PEOPLE-ROLE-INVALID"
PEOPLE_STATUS_INVALID = "PEOPLE-STATUS-INVALID"
PROJECTS_NOT_A_LIST = "PROJECTS-NOT-A-LIST"
PROJECTS_FIELD_MISSING = "PROJECTS-FIELD-MISSING"
PROJECTS_ID_DUPLICATE = "PROJECTS-ID-DUPLICATE"
PROJECTS_STATUS_INVALID = "PROJECTS-STATUS-INVALID"

# A person's `status` is one of these. A `role` is any non-empty string, so
# that any lab's roles fit (SPEC.md, *The people and projects files*).
PERSON_STATUSES = ("current", "alumni")
PROJECT_STATUSES = ("active", "completed")


def _to(collected: Optional[List[str]]) -> Callable[[str], None]:
    """Report into a list, or to standard error when there is none."""
    def report(message: str) -> None:
        if collected is None:
            print(f"Warning: {message}", file=sys.stderr)
        else:
            collected.append(message)
    return report


def _records(path: str, not_a_list: str, missing: str, duplicate: str,
             required: tuple, errors, diagnostics) -> List[dict]:
    """The records of one people or projects file that can be emitted.

    A missing file is not this function's to report (the assembler names the
    configuration key instead) and reads as no records, as does an empty one.
    A record that is not a mapping, or that lacks a required field, is
    reported and left out; a repeated id is reported and kept, as the parser
    library keeps a repeated citation key.
    """
    fail, report = _to(errors), _to(diagnostics)
    if not Path(path).exists():
        return []

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if data is None:
        return []
    if not isinstance(data, list):
        fail(diagnostic(not_a_list, path, None, None,
                        "the file must be a list of records, one per entry; "
                        f"it is a {type(data).__name__}"))
        return []

    records, seen = [], set()
    for number, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            fail(diagnostic(not_a_list, path, None, None,
                            f"entry {number} is not a mapping"))
            continue
        key = entry.get('id')
        absent = [name for name in required
                  if entry.get(name) is None or str(entry[name]).strip() == ""]
        for name in absent:
            fail(diagnostic(missing, path, key if name != 'id' else None, name,
                            f"entry {number} has no {name}"))
        if absent:
            continue
        if key in seen:
            report(diagnostic(duplicate, path, key, 'id',
                              f"the id '{key}' is declared more than once"))
        seen.add(key)
        records.append(entry)
    return records


def load_people(path: str, errors: Optional[List[str]] = None,
                diagnostics: Optional[List[str]] = None,
                warnings: Optional[List[str]] = None) -> List[Person]:
    """Load people from a YAML file.

    Expected format (list of dicts):
        - id: "aadams"
          name: "Alice Adams"
          aliases: ["A. Adams", "A. J. Adams"]
          role: "pi"
          status: "current"
          ...

    ``errors``, ``diagnostics`` and ``warnings`` receive what is wrong with
    the file, in the three classes `labdata.assembler.AssemblyResult` keeps;
    without a list, a problem is printed to standard error.
    """
    warn = _to(warnings)
    people = []
    for entry in _records(path, PEOPLE_NOT_A_LIST, PEOPLE_FIELD_MISSING,
                          PEOPLE_ID_DUPLICATE, ('id', 'name'),
                          errors, diagnostics):
        role = entry.get('role')
        if not isinstance(role, str) or not role.strip():
            warn(diagnostic(PEOPLE_ROLE_INVALID, path, entry['id'], 'role',
                            "role is missing, empty or not a string; any "
                            "non-empty string is accepted"))
        status = entry.get('status', 'current')
        if status not in PERSON_STATUSES:
            warn(diagnostic(PEOPLE_STATUS_INVALID, path, entry['id'], 'status',
                            f"'{status}' is not one of "
                            f"{', '.join(PERSON_STATUSES)}"))
        person = Person(
            id=entry['id'],
            name=entry['name'],
            aliases=entry.get('aliases', []),
            role=entry.get('role'),
            status=status,
            photo=entry.get('photo'),
            website=entry.get('website'),
            email=entry.get('email'),
            co_advisor=entry.get('co_advisor'),
            start_year=entry.get('start_year'),
            end_year=entry.get('end_year'),
            degree=entry.get('degree'),
            thesis_title=entry.get('thesis_title'),
            current_position=entry.get('current_position'),
        )
        people.append(person)

    return people


def load_projects(path: str, errors: Optional[List[str]] = None,
                  diagnostics: Optional[List[str]] = None,
                  warnings: Optional[List[str]] = None) -> List[Project]:
    """Load projects from a YAML file.

    Expected format (list of dicts):
        - id: "gardenbot"
          title: "Robot-Assisted Gardening"
          description: "Autonomous gardening systems"
          website: "https://gardenbot.example.org"
          status: "active"

    Problems are reported as `load_people()` reports them.
    """
    warn = _to(warnings)
    projects = []
    for entry in _records(path, PROJECTS_NOT_A_LIST, PROJECTS_FIELD_MISSING,
                          PROJECTS_ID_DUPLICATE, ('id', 'title'),
                          errors, diagnostics):
        status = entry.get('status', 'active')
        if status not in PROJECT_STATUSES:
            warn(diagnostic(PROJECTS_STATUS_INVALID, path, entry['id'],
                            'status', f"'{status}' is not one of "
                            f"{', '.join(PROJECT_STATUSES)}"))
        project = Project(
            id=entry['id'],
            title=entry['title'],
            description=entry.get('description'),
            website=entry.get('website'),
            status=status,
        )
        projects.append(project)

    return projects


@dataclass
class DeclaredCollaborator:
    """One external co-author declared in `collaborators_file`.

    It only groups authorships into `collaborators`; it is never a person
    and never produces a `person_id`.
    """
    name: str
    aliases: List[str] = field(default_factory=list)


def load_collaborators(path: str) -> List[DeclaredCollaborator]:
    """Load declared external co-authors from a YAML file.

    Expected format (list of dicts):
        - name: "Priya Patel"
          aliases: ["P. Patel"]
    """
    if not Path(path).exists():
        return []

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, list):
        return []

    return [DeclaredCollaborator(name=entry['name'],
                                 aliases=entry.get('aliases', []))
            for entry in data]
