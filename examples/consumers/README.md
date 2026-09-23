# Consumer probes

**If a consumer probe cannot be written from the emitted document alone, that
is a schema bug, not a probe bug.**

Each probe here is a different kind of consumer, written against the document
and nothing else, so a property the document does not carry shows up as a
probe that cannot be written. They are **not** example applications, and they
are not documentation of how to build a site. They are small and ugly on
purpose. The HTML evidence is the renderer in
[sslabdata-site](https://github.com/siddhss5/sslabdata-site).

## The probes

| Probe | Emits |
|---|---|
| `cv_tex.py` | a LaTeX CV fragment, works grouped by year |
| `csl_json.py` | a CSL-JSON export |
| `graph.py` | a person / project / work edge list |

Each takes the document as its one argument and writes to standard output:

```bash
sslabdata --config examples/demo/lab.yaml --format json --output lab.json
python examples/consumers/cv_tex.py    lab.json > works.tex
python examples/consumers/csl_json.py  lab.json > lab.csl.json
python examples/consumers/graph.py     lab.json > graph.tsv
```

`tests/conformance/test_consumer_probes.py` runs all three against the demo
output in CI, the same way: as a subprocess handed a path. The tests match
**per record** rather than counting, because a count passes with two works'
author lists swapped:

| Probe | Checked | Records matched by |
|---|---|---|
| `cv_tex.py` | year grouping, authors from the name parts, and a complete citation for one article | the entry's **title**, because a LaTeX fragment carries no ids |
| `csl_json.py` | validity against the vendored CSL-JSON schema, the core fields of every record, and a complete citation for one article | the record's `id` |
| `graph.py` | every node and every `authored`, `part_of` and `member_of` edge, and the identity questions below | complete edge tuples; a contributor by **the exact set of works it authored**, never by its label |

The same module also checks, without a probe, that every field of every entry
in the demo's input reaches the property the document gives it
(`test_demo_field_reaches_the_document`).

## What a probe may read

- **The emitted document, and only the emitted document** — not the
  compiler, and not the `.bib` or YAML inputs.
- **Structured properties, never `work.bibtex`.** That record is an opaque
  re-serialization of the entry for a reference manager (SPEC.md §5); a probe
  that reached into it could pass while proving nothing about the schema.
- **Structured properties, never a pre-composed string taken apart.**

Reading an author's name from the parts is allowed. `given`, `von`, `family`,
`suffix` and `literal` preserve whatever the input supplied, which is an
initial where the entry wrote one, so the probes reproduce the parts as they
find them and the tests assert that over every authorship.

## The identity questions `graph.py` answers

A lab member is `person:<id>` and a co-author who matched nobody is
`collaborator:<key>`: two namespaces, so an unresolved string is never
labelled a person. An `authored` edge carries the authorship's `position`,
because a work lists authorships rather than contributors.

| Asked of the probe | Answer |
|---|---|
| `Patel, Priya` on two works and `Patel, P.` on a third are **one** contributor holding exactly those three | One `collaborator:` node, because the demo's `collaborators_file` declares `P. Patel` as an alias |
| `Patel, Pradeep` on a fourth work is a **different** contributor holding exactly that work | A separate node: the grouping key is the normalised full name |
| The two `Lee, Lin` co-authors of `nolan2020stairs` stay **two authorships** | One grouping with two `authored` edges at the two positions the document declares |

## Adding a probe

Drop it in this directory and add it to `probe_output` in
`tests/conformance/test_consumer_probes.py` with a test that reads what it
wrote. If it cannot be written, that is the finding: leave it emitting the
best artifact it can, and mark the assertion on the missing property
`xfail(strict=True, reason="#N")` in a test of its own.
