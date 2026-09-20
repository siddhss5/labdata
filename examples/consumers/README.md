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
output in CI, the same way: as a subprocess handed a path. The three that
cannot produce correct output are `xfail(strict=True, reason="#56")` there,
and each marker names the property that blocks it. They turn green in #56 and
lose their markers there.

## What a probe may read

- **The emitted document, and only the emitted document.** No
  `import labdata`, no `.bib` file, no `lab.yaml`, `people.yaml` or
  `projects.yaml`. The test module checks both statically: no probe imports
  `labdata`, no probe names an input file, and each probe opens exactly one
  file — the one on its command line.
- **Structured properties, never `publication.bibtex`.** That record is a
  verbatim export for a consumer to copy into a reference manager. It is not
  a source of structured data, even though the fields are visibly sitting in
  it: `pages = "112--131"` is in the record for `brown2025tidy` and is
  nowhere else in the document. A probe that reached into it could be made to
  pass while proving nothing at all about the schema, so the static check
  forbids that too.
- **Structured properties, never a pre-composed string taken apart.**
  `venue` arrives as `*Transactions on Robot Learning*, 4(2), 2025` — one
  string with Markdown emphasis in it and the volume, issue and year fused
  in. A probe renders markup it was handed; it does not parse fields back out
  of a string the compiler composed.

Reconstructing an author's full name *is* allowed and the probes do it.
`author.name` is the document's display form and abbreviates given names to
initials (`A. Adams`), but `given`, `von`, `family`, `suffix` and `literal`
are on every author, so a full name is a join and not a gap.

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
- **`graph.py`** — a `collaborators` entry carries no `id`, and an
  unresolved author carries no reference to one: only `person_id: null` and a
  display name that SPEC.md section 5 states is *not* an identity, because
  three different people who all write as `J. Smith` become one entry. So the
  five co-authors of the demo who are not lab members cannot be nodes, and
  their five authorships cannot be edges.

Note that CSL-JSON schema validation is not what fails in `csl_json.py`.
Almost every CSL field is optional, so a record with no `page`, `volume`,
`issue` or `container-title` is still schema-valid. The schema check in the
test is a real check on the part the probe *can* produce; what fails is the
separate assertion that the probe can map a journal article to a complete
reference.

## Adding a probe

Drop it in this directory and add it to `PROBE_TESTS` in
`tests/conformance/test_consumer_probes.py` with the test that checks what it
emits. `test_every_probe_is_exercised` fails if you do the first without the
second, so a probe cannot sit here and never run.

If your probe cannot be written, that is the finding. Leave the probe
emitting the best artifact it can, put the correctness assertion in the test,
and mark that test `xfail(strict=True, reason="#N")` naming the missing
property. Do not weaken the probe until it passes: a probe edited to assert
its own incompleteness proves nothing, and `strict=True` makes the marker
fall over as soon as the property lands.
