"""
YAML data loaders for people and projects.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import yaml
from typing import List
from pathlib import Path

from .models import Person, Project


def load_people(path: str) -> List[Person]:
    """Load people from a YAML file.

    Expected format (list of dicts):
        - id: "aadams"
          name: "Alice Adams"
          aliases: ["A. Adams", "A. J. Adams"]
          role: "pi"
          status: "current"
          ...
    """
    if not Path(path).exists():
        return []

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, list):
        return []

    people = []
    for entry in data:
        person = Person(
            id=entry['id'],
            name=entry['name'],
            aliases=entry.get('aliases', []),
            role=entry.get('role'),
            status=entry.get('status', 'current'),
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


def load_projects(path: str) -> List[Project]:
    """Load projects from a YAML file.

    Expected format (list of dicts):
        - id: "gardenbot"
          title: "Robot-Assisted Gardening"
          description: "Autonomous gardening systems"
          website: "https://gardenbot.example.org"
          status: "active"
    """
    if not Path(path).exists():
        return []

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, list):
        return []

    projects = []
    for entry in data:
        project = Project(
            id=entry['id'],
            title=entry['title'],
            description=entry.get('description'),
            website=entry.get('website'),
            status=entry.get('status', 'active'),
        )
        projects.append(project)

    return projects
