#!/usr/bin/env python3
"""
Basic usage example for sslabdata.

This demonstrates the Python API for assembling academic lab data.
"""

from pathlib import Path
from sslabdata import LabDataConfig, assemble, export_to_yaml, export_to_json

# Example 1: Assemble data from config file
print("Example 1: Assemble from YAML config")
print("=" * 50)

config = LabDataConfig.from_yaml("config.yaml")
data = assemble(config)

print(f"Works: {len(data.works)}")
print(f"People: {len(data.people)}")
print(f"Projects: {len(data.projects)}")

# Export to YAML
export_to_yaml(data, "output/lab.yml")
print("Exported to output/lab.yml")

# Export to JSON
export_to_json(data, "output/lab.json")
print("Exported to output/lab.json")


# Example 2: Inspect the data
print("\n\nExample 2: Working with the data")
print("=" * 50)

for work in data.works[:3]:
    author_names = ", ".join(a.name for a in work.authors)
    print(f"\n{work.title}")
    print(f"  {author_names}")
    if work.venue:
        print(f"  {work.venue.name} ({work.venue.kind})")
    if work.project_ids:
        print(f"  Projects: {', '.join(work.project_ids)}")

for person in data.people:
    print(f"\n{person.name} ({person.role}, {person.status})")
    print(f"  {len(person.work_ids)} works")
