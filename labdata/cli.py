"""
Command-line interface for labdata.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import argparse
import sys

from .config import LabDataConfig
from .assembler import assemble
from .exporters import export_to_yaml, export_to_json


def main(argv=None):
    """Main CLI entry point. ``argv`` defaults to ``sys.argv[1:]``."""
    parser = argparse.ArgumentParser(
        description='Assemble academic lab data from BibTeX and YAML',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate YAML output
  labdata --config lab.yaml --output _data/lab.yml

  # Generate JSON output
  labdata --config lab.yaml --format json --output lab.json

  # Validate configuration and data
  labdata --config lab.yaml --validate

  # Show unresolved author names
  labdata --config lab.yaml --unresolved
        """
    )

    parser.add_argument(
        '--config', required=True,
        help='Path to YAML configuration file (lab.yaml)'
    )
    parser.add_argument(
        '--format', choices=['yaml', 'json'], default='yaml',
        help='Output format (default: yaml)'
    )
    parser.add_argument(
        '--output',
        help='Output file path'
    )
    parser.add_argument(
        '--validate', action='store_true',
        help='Validate configuration and report issues, then exit'
    )
    parser.add_argument(
        '--unresolved', action='store_true',
        help='Show unresolved author names, then exit'
    )

    args = parser.parse_args(argv)

    # Validate arguments
    if not args.output and not args.validate and not args.unresolved:
        parser.error("One of --output, --validate, or --unresolved is required")

    # Load configuration
    try:
        config = LabDataConfig.from_yaml(args.config)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)

    # Assemble data with diagnostics
    result = assemble(config, diagnostics=True)
    data = result.data

    # --validate mode
    if args.validate:
        errors = 0
        print(f"Publications: {len(data.publications)}")
        print(f"People: {len(data.people)}")
        print(f"Projects: {len(data.projects)}")

        if result.unresolved_authors:
            print(f"\nUnresolved authors ({len(result.unresolved_authors)}):")
            for name in sorted(result.unresolved_authors):
                print(f"  - {name}")

        if result.unknown_projects:
            print(f"\nUnknown project IDs ({len(result.unknown_projects)}):")
            for pid in sorted(result.unknown_projects):
                print(f"  - {pid}")
            errors += len(result.unknown_projects)

        if errors:
            print(f"\nValidation found {errors} error(s).")
            sys.exit(1)
        else:
            print("\nValidation passed.")
        return

    # --unresolved mode
    if args.unresolved:
        if not config.people_file:
            print("Author resolution is not configured (no people_file).")
            return
        if not result.unresolved_authors:
            print("All authors resolved.")
        else:
            print(f"Unresolved authors ({len(result.unresolved_authors)}):")
            for name in sorted(result.unresolved_authors):
                print(f"  {name}")
        return

    # Export
    export_func = export_to_yaml if args.format == 'yaml' else export_to_json
    export_func(data, args.output)

    print(f"Wrote {args.output}")
    print(f"  {len(data.publications)} publications, "
          f"{len(data.people)} people, "
          f"{len(data.projects)} projects")


if __name__ == "__main__":
    main()
