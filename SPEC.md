# labdata specification

labdata is a compiler. It reads BibTeX and a little YAML and emits one
validated document describing a lab's works, people, projects and the links
between them.

This file states the parts of that contract a JSON Schema cannot express:
what the strings in the document are, what order the lists are in, what an
absent key means, which fields are computed, when the version changes, and
how a repeated `@string` macro resolves. `schema/output.schema.json` states
the rest.

Everything here is normative unless it carries a `Target` note. A `Target`
note marks a rule that the emitted document does **not** satisfy today, and
names the issue that will make it true. Until that issue lands, the rule is
the intent and the note is the fact.

- Applies to: `schema_version` 3, package version 2.0.0
  (`labdata/models.py:22`, `labdata/__init__.py:36`).

---

## 1. Contract hierarchy

**The emitted document plus its published schema is normative.** Everything
else in this repository — the CLI's internals, the Python classes, the
bundled Jekyll templates — exists to produce that document.

**When the emitted document and the schema disagree, the schema wins and the
code is the bug.** A consumer that validates against the published schema and
is rejected by labdata's own output has found a defect in labdata, never in
itself.

**The CLI is the reference compiler.** Its flags, its exit codes and its
diagnostic format are public API.

Flags (`labdata/cli.py:38-57`):

| Flag | Meaning |
|---|---|
| `--config PATH` | Required. The `lab.yaml` to compile. |
| `--format {yaml,json}` | Output format. Default `yaml`. |
| `--output PATH` | Write the document to `PATH`. |
| `--validate` | Report counts and problems, then exit without writing. |
| `--unresolved` | List author names that matched no person, then exit. |

Exactly one of `--output`, `--validate` or `--unresolved` is required
(`labdata/cli.py:62-63`).

Exit codes, as `labdata/cli.py` returns them today:

| Code | Meaning |
|---|---|
| `0` | Success. `--output` wrote the file; `--validate` found no errors. |
| `1` | Error. Configuration file missing (`cli.py:68-70`), configuration failed to load (`cli.py:71-73`), or `--validate` found unknown project ids (`cli.py:97-99`). |
| `2` | Usage error from the argument parser: a missing or unrecognised flag, or none of `--output` / `--validate` / `--unresolved`. |

Diagnostics go to standard error and are prefixed `Warning: `
(`labdata/parsers/bibtex.py:80-86`, `labdata/resolver.py:91`). Ordinary
reporting — counts, unresolved names, unknown project ids — goes to standard
output (`labdata/cli.py:82-94`).

