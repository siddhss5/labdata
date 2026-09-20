# labdata

labdata compiles BibTeX and a little YAML into one validated document — works,
people, projects and the links between them — that any website, CV or script
can read.

Most academics already keep good BibTeX. What they do not have is that
bibliography as *data*: authors linked to the people in the group, papers
linked to the projects they belong to, names normalised, LaTeX resolved to
plain Unicode text. labdata does that one job, checks the result against a
published schema, and writes it to a single YAML or JSON file.

```bash
labdata --config lab.yaml --output lab.yml
```

- [`SPEC.md`](SPEC.md) — the normative contract: what the strings are, what
  order the lists are in, which fields are derived, when the version changes.
- [`schema/output.schema.json`](schema/output.schema.json) — the document's
  JSON Schema.
- [`tests/COVERAGE.md`](tests/COVERAGE.md) — every input case labdata
  supports, and every case it does not, with the fixture and test for each.

## What labdata is not

**labdata is not a CMS and not a site generator.** It does not build a
website, own your pages or manage your content. News, openings, teaching
pages, press and galleries are prose with no shared structure to compile, and
they belong in your site repository. [`SPEC.md` §8](SPEC.md) gives the
evidence for that boundary and the destination for each content type it
leaves out.

labdata emits data. Rendering it is your renderer's job.

## Install

```bash
pip install git+https://github.com/siddhss5/labdata.git
```

## Write `lab.yaml`

```yaml
lab:
  name: "My Lab"
  description: "What our lab does"
  university: "University Name"
  website: "https://mylab.example.org"

bib_dir: "data/bib"
bib_files:
  - name: "journal.bib"
    category: "Journal Papers"
  - name: "conference.bib"
    category: "Conference Papers"

pdf_base_url: "https://mylab.example.org/pdfs"
people_file: "data/people.yaml"       # optional
projects_file: "data/projects.yaml"   # optional
```

Paths are relative to the directory you run `labdata` from.
[`examples/demo/lab.yaml`](examples/demo/lab.yaml) is a complete example,
built from the fictional Example Lab in [`examples/demo/`](examples/demo/).

Then compile it:

```bash
labdata --config lab.yaml --validate            # report counts and problems
labdata --config lab.yaml --unresolved          # list unmatched author names
labdata --config lab.yaml --output lab.yml      # write the document
labdata --config lab.yaml --format json --output lab.json
```

`--validate` exits `1` when it finds an error, `0` otherwise. The exit codes
are part of the contract; [`SPEC.md` §1](SPEC.md) lists them.

## Inputs

### BibTeX (required)

Standard `.bib` files. labdata reads these fields:

| Field | Becomes |
|-------|---------|
| `title` | `title`, LaTeX converted to plain Unicode text; `$...$` math kept as TeX |
| `author` | `authors`, each with a display `name`, its `given` / `von` / `family` / `suffix` parts (or `literal` for a corporate name), a `person_id` when it matched someone in `people.yaml`, and `equal_contribution` |
| `year` | `year`, and the sort order of the publication list |
| `journal` / `booktitle` / `school` / `institution`, with `volume`, `number`, `type` | `venue`, composed according to the entry type ([`SPEC.md` §5](SPEC.md)) |
| `doi` | `doi_url` |
| `eprint` + `archivePrefix` | `arxiv_url` |
| `abstract` | `abstract` |
| `note` | `note` |
| `url` | `video_url` when it points at YouTube or Vimeo, otherwise `url` |
| `project` | `project_ids` (see below) |

