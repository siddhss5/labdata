# Consumer probes

**If a consumer probe cannot be written from the emitted document alone, that
is a schema bug, not a probe bug.**

That rule is why this directory exists. The bundled Jekyll site in `site/` is
the only other evidence that the emitted document is enough to build anything
with, and it is weak evidence: it grew up alongside the data and quietly
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
| `cv_tex.py` | a LaTeX CV fragment, publications grouped by year | **fails** — see below |
| `csl_json.py` | a CSL-JSON export | **fails** — see below |
| `graph.py` | a person / project / work edge list | **fails** — see below |
| `bibtex_roundtrip.py` | one BibTeX entry per work, from structured properties | **fails** — see below |

Each takes the document as its one argument and writes to standard output:

```bash
labdata --config examples/demo/lab.yaml --format json --output lab.json
python examples/consumers/plain_html.py lab.json > lab.html
python examples/consumers/cv_tex.py    lab.json > publications.tex
python examples/consumers/csl_json.py  lab.json > lab.csl.json
python examples/consumers/graph.py     lab.json > graph.tsv
python examples/consumers/bibtex_roundtrip.py lab.json > works.bib
```

`tests/conformance/test_consumer_probes.py` runs all five against the demo
output in CI, the same way: as a subprocess handed a path.

Each **failing** probe's obligations are split by kind rather than gathered
into one test, and a marker covers one claim about what is missing rather
than everything a probe cannot do — a single claim may name several
properties, as the field-loss one does. The assertions
naming the missing properties carry `xfail(strict=True)` against the issue that owns
the missing property -- #56 for all but one, which is #24's, for the reason
the identity paragraph under `graph.py` gives -- and
everything the probe already does — schema validity, year grouping, edge
endpoints, one entry per work — goes in a test that passes, so a regression in
it turns the suite red instead of being absorbed by the expected `#56` xfail.

A strict `xfail` swallows *every* failure in its test, and an xfailed test
cannot help relying on some things that already work: the CV one looks up a
publication by id, then that publication's one `\item` by title, and both
lookups assert.
The rule that covers those is: **every prerequisite an xfailed test already
satisfies is independently enforced by a test that passes.** Here the passing
CV test calls the same `tex_entry()` for every publication, and the passing
HTML and graph tests both fail on a duplicated id, so nothing the xfailed test
leans on is checked only inside the marker.

Seven probe tests are xfailed. Six cite #56 and turn into passes there; the
seventh cites **#24**, because the property it asks for is #24's and not
#56's — see the identity paragraph under `graph.py` below. A strict xfail
citing an issue is a promise that *that* issue makes it pass, so filing one
against an issue that will not is as much a defect as a weak assertion.

The passing tests match **per record**, rather than counting or searching the
page for a substring. A count passes with two works' author lists swapped, and
a substring search for a year is satisfied by a DOI that happens to contain
it; both are exactly the kind of regression #56 could introduce. What each
test matches a record *by* differs, because the artifacts differ:

| Probe | Records matched by |
|---|---|
| `plain_html.py` | the `bib_id`, person id and project id the page carries as element ids — except collaborators, compared as a **multiset**, because the document gives them no id at all, which is the gap `graph.py` fails on showing up a second time |
| `csl_json.py` | the record's `id`, against the fields `schema_version` 3 can supply |
| `cv_tex.py` | the entry's **title**, because a LaTeX fragment carries no ids; a duplicate title fails loudly rather than matching the wrong entry |
| `graph.py` | nothing — every `authored`, `part_of` and `member_of` edge is compared as a complete tuple. The identity tests match a contributor by **the exact set of works it authored**, and an authorship by the **position the document declares**, never by a node's label, so they survive #56 changing what the display form of a name is. Each work set is pinned in both directions: "these two contributors differ" would be satisfied by one that had taken the other's work as well, which is the merge being tested for. They also select contributors by the `collaborator:` **namespace**, so a co-author arriving under `person:` — the semantic widening #56 rejects — satisfies none of them |
| `bibtex_roundtrip.py` | the entry's citation key. Field **names** are compared, never values: the LaTeX-to-Unicode conversion is deliberately one-way, so comparing values would assert something false |

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
the demo, and an initial in ten of its authorships, across eight distinct
abbreviated names, whose entry wrote `Brown, B.` rather than `Brown, Bob`
(`brown2024blend`, `ingram2019toolkit`, `ingram2021affordances`,
`jones2021timing`).

