# sslabdata

sslabdata compiles BibTeX and a little YAML into one schema-specified document —
works, people, projects and the links between them — that any website, CV or
script can read.

Most academics already keep good BibTeX. What they do not have is that
bibliography as *data*: authors linked to the people in the group, papers
linked to the projects they belong to, names normalised, LaTeX resolved to
plain Unicode text. sslabdata does that one job and writes the result to a
single YAML or JSON file, specified by a published JSON Schema you can check
it against.

```bash
sslabdata --config lab.yaml --output lab.yml
```

- [`SPEC.md`](SPEC.md) — the normative contract: what the strings are, what
  order the lists are in, which fields are derived, when the version changes.
- [`schema/v4/output.schema.json`](schema/v4/output.schema.json) — the
  document's JSON Schema. Published versions are immutable and live at their
  own paths; [`schema/v3/`](schema/v3/output.schema.json) is still there.
- [`tests/COVERAGE.md`](tests/COVERAGE.md) — every input case sslabdata
  supports, and every case it does not, with the fixture and test for each.

## What sslabdata is not

**sslabdata is not a CMS and not a site generator.** It does not build a
website, own your pages or manage your content. News, openings, teaching
pages, press and galleries are prose with no shared structure to compile, and
they belong in your site repository. [`SPEC.md` §8](SPEC.md) gives the
evidence for that boundary and the destination for each content type it
leaves out.

sslabdata emits data. Rendering it is your renderer's job.

## Install

```bash
pip install git+https://github.com/siddhss5/sslabdata.git
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
collaborators_file: "data/collaborators.yaml"  # optional
```

Each `bib_files` entry's `name` is a name under `bib_dir`, and must not be an
absolute path: it is emitted as the work's `source.file`, so an absolute one
would put your directory layout in a document you share. sslabdata rejects it
rather than rewriting it.

Paths are relative to the directory you run `sslabdata` from.
[`examples/demo/lab.yaml`](examples/demo/lab.yaml) is a complete example,
built from the fictional Example Lab in [`examples/demo/`](examples/demo/).

Then compile it:

```bash
sslabdata --config lab.yaml --validate            # report counts and problems
sslabdata --config lab.yaml --unresolved          # list unmatched author names
sslabdata --config lab.yaml --output lab.yml      # write the document
sslabdata --config lab.yaml --format json --output lab.json
sslabdata --config lab.yaml --validate --strict   # fail on every problem
sslabdata --config lab.yaml --validate --format json   # problems as JSON
```

`--validate` exits `0` when it finds no errors and `1` when it does, or when
the run fails outright. An author who
matched nobody is reported but is not an error — most are external
collaborators. `--validate` does not check the output against the JSON
Schema; it checks the configuration, the people and projects files and every
entry, and reports every problem under a stable code that
[`SPEC.md`](SPEC.md) registers, with its class.

`--strict` combines with any mode and turns every coded problem into an
error, except the ones about authors who matched no lab member (sslabdata
cannot yet tell an outside co-author from a misspelt member) and redefined
`@string` macros; any error exits `1`, and an export then writes nothing.
With `--validate` or `--unresolved`, `--format json` prints the problems as
one JSON array of `{code, severity, file, key, field, message}` on standard
output; with `--output`, `--format` is still the document's format. The exit
codes and that JSON shape are part of the contract; [`SPEC.md` §1](SPEC.md)
lists them, along with the precedence rule when you pass more than one mode.

## Inputs

### BibTeX (required)

Standard `.bib` files. These are the fields sslabdata interprets. A field not
listed here is carried through in `bibtex` but is not interpreted and affects
nothing else:

