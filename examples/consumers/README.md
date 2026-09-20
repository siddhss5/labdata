# Consumer probes

**If a consumer probe cannot be written from the emitted document alone, that
is a schema bug, not a probe bug.**

That rule is why this directory exists. The bundled Jekyll site in `site/` is
the only other evidence that the emitted document is enough to build anything
with, and it is weak evidence: it grew up alongside the data and quietly
absorbed its quirks. These four probes are the falsification test. Each one is
a different kind of consumer, and each is written against the document and
nothing else, so a quirk the demo absorbed shows up here as a probe that
cannot be written.

They are **not** example applications, and they are not documentation of how
to build a site. Nobody should copy them. They are small and ugly on purpose.

## The probes

| Probe | Emits | Status |
|---|---|---|
| `plain_html.py` | one HTML page: works, people, collaborators, projects | passes |
| `cv_tex.py` | a LaTeX CV fragment, publications grouped by year | **fails** — see below |
| `csl_json.py` | a CSL-JSON export | **fails** — see below |
| `graph.py` | a person / project / work edge list | **fails** — see below |

Each takes the document as its one argument and writes to standard output:

```bash
labdata --config examples/demo/lab.yaml --format json --output lab.json
python examples/consumers/plain_html.py lab.json > lab.html
python examples/consumers/cv_tex.py    lab.json > publications.tex
python examples/consumers/csl_json.py  lab.json > lab.csl.json
python examples/consumers/graph.py     lab.json > graph.tsv
```

`tests/conformance/test_consumer_probes.py` runs all four against the demo
output in CI, the same way: as a subprocess handed a path.

Each probe's obligations are split across two tests. What it *can* do today —
the CSL export validating against the published schema, the CV grouping by
year, the graph's edges resolving to declared nodes — is asserted in a test
that passes. Only the assertions naming the missing properties sit under
`xfail(strict=True, reason="#56")`, so each xfail fails for exactly the
property its marker names. Putting them together would neuter the first group:
a regression in, say, schema validity would surface as the already-expected
`#56` xfail and CI would stay green. The three xfails turn into passes in #56
and lose their markers there.

## What a probe may read

- **The emitted document, and only the emitted document.** No
  `import labdata`, no `.bib` file, no `lab.yaml`, `people.yaml` or
  `projects.yaml`. The test module checks both statically: no probe imports
  `labdata`, no probe names an input file, and each probe opens exactly one
  file — the one on its command line.
- **Structured properties, never `publication.bibtex`.** That record is an
  opaque re-serialization of the entry, for a consumer to copy into a
  reference manager. It is not a set of first-class properties, and it is not
  even a faithful copy of what the author wrote: `format_bibtex()` re-typesets
  the *parsed* entry, so field order, delimiters, whitespace and `@string`
  macros are all gone (SPEC.md §5). The fields are none the less visibly
  sitting in it — `pages = "112--131"` is in the record for `brown2025tidy`
  and is nowhere else in the document — and a probe that reached in could be
  made to pass while proving nothing at all about the schema. The static
  check forbids that too.
- **Structured properties, never a pre-composed string taken apart.**
  `venue` arrives as `*Transactions on Robot Learning*, 4(2), 2025` — one
  string with Markdown emphasis in it and the volume, issue and year fused
  in. A probe renders markup it was handed; it does not parse fields back out
  of a string the compiler composed.

Reading an author's name from the parts *is* allowed and the probes do it.
`author.name` is the document's display form and abbreviates the given name
**unconditionally** (`Brown, Bob` → `B. Brown`), so it is lossy as a source.
`given`, `von`, `family`, `suffix` and `literal` are on every author and
preserve whatever the input supplied — which is a full given name for most of
the demo, and an initial in nine of its authorships, across seven distinct
authors, whose entry wrote `Brown, B.` rather than `Brown, Bob`
(`brown2024blend`, `ingram2021affordances`, `jones2021timing`).

So the parts are not a promise of a full name; they are a promise of the
input's name. That is the right guarantee and no property is missing: where
the input wrote an initial, an initial is the correct value, and a CSL record
carrying `given: "P."` is correct CSL. The probes therefore reproduce the
parts as they find them — neither abbreviating a full name nor inventing one
from an initial — and the tests assert that over every authorship rather than
spot-checking one. (The published schema describes `given` as
"unabbreviated", which those seven authors contradict; that wording is #68,
and it is a description to correct, not data to change.)

## What blocks the three failing probes

Verified against the demo record `brown2025tidy`:

- **`cv_tex.py`** — `pages`, `volume` and `number` are not emitted as
  first-class properties, and `venue` is a composed Markdown string rather
  than a venue name plus its parts. So the entry has no journal name to put
  in `\emph{}`, no `4(2)` and no `112--131`.
- **`csl_json.py`** — the same three, plus the DOI, which reaches the
  document only as the link `doi_url`. CSL wants an identifier in `DOI`, and
  the link is not invertible back into one: a `doi` written as a URL in the
  input is passed through unchanged, so there is no prefix a consumer can
  reliably strip. The record therefore has no `container-title`, `volume`,
  `issue`, `page` or `DOI`.
- **`graph.py`** — a `collaborators` entry carries no `id`, so there is
  nothing to make a node out of; and no field of an authorship could point at
  one if it did. `author.person_id` is not that field: the schema defines it
  at `/$defs/author/properties/person_id` as "the id of the matching person in
  `people.yaml`", which a collaborator by definition is not, and for these
  authors it is `null`. What is left is the display name, which SPEC.md §5
  states is *not* an identity — three different people who all write as
  `J. Smith` are one entry — so keying a node on it would merge people the
  document itself warns are distinct. The five co-authors of the demo who are
  not lab members are therefore neither nodes nor edge endpoints.

  That is the gap as it stands. How #56 closes it — an `id` on the entry plus
  some authorship reference, a demotion of `collaborators` to an explicitly
  derived index, or something else — is #56's to decide, and this probe names
  no field for it to adopt.

Note that CSL-JSON schema validation is not what fails in `csl_json.py`.
Almost every CSL field is optional, so a record with no `page`, `volume`,
`issue` or `container-title` is still schema-valid, and today's export is. The
schema check therefore lives in the *passing* test, where a regression in it
turns CI red; what sits under `xfail` is the separate assertion that the probe
can map a journal article to a complete reference.

## Adding a probe

Drop it in this directory and add it to `PROBE_TESTS` in
`tests/conformance/test_consumer_probes.py`, mapped to the tests that check
what it emits. `test_every_probe_is_exercised` fails if you do the first
without the second, so a probe cannot sit here and never run.

If your probe cannot be written, that is the finding. Leave the probe emitting
the best artifact it can and put the correctness assertions in the tests. Keep
everything the probe *can* establish in a test that passes, and give the
missing properties a test of their own marked
`xfail(strict=True, reason="#N")` whose marker names them. Do not weaken the
probe until it passes: a probe edited to assert its own incompleteness proves
nothing, and `strict=True` makes the marker fall over as soon as the property
lands.