So the parts are not a promise of a full name; they are a promise of the
input's name. That is the right guarantee and no property is missing: where
the input wrote an initial, an initial is the correct value, and a CSL record
carrying `given: "P."` is correct CSL. The probes therefore reproduce the
parts as they find them — neither abbreviating a full name nor inventing one
from an initial — and the tests assert that over every authorship rather than
spot-checking one. (The published schema describes `given` as
"unabbreviated", which those eight names contradict; that wording is #68,
and it is a description to correct, not data to change.)

### Escaping

`SPEC.md` §2 says text in the document is untrusted — a title may contain `<`,
`&`, `"`, `*` or `$`, and `Informed RRT*` is a real one — and that escaping is
the renderer's job. Running `plain_html.py` on the demo establishes almost
nothing about escaping, because of what the demo contains. Outside the
`bibtex` record, which no probe reads, its **only** HTML-sensitive character
is the apostrophe — in two abstracts and one project description — and an
apostrophe in element text is harmless. No `<`, `>`, `&` or double quote
appears in any field the page renders, and no demo value reaches an attribute
carrying a character that could break out of one. Its venues are full of `*`,
but `*` is not HTML-sensitive: it is the Markdown emphasis the page
deliberately renders. So #55 names this probe as the renderer we own where
escaping can be asserted, and the assertion needs values the demo does not
supply. (#55 mentions #36 alongside this; #36 is about testing the rendered
Jekyll site — snapshots, internal links, accessibility — and says nothing
about escaping, so nothing here depends on it.)

`test_plain_html_escapes_hostile_text` therefore puts hostile values into a
copy of the document — markup and quotes in a title, a person's name and the
lab name, a `"`-bearing URL that reaches an `href`, and a `"`-bearing id
reaching the `id` attribute this page gives each entity — and runs the
**unmodified** probe on that. It then parses the output and asserts the markup
never became markup: no `script` or `b` element, the hostile text coming back
out of the parser as the characters that went in, no `on*` attribute anywhere,
and the URL and each id arriving as one intact attribute value, with two ids
that differ only by an escape (`x&y` and `x&amp;y`) staying distinct.

## What blocks the four failing probes