The whole entry is also emitted verbatim as `bibtex`, so fields labdata does
not read are not lost. The full list of bibliographic fields the document does
not yet carry as first-class properties is tracked in
[#56](https://github.com/siddhss5/labdata/issues/56).

### The `project` tag

labdata adds one custom BibTeX field, `project`, to link a paper to a research
project:

```bibtex
@inproceedings{cote2024pantry,
  title     = {Where Does This Go? Object Placement in Unfamiliar Kitchens},
  author    = {C{\^o}t{\'e}, Carol and Davis, Dave and Adams, Alice},
  booktitle = {Proceedings of the Conference on Robot Learning Systems},
  year      = {2024},
  eprint    = {2406.99812},
  archivePrefix = {arXiv},
  project   = {homebot}
}
```

Several projects go in one field, comma-separated:
`project = {homebot, sharedcontrol}`. Each project in the document then
back-links the publications tagged with it, and the people who wrote them.

### People (optional, `data/people.yaml`)

A list of lab members and alumni. `aliases` tells labdata how to match BibTeX
author names to people:

```yaml
- id: "bbrown"
  name: "Bob Brown"
  aliases: ["B. Brown"]
  role: "phd_student"
  status: "current"
  website: "https://example.org/people/bbrown"
  co_advisor: "Peggy Park"
  start_year: 2021

- id: "iingram"
  name: "Ivan Ingram"
  aliases: ["I. Ingram"]
  role: "phd_student"
  status: "alumni"
  start_year: 2016
  end_year: 2022
  degree: "PhD"
  thesis_title: "Learning Grasp Affordances from Play"
  current_position: "Research Scientist, Example Robotics Inc."
```

### Projects (optional, `data/projects.yaml`)

```yaml
- id: "homebot"
  title: "Household Manipulation"
  description: "Robots that tidy up, fetch things and put them away in real homes."
  website: "https://example.org/projects/homebot"
  status: "active"
```

## How author matching works

labdata matches BibTeX author names to lab members in two passes:

1. **Exact alias match** against the `aliases` list in `people.yaml`, after
   normalising case, accents and punctuation.
2. **Fuzzy fallback** on string similarity, threshold 0.85, for minor spelling
   variations. Single-initial names such as `S. Zhang` are never fuzzy-matched:
   there is not enough there to match on.

A name that matches nobody keeps `person_id: null` and appears in the derived
`collaborators` list. `labdata --config lab.yaml --unresolved` shows those
names so you can add aliases.

`collaborators` is keyed by display name, which is not an identity: three
people who all write as `J. Smith` are one entry. Read it as an index of
unresolved authorships, not as a list of humans.

## Reading the document

The output is one YAML or JSON file. Every string in it is plain Unicode text
— not HTML, not Markdown, not escaped — and it is untrusted, so **escape it
when you render it**. Math is the one exception and stays delimited by `$…$`.
[`SPEC.md` §2](SPEC.md) states the rule and its exceptions.

Validate a document against the schema with any JSON Schema tool:

```bash
python -c "
import json, yaml, jsonschema
schema = json.load(open('schema/output.schema.json'))
jsonschema.Draft202012Validator(schema).validate(yaml.safe_load(open('lab.yml')))
print('valid')
"
```

## Python API

The CLI is the reference compiler. The Python API is a convenience wrapper
over the same pipeline:

```python
from labdata import LabDataConfig, assemble, export_to_yaml

config = LabDataConfig.from_yaml("lab.yaml")
data = assemble(config)

export_to_yaml(data, "lab.yml")

for pub in data.publications:
    authors = ", ".join(a.name for a in pub.authors)
    print(f"{pub.title} ({authors})")
```

Public: the names exported from `labdata/__init__.py`. Everything else —
`labdata.parsers`, `labdata.loaders`, `labdata.resolver` — is private and may
change without a version bump.

## The demo renderer

[`site/`](site/) holds a Jekyll template that renders the Example Lab document,
and [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) publishes it
to GitHub Pages ([what it looks like](https://siddhss5.github.io/labdata/)).
It is a **downstream consumer kept here as a worked example**,
not part of what labdata promises; it moves to its own repository in
[#57](https://github.com/siddhss5/labdata/issues/57).

`scripts/generate_site_config.py` reads an optional `site:` section of
`lab.yaml` (`url` and `baseurl`) and writes it, with the lab name and
description, into `site/_config.generated.yml`. labdata itself ignores that
section. To build the demo locally:

```bash
labdata --config examples/demo/lab.yaml --output site/_data/lab.yml
python scripts/generate_site_config.py examples/demo/lab.yaml site/_config.generated.yml
cd site && bundle install
bundle exec jekyll serve --config _config.yml,_config.generated.yml
```

## Dependencies

- **pybtex** — BibTeX parsing
- **pylatexenc** — LaTeX to Unicode text
- **pyyaml** — YAML I/O

No network calls. All processing is local and offline.

## License

MIT License. Copyright (c) 2024 Personal Robotics Laboratory, University of Washington.
