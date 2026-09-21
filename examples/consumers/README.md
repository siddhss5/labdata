# Consumer probes

**If a consumer probe cannot be written from the emitted document alone, that
is a schema bug, not a probe bug.**

That rule is why this directory exists. The demo site in
[labdata-site](https://github.com/siddhss5/labdata-site) is the only other
evidence that the emitted document is enough to build anything with, and it
is weak evidence: it grew up alongside the data and quietly
absorbed its quirks. These five probes are the falsification test. Each one is
a different kind of consumer, and each is written against the document and
nothing else, so a quirk the demo absorbed shows up here as a probe that
cannot be written.

They are **not** example applications, and they are not documentation of how
to build a site. Nobody should copy them. They are small and ugly on purpose.

## The probes

| Probe | Emits | Status |
|---|---|---|
| `plain_html.py` | one HTML page: works, people, collaborators, projects | passes |
| `cv_tex.py` | a LaTeX CV fragment, works grouped by year | passes |
| `csl_json.py` | a CSL-JSON export | passes |
| `graph.py` | a person / project / work edge list | passes, except one identity claim — see below |
| `bibtex_roundtrip.py` | one BibTeX entry per work, from structured properties | passes |

Each takes the document as its one argument and writes to standard output:

```bash
labdata --config examples/demo/lab.yaml --format json --output lab.json
python examples/consumers/plain_html.py lab.json > lab.html
python examples/consumers/cv_tex.py    lab.json > works.tex
python examples/consumers/csl_json.py  lab.json > lab.csl.json
python examples/consumers/graph.py     lab.json > graph.tsv
python examples/consumers/bibtex_roundtrip.py lab.json > works.bib
```

`tests/conformance/test_consumer_probes.py` runs all five against the demo
output in CI, the same way: as a subprocess handed a path.

Under `schema_version` 3 four of these probes could not produce correct
output, and their assertions about the missing properties sat under
`xfail(strict=True)` against the issue that owned each. `schema_version` 4
(#56) closed every one of those gaps but one, and the markers came off. The
arrangement they came off from is the one to keep when the next gap appears:
a marker covers **one claim** about what is missing rather than everything a
probe cannot do, and everything the probe already does — schema validity,
year grouping, edge endpoints, one entry per work — goes in a test that
passes, so a regression in it turns the suite red instead of being absorbed
by an expected `xfail`.

A strict `xfail` swallows *every* failure in its test, and an xfailed test
cannot help relying on some things that already work. The rule that covers
those is: **every prerequisite an xfailed test already satisfies is
independently enforced by a test that passes.** The one marker left reads the
graph's `authored` edges; the passing `test_graph_is_well_formed` asserts
that every one of them matches the document, and the passing
`test_identity_fixtures_are_present` asserts that the works it is about are
still in the demo, so nothing it leans on is checked only inside the marker.

**No probe test is xfailed.** The last one cited **#24** rather than #56,
because the property it asked for was #24's — see the identity table under
`graph.py` below — and #24 made it pass. A strict xfail citing an issue is a
promise that *that* issue makes it pass, so filing one against an issue that
will not is as much a defect as a weak assertion.

The tests match **per record**, rather than counting or searching the page
for a substring. A count passes with two works' author lists swapped, and a
substring search for a year is satisfied by a DOI that happens to contain it;
both are exactly the kind of regression a schema change can introduce. What
each test matches a record *by* differs, because the artifacts differ:

| Probe | Records matched by |
|---|---|
| `plain_html.py` | the `bib_id`, person id and project id the page carries as element ids — except collaborators, compared as a **multiset**, because a collaborator's `key` is a lookup key over grouped authorships and not the address of a person, so the page does not turn it into an element id |
| `csl_json.py` | the record's `id` |
| `cv_tex.py` | the entry's **title**, because a LaTeX fragment carries no ids; a duplicate title fails loudly rather than matching the wrong entry |
| `graph.py` | nothing — every `authored`, `part_of` and `member_of` edge is compared as a complete tuple. The identity tests match a contributor by **the exact set of works it authored**, and an authorship by the **position the document declares**, never by a node's label, so they survive a change to what the readable form of a name is. Each work set is pinned in both directions: "these two contributors differ" would be satisfied by one that had taken the other's work as well, which is the merge being tested for. They also select contributors by the `collaborator:` **namespace**, so a co-author arriving under `person:` — a semantic widening the schema rejects — satisfies none of them |
| `bibtex_roundtrip.py` | the entry's citation key. Field **names** are compared, never values: the LaTeX-to-Unicode conversion is deliberately one-way, so comparing values would assert something false |

## What a probe may read

- **The emitted document, and only the emitted document.** No
  `import labdata`, no `.bib` file, no `lab.yaml`, `people.yaml` or
  `projects.yaml`. The test module checks both statically: no probe imports
  `labdata`, no probe names an input file, and each probe opens exactly one
  file — the one on its command line.
- **Structured properties, never `work.bibtex`.** That record is an opaque
  re-serialization of the entry, for a consumer to copy into a reference
  manager. It is not a set of first-class properties, and it is not even a
  faithful copy of what the author wrote: `format_bibtex()` re-typesets the
  *parsed* entry, so field order, delimiters, whitespace and `@string` macros
  are all gone (SPEC.md §5). Every field of the entry is none the less
  visibly sitting in it, read or not, so a probe that reached in could be made
  to pass while proving nothing at all about the schema. The static check
  forbids that too.
- **Structured properties, never a pre-composed string taken apart.** A probe
  renders markup it was handed; it does not parse fields back out of a string
  the compiler composed. `schema_version` 4 leaves nothing composed to take
  apart — `venue` is `{kind, name}` and the bibliographic parts are
  properties of the work — but the rule is what keeps it that way.

Reading an author's name from the parts *is* allowed and the probes do it.
`given`, `von`, `family`, `suffix` and `literal` are on every authorship and
every editor, and preserve whatever the input supplied — which is a full
given name for most of the demo, and an initial in ten of its authorships,
across eight distinct abbreviated names, whose entry wrote `Brown, B.` rather
than `Brown, Bob` (`brown2024blend`, `ingram2019toolkit`,
`ingram2021affordances`, `jones2021timing`).

So the parts are not a promise of a full name; they are a promise of the
input's name. That is the right guarantee and no property is missing: where
the input wrote an initial, an initial is the correct value, and a CSL record
carrying `given: "P."` is correct CSL. The probes therefore reproduce the
parts as they find them — neither abbreviating a full name nor inventing one
from an initial — and the tests assert that over every authorship rather than
spot-checking one. `name` is those same parts joined in reading order, so it
is a readable form of the input name rather than a citation form; the
description of `given` no longer claims it is unabbreviated (#68).

### Escaping

`SPEC.md` §2 says text in the document is untrusted — a title may contain `<`,
`&`, `"`, `*` or `$`, and `Informed RRT*` is a real one — and that escaping is
the renderer's job. Running `plain_html.py` on the demo establishes almost
nothing about escaping, because of what the demo contains. Outside the
`bibtex` record, which no probe reads, its **only** HTML-sensitive character
is the apostrophe — in two abstracts and one project description — and an
apostrophe in element text is harmless. No `<`, `>`, `&` or double quote
appears in any field the page renders, and no demo value reaches an attribute
carrying a character that could break out of one. So #55 names this probe as
the renderer in this repository where escaping can be asserted, and the
assertion needs values the demo does not supply. (#55 mentions
siddhss5/labdata#36 alongside this; that issue is about testing a rendered
site — snapshots, internal links, accessibility — and says nothing about
escaping, so nothing here depends on it.)

`test_plain_html_escapes_hostile_text` therefore puts hostile values into a
copy of the document — markup and quotes in a title, a person's name and the
lab name, a `"`-bearing URL that reaches an `href`, and a `"`-bearing id
reaching the `id` attribute this page gives each entity — and runs the
**unmodified** probe on that. It then parses the output and asserts the markup
never became markup: no `script` or `b` element, the hostile text coming back
out of the parser as the characters that went in, no `on*` attribute anywhere,
and the URL and each id arriving as one intact attribute value, with two ids
that differ only by an escape (`x&y` and `x&amp;y`) staying distinct.

## What the four failing probes were blocked on, and what unblocked them

Recorded because it is the evidence #56 was built from, and because a reader
should be able to check that each gap is actually closed rather than
described as closed. Verified against the demo output.

- **`cv_tex.py`** — `pages`, `volume` and `number` reached no property, and
  `venue` was a composed Markdown string rather than a venue name plus its
  parts, so the entry had no journal name to put in `\emph{}`, no `4(2)` and
  no `112--131`. All four are properties now: `venue.name` and the flat
  `volume`, `number` and `pages`.
- **`csl_json.py`** — the same three, plus the DOI, which reached the
  document only as a link. CSL wants an identifier in `DOI`, and a link is
  not invertible back into one: a `doi` written as a URL in the input was
  passed through unchanged, so there was no prefix a consumer could reliably
  strip. `identifiers` now carries the DOI as an identifier, with the
  resolver prefix taken off by the compiler, which knows what it stripped.
- **`graph.py`** — a `collaborators` entry carried no key of its own, so
  there was nothing to make a node out of, and no field of an authorship
  could point at one if it had. `person_id` was not that field: the schema
  defines it as "the id of the matching person in `people.yaml`", which a
  collaborator by definition is not. What was left was the display name,
  which SPEC.md §5 states is *not* an identity, so keying a node on it would
  merge people the document itself warns are distinct.

  The document now carries the reference the probe consumes. An authorship
  references exactly one contributor: `person_id`, the id of a person in
  `people.yaml`, or `collaborator_key`, the grouping key for an authorship
  that matched nobody. `person_id` is never widened to reach a collaborator,
  and a `collaborators` entry is read for a `key`, not an `id`, because a
  name-derived value is a lookup key and not a claim about a human. The two
  live in **separate namespaces**: a lab member is `person:<id>` and a group
  is `collaborator:<key>`, so an unresolved string is never labelled a
  person.

  An `authored` edge also carries a fourth column, the authorship's position
  in its work's author list, because a work lists authorships rather than
  contributors. Without it two people written alike on one work are one line
  of output whatever the document says. The document declares `position`, so
  the column is now the document's answer rather than the probe's fallback to
  a list index.

  ### The three identity questions, and the two issues that own them

  | Asked of the probe | Owner | Status |
  |---|---|---|
  | One external co-author on three works, written `Patel, Priya` twice and `Patel, P.` once, is **one** contributor holding exactly those three works | **#24** | Passes. #56 keys the grouping on the *normalised full name*, under which `priya patel` and `p patel` are two keys by construction. #24 adds `collaborators_file`, and the demo declares `P. Patel` as an alias of `Priya Patel`, so the three authorships are one `declared` grouping while `Pradeep Patel`, whom nothing declares, stays apart |
  | `Patel, Pradeep` on a fourth work is a **different** contributor, holding exactly that work and none of the other three | #56 | Passes. Under the normalised full-name key `pradeep patel` is a third key, where the abbreviated `p patel` merged all four authorships into one entry with one count |
  | The two `Lee, Lin` co-authors of `nolan2020stairs` stay **two authorships**, at the two positions that work's author list gives them | #56 | Passes. Not as two contributors: any grouping by name puts them together, and #56's key is a grouping by name. What survives the grouping is the occurrence, addressed by `(work.bib_id, author.position)` — which is what lets a consumer that distrusts the grouping work from occurrences instead |

- **`bibtex_roundtrip.py`** — nothing structural blocked the *entry*; what
  was missing was most of what goes in it. Re-emitting from first-class
  properties yielded `author`, `title`, `year`, `abstract`, `note` and `url`,
  and every one of the demo's 19 entries lost at least one field. Over the
  whole demo, 21 distinct field names reached no property:

  ```
  address, archiveprefix, booktitle, chapter, doi, edition, editor, eprint,
  howpublished, institution, isbn, issn, journal, month, number,
  organization, pages, publisher, school, series, volume
  ```

  They failed in three distinct ways, which is why the list mattered more
  than the count, and each way has its own fix. `pages`, `volume`, `number`,
  `publisher`, `address`, `series`, `edition`, `chapter`, `month`,
  `organization` and `howpublished` were read by nothing; they are properties
  of the work now. `editor` was read by nothing; it is parsed into `editors`.
  `journal`, `booktitle`, `school` and `institution` were fused into the
  composed `venue` string, or dropped outright for the entry types
  `format_venue()` had no rule for; they are `venue.name`, and the venue is
  built from whichever of them the entry wrote rather than from the entry
  type. `doi`, `eprint`, `isbn` and `issn` were either turned into links that
  could not be inverted or read by nothing; they are `identifiers`, and
  `archiveprefix` is the *scheme* of the `eprint` identifier, which is
  exactly what naming the repository does, so it needs no property of its
  own.

  The probe re-emits `project` nowhere, and that one field is the whole
  ignore set of its test, named there on its own with its reason: it is
  labdata's own tag field rather than a bibliographic one, and it does reach
  the document, as `project_ids`.

  Each field is looked for in **every** place it could sit — a flat property,
  the structured `venue`, the `editors` list, the `identifiers` map from
  scheme to identifiers, the `links` map from kind to link records — because
  a probe that looked in one place could report a field lost that had simply
  moved. One of those lookups carries a **provenance rule**: a link counts as
  evidence that the entry's own `url` survived only when the document says
  its `origin` is `input`. A link the lab added by enrichment, from a
  sidecar, or derived for itself says nothing about the input field, and
  letting one stand in for it would make this probe hide a loss — the one
  thing it must never do. A record that states no origin does not count
  either: the question is what the document *says*, and silence is not an
  answer. Identifiers carry no origin, so there is nothing to check there and
  nothing is invented.

Note that CSL-JSON schema validation was never what failed in `csl_json.py`.
Almost every CSL field is optional, so a record with no `page`, `volume`,
`issue` or `container-title` is still schema-valid, and the old export was.
The schema check therefore lives in a test that passes, where a regression in
it turns CI red; what sat under `xfail` was the separate assertion that the
probe can map a journal article to a complete reference.

## Adding a probe

Drop it in this directory and add it to `PROBE_TESTS` in
`tests/conformance/test_consumer_probes.py`, mapped to the tests that check
what it emits. `test_every_probe_is_exercised` fails if you do the first
without the second, so a probe cannot sit here and never run — and it also
fails unless one of the tests you named actually subscripts
`probe_output["<your probe>.py"]` — parsed, so a mention in a comment or a
docstring does not count — so a probe cannot be listed
against tests that never read what it wrote.

If your probe cannot be written, that is the finding. Leave the probe emitting
the best artifact it can and put the correctness assertions in the tests. Every
assertion the probe already satisfies goes in a test that passes; give the
missing properties a test of their own marked
`xfail(strict=True, reason="#N")` whose marker names them. Match per record on
an id the document supplies rather than counting or searching for a substring,
or the assertion will establish less than its wording. Do not weaken the probe
until it passes: a probe edited to assert its own incompleteness proves
nothing, and `strict=True` makes the marker fall over as soon as the property
lands.