Verified against the demo output. The first two are shown by the record
`brown2025tidy`; the third by the eleven authorships the demo cannot resolve,
none of which is on that record; the fourth by every entry in the demo,
including that one:

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
- **`graph.py`** — a `collaborators` entry carries no key of its own, so
  there is nothing to make a node out of; and no field of an authorship could
  point at one if it did. `author.person_id` is not that field: the schema defines it
  at `/$defs/author/properties/person_id` as "the id of the matching person in
  `people.yaml`", which a collaborator by definition is not, and for these
  authors it is `null`. What is left is the display name, which SPEC.md §5
  states is *not* an identity — three different people who all write as
  `J. Smith` are one entry — so keying a node on it would merge people the
  document itself warns are distinct. The demo's eleven unresolved
  authorships, grouped today into seven entries, are therefore neither nodes
  nor edge endpoints.

  The probe consumes the reference #56 settles on. An authorship references
  exactly one contributor: `person_id`, the id of a person in `people.yaml`,
  or `collaborator_key`, the grouping key for an authorship that matched
  nobody. `person_id` is never widened to reach a collaborator — that is the
  semantic widening #56 rejects — and a `collaborators` entry is read for a
  `key`, not an `id`, because a name-derived value is a lookup key and not a
  claim about a human. The two live in **separate namespaces**: a lab member
  is `person:<id>` and a group is `collaborator:<key>`, so an unresolved
  string is never labelled a person. The person side works today; it is the
  collaborator side that is empty, since no entry carries a `key` and no
  authorship carries a `collaborator_key`.

  An `authored` edge also carries a fourth column, the authorship's position
  in its work's author list, because a work lists authorships rather than
  contributors. Without it two people written alike on one work are one line
  of output whatever the document says.

  ### The three identity questions, and the two issues that own them

  | Asked of the probe | Owner | Why |
  |---|---|---|
  | One external co-author on three works, written `Patel, Priya` twice and `Patel, P.` once, is **one** contributor holding exactly those three works | **#24** | #56 keys the grouping on the *normalised full name* and states that the policy is #24's and that this key over-splits — "24% of demo names appear as both `A. Adams` and `Alice Adams`". `priya patel` and `p patel` are two keys under it, by construction. Joining two spellings of one external person needs #24's full-name grouping *plus* the aliases it gives external collaborators. Filing this against #56 would leave #56 unable to remove the marker |
  | `Patel, Pradeep` on a fourth work is a **different** contributor, holding exactly that work and none of the other three | #56 | Under the same normalised full-name key `pradeep patel` is a third key, where today's abbreviated `p patel` merges all four authorships into one entry with one count |
  | The two `Lee, Lin` co-authors of `nolan2020stairs` stay **two authorships**, at the two positions that work's author list gives them | #56 | Not two contributors: any grouping by name puts them together, and #56's key is a grouping by name. What #56 promises is that the authorship is the primary contributor record, addressed by `(work.bib_id, author.position)`, so the occurrence survives the grouping — which is what lets a consumer that distrusts the grouping work from occurrences instead |

  None of the three can be satisfied today, for the same reason: the only
  thing the document offers to key a co-author on is the display name.

- **`bibtex_roundtrip.py`** — nothing structural blocks the *entry*; what is
  missing is most of what goes in it. Re-emitting from first-class properties
  yields `author`, `title`, `year`, `abstract`, `note` and `url`, and every
  one of the demo's 19 entries loses at least one field. Over the whole demo,
  21 distinct field names do not reach a property:

  ```
  address, archiveprefix, booktitle, chapter, doi, edition, editor, eprint,
  howpublished, institution, isbn, issn, journal, month, number,
  organization, pages, publisher, school, series, volume
  ```

  They fail in three distinct ways, which is why the list matters more than
  the count. `pages`, `volume`, `number`, `publisher`, `address`, `series`,
  `edition`, `editor`, `chapter`, `month`, `organization`, `isbn`, `issn` and
  `howpublished` are read by nothing and emitted nowhere. `journal`,
  `booktitle`, `school` and `institution` are read, and then fused into the
  composed `venue` string — or, for the four entry types `format_venue()` has
  no rule for, dropped outright. `doi` and `eprint` are read and turned into
  links that cannot be inverted back into the identifiers they came from, and
  `archiveprefix` is read only to decide and then discarded.

  The probe re-emits `project` nowhere, and that one field is the whole ignore
  set of its test, named there on its own with its reason: it is labdata's own
  tag field rather than a bibliographic one, and it does reach the document,
  as `project_ids`.

  Each field is looked for in **every** place it could sit — a flat property,
  a structured `venue`, an `editors` list, an `identifiers` map from scheme
  to identifiers, a `links` map from kind to link records — because a probe
  that looked in one place could report a field lost that had simply moved.
  One of those lookups carries a **provenance rule**: a link counts as
  evidence that the entry's own `url` survived only when the document says
  its `origin` is `input`. A link the lab added by enrichment, from a
  sidecar, or derived for itself says nothing about the input field, and
  letting one stand in for it would make this probe hide a loss — the one
  thing it must never do. A record that states no origin does not count
  either: the question is what the document *says*, and silence is not an
  answer. Identifiers carry no origin, so there is nothing to check there and
  nothing is invented.

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