> **Target (#26).** Three gaps in the above are real today.
> (a) An unhandled failure — a `.bib` file named in `lab.yaml` that does not
> exist, or a `year` field that is not a number — prints a Python traceback
> and also exits `1`, so `1` does not by itself distinguish a diagnosed error
> from a crash. Verified against `labdata/parsers/bibtex.py:193` and
> `labdata/parsers/bibtex.py:552`.
> (b) Diagnostic *text* is not yet stable: messages relayed from the BibTeX
> parser are passed through as that library phrased them
> (`labdata/parsers/bibtex.py:199-202`), and labdata's own messages do not
> consistently name the file, entry key and field. Consumers may depend on
> the stream and the `Warning: ` prefix, not on the wording.
> (c) `--validate` reports unresolved authors but does not count them as
> errors (`labdata/cli.py:86-90`), so a run with unresolved authors and no
> unknown projects exits `0`.

> **Target (#22).** `--unresolved` prints `All authors resolved.` when no
> `people_file` is configured, where nothing was ever attempted
> (`labdata/cli.py:106-107`).

**The Python API is convenience only.** Public: the names exported from
`labdata/__init__.py` (`labdata/__init__.py:18-35`) — `assemble`,
`AssemblyResult`, the models `LabData`, `Publication`, `Author`, `Person`,
`Project`, `Collaborator`, the config loader `LabDataConfig` with `BibFile`,
and the exporters `export_to_yaml` and `export_to_json`.

Private, and free to change without a version bump: `labdata.parsers.*`,
`labdata.loaders`, `labdata.resolver`, `labdata.cli`'s internals, and every
underscore-prefixed name. Importing them is unsupported. In particular, no
guarantee is made about which BibTeX or LaTeX library sits behind
`labdata.parsers` (`labdata/parsers/bibtex.py:9-11`).

The package version (`labdata/__init__.py:36`) and the document's
`schema_version` (`labdata/models.py:22`) are independent. Neither can be
derived from the other.

---

## 2. The text rule

**Every string in the emitted document is plain Unicode text.** Not HTML, not
Markdown, not escaped, not LaTeX. `labdata/parsers/latex.py` converts each
prose field from LaTeX to Unicode before it reaches the document, so
`C{\^o}t{\'e}` arrives as `Côté` and `\textbf{Best Paper}` arrives as `Best
Paper`.

Which fields are converted is listed in `labdata/parsers/bibtex.py:34-37`:
`title`, `abstract`, `note`, `journal`, `booktitle`, `school`, `institution`,
`type`, `series`, `publisher`, `address`, `organization`. Author name parts
are converted the same way (`labdata/parsers/bibtex.py:306-308`). Everything
else — `url`, `doi`, `eprint`, `project` — is data, not prose, and is carried
through unconverted.

**Text is untrusted.** A title may contain `<`, `&`, `"`, `*` or `$`, and
often does: `Informed RRT*` and `BIT*` are real paper titles. labdata does
not escape them and will not, because it does not know what they are being
escaped for. **Renderers are responsible for escaping** — for HTML bodies, for
HTML attributes, for shell arguments, for whatever they emit.

### Exceptions, and there are only three

1. **Math is left as TeX**, delimited by `$…$`, so that KaTeX or MathJax can
   typeset it (`labdata/parsers/latex.py:22`, `math_mode='verbatim'`). This
   is the one place a renderer may expect markup inside a text field.
2. **`publication.bibtex` is verbatim BibTeX**, not text. It is the entry as
   it was read, before crossref resolution and before LaTeX conversion,
   offered for readers to copy (`labdata/parsers/bibtex.py:410-420`).
3. **`lab` is copied through from `lab.yaml` unchanged**
   (`labdata/config.py:69`, `labdata/models.py:223-224`). No conversion is
   applied. Whatever the author wrote there is what consumers receive.

### Two honest caveats

- When a field cannot be converted, labdata warns and keeps the text as
  written with its braces removed (`labdata/parsers/bibtex.py:209-216`). Such
  a value may still contain LaTeX commands. This is a degraded case, not a
  second contract: the document is still declared plain text, and the warning
  is the signal that one field did not make it.
- `\href{url}{text}` is rewritten to `text (url)` before conversion
  (`labdata/parsers/latex.py:53-54`), because the converter cannot read it.
  Carrying link content into explicit fields is #27.

> **Target (#18).** `publication.venue` contains Markdown today. It is
> composed by `format_venue`, whose own docstring says "Uses Markdown (not
> HTML)" (`labdata/parsers/bibtex.py:436-474`): an article in journal `J`
> published in 2021 yields the string `*J*, 2021`. This is the single known
> violation of the text rule in the emitted document. #18 removes it; #56
> replaces `venue` with a structured container so there is nothing left to
> compose.

---

## 3. Ordering

Every list in the document is covered here. A list not described as ordered
is **unordered**, and a consumer that depends on its order is depending on an
accident.

| List | Order |
|---|---|
| `publications` | `year` **descending**. Ties keep *read order* (below). Verified: `labdata/parsers/bibtex.py:600`. |
| `publication.authors` | The order the `author` field wrote them. A terminal `and others` is BibTeX's "et al." and is dropped rather than emitted as an author (`labdata/parsers/bibtex.py:346-348`). |
| `publication.project_ids` | The order the `project` field wrote them, comma-separated, whitespace trimmed, empty entries dropped (`labdata/parsers/bibtex.py:514-520`). |
| `people` | The order of `people_file`. labdata does not sort people (`labdata/loaders.py:36-56`, `labdata/assembler.py:53`). |
| `projects` | The order of `projects_file`, likewise (`labdata/loaders.py:78-88`, `labdata/assembler.py:54`). |
| `person.publication_ids` | The order of the `publications` list, filtered to that person, first occurrence only (`labdata/resolver.py:198-204`). |
| `project.publication_ids` | The order of the `publications` list, filtered to that project, first occurrence only (`labdata/resolver.py:206-211`). |
| `project.people_ids` | Person id **ascending**, by Unicode code point (`labdata/resolver.py:226`). |
| `collaborators` | `last_year` **descending**, then `publication_count` **descending**, then `name` **ascending** by Unicode code point (`labdata/assembler.py:68-73`). |
| `lab` | Unordered. It is a YAML mapping copied through; consumers read it by key. |

**Read order** is the order in which entries were parsed: the files in the
order `bib_files` lists them in `lab.yaml`, and within each file, the order
the entries appear in the source (`labdata/parsers/bibtex.py:586-594`).
Because the publication sort is stable, read order is the tie-breaker for
publications of the same year, and it is a promise, not an accident.

**Ties and missing sort keys.**

- Two publications of the same year appear in read order. Two entries with
  the same year in the same file appear in source order.
- A publication with **no `year` field is treated as year `0`**
  (`labdata/parsers/bibtex.py:552`) and therefore sorts **last**.
- Two collaborators can only tie through all three keys if they share a
  name, and a name is their identity (`labdata/assembler.py:66`), so the
  order is total.
- Sorting by "Unicode code point" means `Z` sorts before `a`, and `Ö` sorts
  after `z`. No locale collation is applied.

> **Target (#56).** `year: 0` for an absent year is silent corruption: it is
> indistinguishable from a genuine year `0` and it places the entry in a
> position that means nothing. #56 makes `year` nullable and emits a
> diagnostic instead. When it does, the sort position of a publication with
> no year changes, which is itself a breaking change under §6.

**Key order within an object is not part of the contract.** The YAML export
writes keys in insertion order (`labdata/exporters.py:29-30`,
`sort_keys=False`) and the JSON export does the same, but both formats define
objects as unordered and consumers must treat them that way.

**YAML and JSON carry the same document.** `--format yaml` and
`--format json` serialize the identical structure
(`labdata/exporters.py:18-45`); neither is more authoritative.

---

## 4. Absent versus null

**One policy, for every entity type:**

> Every property the schema declares for an entity is **always present**. A
> value that does not apply, or was not supplied, is **`null`**. An absent key
> and a `null` key mean the same thing, and consumers must not read meaning
> into the difference.

A consumer may therefore treat `entry.get("photo")` and `entry["photo"]` as
equivalent, and must not use `"photo" in entry` as a test for whether a person
has a photo. The test is whether the value is `null`.

Two consequences worth stating outright:

- `author.person_id` is `null` when the name matched no person in
  `people_file`. That is an ordinary, expected value, not an error.
- An empty list is `[]`, never `null` and never absent. `project.people_ids`
  for a project with no publications is `[]`.

This rule is satisfied today by `Author`, `Publication` (except `bibtex`),
`Project` and `Collaborator`, all of which emit every declared key
(`labdata/models.py:48-59`, `:86-102`, `:192-202`, `:171-176`).

> **Target (#56).** Three deviations exist today, and each is a bug against
> the rule above rather than a second policy.
> (a) `Person.to_dict` emits only `id`, `name`, `role`, `status`, `website`
> and `publication_count` unconditionally, and **omits** `photo`, `email`,
> `co_advisor`, `start_year`, `publication_ids` and the alumni fields
> `end_year`, `degree`, `thesis_title` and `current_position` whenever their
> value is falsy (`labdata/models.py:142-160`). The alumni fields are
> additionally omitted for anyone whose `status` is not `alumni`
> (`labdata/models.py:150`). Verified: a person with no publications has no
> `publication_ids` key at all.
> (b) `publication.bibtex` is omitted when the entry could not be written
> back out as BibTeX (`labdata/models.py:103-104`).
> (c) Top-level `lab` is omitted when `lab.yaml` has no `lab` section
> (`labdata/models.py:223-224`).
> Fixing any of these changes the schema's `required` lists and the
> nullability of the affected properties, which is breaking under §6.
> #56 is the consolidated breaking change that normalises them.

Because the schema is closed (`additionalProperties: false` throughout,
`schema/output.schema.json:8`, `:49`, `:89`, `:112`, `:136`, `:150`), a
property that is not declared cannot appear at all. "Absent" above always
means a declared property with no value, never an undeclared one.

---

## 5. Input versus derived

**Input** fields come from the author's files and labdata carries them
through. **Derived** fields labdata computes. Derived fields are **read-only
outputs**: they must never be written back into `people.yaml`,
`projects.yaml` or a `.bib` file. Doing so makes the next compile read
labdata's own output as input, and a wrong derivation becomes permanent.

| Field | Origin |
|---|---|
| `schema_version` | Derived — a constant of the compiler (`labdata/models.py:22`). |
| `lab` | Input — the `lab` section of `lab.yaml`, copied unchanged (`labdata/config.py:69`). |
| `publication.bib_id`, `entry_type` | Input — the BibTeX citation key and entry type, lowercased (`labdata/parsers/bibtex.py:405-406`). |
| `publication.title`, `abstract`, `note` | Input — BibTeX fields, converted from LaTeX to text (§2). `note` additionally has trailing `.` and whitespace trimmed (`labdata/parsers/bibtex.py:477-482`). |
| `publication.year` | Input — the BibTeX `year`, as an integer; `0` when absent (`labdata/parsers/bibtex.py:552`). |
| `publication.category` | Input — the `category` of the `bib_files` entry the file was listed under, not anything in the `.bib` file (`labdata/config.py:59-61`, `labdata/parsers/bibtex.py:590`). |
| `publication.venue` | **Derived** — composed from `journal`, `booktitle`, `school`, `institution`, `type`, `number`, `volume`, `eprint` and `year` according to the entry type (`labdata/parsers/bibtex.py:436-474`). |
| `publication.url` | Input — the BibTeX `url`, but only when it is not a video URL (`labdata/parsers/bibtex.py:561`). |
| `publication.video_url` | **Derived** — the BibTeX `url`, when it names youtube.com, youtu.be or vimeo.com (`labdata/parsers/bibtex.py:485-490`). |
| `publication.doi_url` | **Derived** — `https://doi.org/` plus the `doi` field, unless `doi` is already a URL (`labdata/parsers/bibtex.py:493-501`). |
| `publication.arxiv_url` | **Derived** — `https://arxiv.org/abs/` plus the `eprint` field (`labdata/parsers/bibtex.py:504-511`). |
| `publication.pdf_url` | **Derived** — `pdf_base_url` plus the citation key plus `.pdf` (`labdata/parsers/bibtex.py:523-531`). |
| `publication.project_ids` | Input — the `project` field, split on commas (`labdata/parsers/bibtex.py:514-520`). |
| `publication.bibtex` | **Derived** — the entry serialized back out as BibTeX (`labdata/parsers/bibtex.py:410-420`). |
| `author.given`, `von`, `family`, `suffix`, `literal` | Input — the parts BibTeX split the name into, converted from LaTeX, with an equal-contribution marker removed (`labdata/parsers/bibtex.py:295-320`). |
| `author.name` | **Derived** — the display form, built from the parts by abbreviating given names to initials: `A. J. van Last, Jr.` (`labdata/parsers/bibtex.py:323-335`). |
| `author.person_id` | **Derived** — the resolver's match against `people_file` (`labdata/resolver.py:124-164`). |
| `author.equal_contribution` | **Derived** — whether the entry wrote a `*` marker on any part of the name (`labdata/parsers/bibtex.py:269-276`). |
| `person.*` except the two below | Input — the fields of `people_file` (`labdata/loaders.py:37-53`). `aliases` is read for matching and is **not** emitted. |
| `person.publication_ids`, `publication_count` | **Derived** — back-links, and their count (`labdata/resolver.py:198-215`). |
| `project.id`, `title`, `description`, `website`, `status` | Input — the fields of `projects_file` (`labdata/loaders.py:80-85`). |
| `project.publication_ids`, `people_ids` | **Derived** — back-links, and the people reached through them (`labdata/resolver.py:206-226`). |
| `collaborators` | **Derived, entirely** — one entry per distinct author display name that resolved to nobody, with the number of publications it appears on and the most recent year (`labdata/assembler.py:60-73`). |

Three properties of the derived fields consumers should know:

- **`pdf_url` is guessed, never verified.** For an `http`/`https` base it is
  constructed unconditionally and may 404; for a local path the file's
  existence is checked (`labdata/parsers/bibtex.py:529-531`). Verifying it is
  #20.
- **`collaborators` is keyed by display name, which is not an identity.**
  Three different people who all write as `J. Smith` are one entry. It is a
  derived index over unresolved authorships and must not be read as an
  authoritative list of humans. #56 relabels it accordingly.
- **Unknown project ids are kept, not dropped.** A `project_ids` entry naming
  no project in `projects_file` stays in the publication so the problem stays
  visible, and `--validate` reports it and exits `1`
  (`labdata/resolver.py:167-185`, `labdata/cli.py:91-99`).

---

## 6. Version policy

The document carries a single integer, `schema_version`
(`labdata/models.py:22`, `schema/output.schema.json:10-13`). It has no minor
component, because there is nothing in the document a consumer would branch
on below the level of "can I still read this".

**A major change increments `schema_version`.** A change is major — breaking —
when it can make a conforming consumer reject the output or misinterpret it:

- **Adding, removing or renaming a property.** *Adding* is breaking here
  because the schema is closed: every object sets
  `additionalProperties: false`, so a consumer validating against the
  previous version rejects a document carrying a new key.
- **Changing a type**, including making a string an object or a scalar a
  list.
- **Changing nullability** — a property that could not be `null` now can, or
  the reverse.
- **Changing requiredness** — moving a property into or out of `required`.
- **Changing meaning** while keeping the name and type. `venue` ceasing to
  carry Markdown is this kind of change even though it stays a string.
- **Changing an identifier or a relationship** — how `bib_id` or a person
  `id` is formed, or what `publication_ids` points at.
- **Changing an order that §3 promises.** Reordering `publications`, or
  moving where a publication with no year lands, is breaking. Changing the
  order of a list §3 calls unordered is not.

**A minor change does not increment it.** Minor changes are those that leave
every conforming document conforming and every conforming reading correct:
new CLI flags, new diagnostics, faster or clearer implementations,
documentation, and bug fixes whose output was already non-conforming.

**Published schemas are immutable and live at versioned paths.** A schema
that has been published is never edited. Version `N`'s schema stays
reachable, byte for byte, at its own path after version `N+1` ships, so a
consumer pinned to `N` keeps a stable target.

> **Target (#56).** This is not true today. There is one schema file, at the
> unversioned path `schema/output.schema.json`, and it is edited in place on
> every bump: it currently asserts `"const": 3`
> (`schema/output.schema.json:12`). Its `$id` points at
> `.../blob/main/schema/output.schema.json`
> (`schema/output.schema.json:3`), a mutable branch URL, which is unfit for a
> public contract. #56 moves the v4 schema to `schema/v4/output.schema.json`
> and keeps v3 reachable unchanged; #37 covers publishing the resulting URLs
> for outside consumers.

**Version history.**

| `schema_version` | Change |
|---|---|
| 1 | The original document. |
| 2 | Authors carry their structured name parts (#23). Breaking: the schema is closed, so a v1 consumer rejects the new keys. |
| 3 | Authors carry `equal_contribution` (#46). Breaking, for the same reason. |

Recorded at `labdata/models.py:16-22`.

---

## 7. `@string` macros: last definition wins

BibTeX `@string` macros are expanded before a field reaches labdata. When one
file defines the same macro more than once, **the last definition wins**.

This matches classic BibTeX. It is not universal: some BibTeX parsers keep
the first definition instead, which is why the rule has to be written down
rather than assumed.

Verified: `tests/corpus/valid/strings.bib` defines `rss`, `cfx` and `jfx`
twice each, and `tests/COVERAGE.md` row `strings.repeat_last_wins` records
that the last definition is used and the first never appears in the output
(`tests/conformance/test_valid_corpus.py::test_strings`, status `pass`).

**Precisely: expansion is positional.** A definition applies to every use
*after* it in the same file, and a redefinition replaces it from that point
on. In the ordinary layout, where a file's `@string` block precedes its
entries, that is exactly "the last definition wins" for the whole file. It
differs only for an entry written *between* two definitions, which expands
with the earlier one — the definition that was in force where it was written.
Verified directly against a file with an entry between two definitions of the
same macro; `tests/corpus/valid/strings.bib` defines all three macros before
any entry uses them, so the corpus does not distinguish the two readings.

A redefinition is never silent. labdata reports it on standard error
(`labdata/parsers/bibtex.py:91-107`, `:195-197`):

```
Warning: @string macro 'rss' is defined more than once; the last definition is used
```

Today that is one line per redefined macro per file. Collapsing a run's
redefinitions into a single summary line is tracked as `xfail #21` in
`tests/COVERAGE.md:63`. The *rule* — last wins — is in force either way; only
the shape of the message is open.

**Macros are scoped to the file that defines them.** Each `.bib` file is
parsed with its own parser, so a macro defined in one file is undefined in
the next (`labdata/parsers/bibtex.py:193-204`). A use of an undefined macro
is reported and expands to the empty string; the entry itself is kept, not
dropped. Verified directly. Making that diagnostic name the file, entry key
and field — rather than relaying the parser's own wording — is #26
(`tests/COVERAGE.md:67`).

---

## 8. The entity boundary, and the evidence for it

The document describes exactly these entities:

```
schema_version, lab, people, publications, projects, collaborators (derived)
```

`lab` is the one entity labdata does not compute anything from. It is kept
deliberately: a document needs a header, and it is where contact information
lives.

The boundary is a finding, not an omission. Two independent surveys of real
academic lab websites — 27 groups and 18 groups, spanning robotics, biology,
chemistry, physics, economics and public health, across six countries — found
only three content types at or above **85% prevalence**: people, publications,
and projects or research areas. Everything else fell below **70%**. The types
that recur most often below that line — news, openings, teaching — are prose
or institution-specific, with no shared structure to compile: there is no
schema for them that two labs would both accept, and nothing for a compiler
to check. The full reasoning is #38; #60 is the one experiment that could
later change it.

So each rejected type is rejected for a stated reason, and each has a home:

| Not an entity | Where it belongs instead |
|---|---|
| News and blog posts | Prose pages in your site repository; #60 explores deriving a feed from works instead of modelling news. |
| Openings and recruiting | A prose page in your site repository. |
| Teaching and courses | A prose page in your site repository, or the institution's course catalogue. |
| Press and media coverage | A typed link on the work it covers, once #27 adds explicit link fields. |
| Galleries, photos and videos | Your site repository; a video already reaches the document as `publication.video_url`. |
| Awards and honours | An attribute of the work, today `publication.note`; #27 moves it out of `note`. |
| Funding and grants | Your site repository. Nothing in the document depends on it. |
| Software and datasets | Not a separate collection — they are kinds of *work*, added by #31. |
| Alumni | Not a collection — a `status` on a person (`labdata/models.py:115`). |
| Robots, platforms, facilities | Your site repository; one of 27 surveyed sites had such a page. |

**There is no generic extension mechanism and no `collections` escape
hatch.** What one would carry is mostly prose, and its one real service —
catching references that point at nothing — is delivered by #58 without the
document owning the payload.

---

## 9. What this file is not

It does not list the document's fields; `schema/output.schema.json` does,
and #56 revises that list for `schema_version` 4. It does not describe the
Jekyll templates in `site/`, which are one downstream consumer and move to
their own repository in #57. It does not describe the input formats
`lab.yaml`, `people.yaml` and `projects.yaml` beyond what §5 needs; schemas
for those are #37.

`tests/COVERAGE.md` is the case-by-case record of what labdata does with each
input, with the fixture and the test for each. Where it and this file
disagree about current behaviour, `tests/COVERAGE.md` is the one backed by a
test.
