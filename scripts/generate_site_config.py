#!/usr/bin/env python3
"""
Write the Jekyll settings that come from lab.yaml to a separate config file.

The site title and description come from `lab.name` and `lab.description`;
`url` and `baseurl` come from the optional `site` section. Build with both
files so these values override site/_config.yml:

    python scripts/generate_site_config.py lab.yaml site/_config.generated.yml
    cd site && bundle exec jekyll build --config _config.yml,_config.generated.yml
"""

import argparse
from pathlib import Path

import yaml


def site_config(lab_config: dict) -> dict:
    """Map a parsed lab.yaml to Jekyll config values."""
    lab = lab_config.get('lab') or {}
    site = lab_config.get('site') or {}
    config = {}
    if lab.get('name'):
        config['title'] = lab['name']
    if lab.get('description'):
        config['description'] = lab['description']
    if site.get('url'):
        config['url'] = site['url']
    config['baseurl'] = site.get('baseurl', '')
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('lab_yaml', help='Path to lab.yaml')
    parser.add_argument('output', help='Path of the Jekyll config file to write')
    args = parser.parse_args()

    with open(args.lab_yaml, 'r', encoding='utf-8') as f:
        lab_config = yaml.safe_load(f) or {}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        f.write(f"# Generated from {args.lab_yaml} by scripts/generate_site_config.py. Do not edit.\n")
        yaml.safe_dump(site_config(lab_config), f, allow_unicode=True, sort_keys=False)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