| Field | Becomes |
|-------|---------|
| `title` | `title`, LaTeX converted to plain Unicode text; `$...$` math kept as TeX |
| `author` | `authors`, one authorship per name, each with its `position`, a readable `name`, its `given` / `von` / `family` / `suffix` parts (or `literal` for a brace-protected name), `equal_contribution`, a `resolution` record, and exactly one of `person_id` and `collaborator_key` |
| `editor` | `editors`, read by the same machinery. Editing a volume is not an authorship: editors count towards nobody's `work_count` and produce no collaborator |
| `year` | `year`, and the sort order of the works list. `null`, with a diagnostic, when the entry has none |
| `journal` / `booktitle` / `school` / `institution` | `venue`, as `{kind, name}` — the one place sslabdata normalises across entry types. `null` when the entry names no container |
| `volume`, `number`, `pages`, `series`, `edition`, `publisher`, `address`, `organization`, `chapter`, `month`, `howpublished`, `type` | Properties of the work, under BibTeX's own names and with BibTeX's own meanings |
| `doi`, `isbn`, `issn`, `eprint` + `archivePrefix` | `identifiers`, an open map from scheme to a list of identifiers, plus the links built from them. An `eprint`'s scheme is the repository `archivePrefix` named, lower-cased, so that field needs no property of its own — and an `eprint` in a repository other than arXiv gets no arXiv link |
| `abstract` | `abstract` |
| `note` | `note` |
| `url` | A link of kind `video` when it points at YouTube or Vimeo, otherwise of kind `url` |
| `project` | `project_ids` (see below) |
| `crossref` | **An error.** Partial inheritance dropped every author a child entry did not write itself, silently; sslabdata rejects the field instead, names the file, the key and the parent, and fails the run. Write the fields out on the entry itself |

The entry is also re-serialized into a `bibtex` field, so fields sslabdata does
not interpret are still carried. It is a re-serialization, not a copy: field
order, braces and quoting are normalised and `@string` macros are expanded.
That every field name in the demo's input reaches a first-class property is
measured, not asserted: `examples/consumers/bibtex_roundtrip.py` re-emits each
entry from the document alone and the test behind it fails naming any field
that reached none.

### The `project` tag

sslabdata adds one custom BibTeX field, `project`, to link a paper to a research
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
back-links the works tagged with it, and the people who wrote them.

### People (optional, `data/people.yaml`)

A list of lab members and alumni. `aliases` tells sslabdata how to match BibTeX
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

`id` and `name` are required. `role` is any non-empty string, so any lab's
roles fit; `status` is `current` (the default) or `alumni`.

### External co-authors (optional, `data/collaborators.yaml`)

A list of co-authors outside the lab whose spellings you want grouped
together. It only decides which authorships share one `collaborators`
entry; it never makes anyone a lab member and never produces a `person_id`:

```yaml
- name: "Priya Patel"
  aliases: ["P. Patel"]
```

`Patel, Priya` and `Patel, P.` are then one collaborator, with
`grouped_by: declared`. A different `Patel, Pradeep` is not joined, because
nothing declares him. A name or alias that a lab member already declares is
reported under `RESOLVE-COLLABORATOR-ALIAS-IS-MEMBER` and left to the member.

### Projects (optional, `data/projects.yaml`)

```yaml
- id: "homebot"
  title: "Household Manipulation"
  description: "Robots that tidy up, fetch things and put them away in real homes."
  website: "https://example.org/projects/homebot"
  status: "active"
```

`id` and `title` are required; `status` is `active` (the default) or
`completed`.

## How author matching works

sslabdata matches the **structured parts** of each BibTeX author name — given,
von, family, suffix — to lab members, in this order:

1. **The full name**, against each person's `name` and any alias written in
   full, after normalising both sides: lowercase, strip accents, remove
   periods, strip `<sup>…</sup>` tags, collapse whitespace. Other
   punctuation — apostrophes, hyphens, a `*` that is not an equal-contribution
   marker — is kept, so `O'Neill` and `Zhang-Smith` must match on those
   characters, and `Davis{*}` is not `Davis`. `Kim, Alan`
   finds `Alan Kim` even when he declares no aliases.
2. **A declared alias, only when the name is itself abbreviated** — when some
   part of the given name is an initial, as in `Kim, A.` or `Brown, Bob A.`.
   It links only when exactly one person declares that abbreviation *and* no
   other member's name could be it too. A full name is never abbreviated to
   find a match, so `Kim, Alan` does not resolve to another Kim who declared
   `A. Kim`.

Nothing is guessed. A name that fits more than one person — `Kim, A.` when
the lab has Alex Kim and Alan Kim — gets no `person_id`, has
`resolution.status: ambiguous`, and is reported under
`RESOLVE-AMBIGUOUS-NAME`. A near miss — `Davis, Dave M.` beside `Dave Davis`,
or an initial nobody declared — is never linked, and is reported under
`RESOLVE-SUGGESTION` with the ids it might be. Both name the file, the entry
key and the author position, and both are warnings: `--validate` lists them
and still exits `0`. To resolve one, add the spelling to that person's
`aliases`.

A name that matches nobody keeps `person_id: null` and its authorship
references a `collaborators` entry instead, by `collaborator_key`.
`sslabdata --config lab.yaml --unresolved` lists those names so you can add
aliases — or, if you have configured no `people_file`, tells you resolution
was never attempted.

**`collaborators` is a grouping over unresolved authorships, not a list of
humans.** Its `key` is a lookup key — a slug of the normalised name plus a
short digest — and explicitly not an assertion about a person: two people who
write their names identically are one key. That is why each entry also lists
the `authorships` it grouped, by `(work_id, position)`: a consumer that
distrusts the grouping can ignore it and work from the occurrences. The
grouping is keyed on the normalised full name, which over-splits — one person
written `Priya Patel` on two papers and `P. Patel` on a third is two keys
unless `collaborators_file` declares the alias — and sslabdata reports both
risks rather than leaving them silent: a key that spans more than one
spelling, and an initials-only key that could be any of several fuller ones.

## Reading the document

The output is one YAML or JSON file. Strings in it that are meant for display
— titles, abstracts, notes, names, project descriptions, each work's
`category` — are plain Unicode text: not HTML, not Markdown, not escaped. They
are untrusted, and a title really may contain `<`, `&`, `"` or `*`, so
**escape them when you render them**. Math is the one intended markup
exception and stays delimited by `$…$`.

One string sits outside that rule: `bibtex` is a machine-oriented BibTeX
record that deliberately keeps its LaTeX — copy it, do not display it as
text. Identifiers and URLs are not display text either. sslabdata itself
generates no markup anywhere; where the document carries Markdown
punctuation, an author wrote it. [`SPEC.md` §2](SPEC.md) treats all of this
properly.

sslabdata *enforces* that rule only where it converts: the BibTeX prose fields
it reads. Strings you supply directly in YAML — names and roles in
`people.yaml`, titles and descriptions in `projects.yaml`, the `category` of
each `bib_files` entry, and everything under `lab` — are copied through
exactly as written and are never checked. Keeping them plain is on you.
[`SPEC.md` §2](SPEC.md) draws the line precisely.

Validate a document against the schema with any JSON Schema tool. sslabdata
does not do this for you, and does not depend on a validator — `jsonschema`
is a test-only dependency, so install it first:

```bash
pip install jsonschema
python -c "
import json, yaml, jsonschema
schema = json.load(open('schema/v4/output.schema.json'))
jsonschema.Draft202012Validator(schema).validate(yaml.safe_load(open('lab.yml')))
print('valid')
"
```

## Python API

The CLI is the reference compiler. The Python API is a convenience wrapper
over the same pipeline:

```python
from sslabdata import LabDataConfig, assemble, export_to_yaml

config = LabDataConfig.from_yaml("lab.yaml")
data = assemble(config)

export_to_yaml(data, "lab.yml")

for work in data.works:
    authors = ", ".join(a.name for a in work.authors)
    print(f"{work.title} ({authors})")
```

Public: the names exported from `sslabdata/__init__.py`. Everything else —
`sslabdata.parsers`, `sslabdata.loaders`, `sslabdata.resolver` — is private and may
change without a version bump.

## The demo renderer

[sslabdata-site](https://github.com/siddhss5/sslabdata-site) renders the Example
Lab document as a website ([what it looks like](https://siddhss5.github.io/sslabdata-site/)).
It is an **optional downstream consumer**, not part of sslabdata and not part of
what sslabdata promises; it installs sslabdata from a pinned tag or commit and keeps its own
copy of the demo. sslabdata ignores a `site:` section in `lab.yaml`, so a
renderer can keep its own settings there.

Before publishing a sslabdata release, build sslabdata-site against the candidate:
run its **Release gate** workflow with the candidate's git ref as
`sslabdata_ref`. It builds without deploying, and keeps the renderer's toolchain
out of this repository's CI.

## Dependencies

- **pybtex** — BibTeX parsing
- **pylatexenc** — LaTeX to Unicode text
- **pyyaml** — YAML I/O

No network calls. All processing is local and offline.

## License

MIT License. Copyright (c) 2024 Personal Robotics Laboratory, University of Washington.
