# labdata specification

labdata is a compiler. It reads BibTeX and a little YAML and emits one
document describing a lab's works, people, projects and the links between
them.

This file states the parts of that contract a JSON Schema cannot express:
what the strings in the document are, what order the lists are in, what an
absent key means, which fields are computed, when the version changes, and
how a repeated `@string` macro resolves. `schema/output.schema.json` states
the rest.

Everything here is normative unless it carries a `Target` note. A `Target`
note marks a rule that the emitted document does **not** satisfy today, and
names the issue that will make it true. Until that issue lands, the rule is
the intent and the note is the fact. A `Version note` marks behaviour that
changed at a known release boundary, and states both sides.

- Applies to: `schema_version` 3 (`labdata.models.SCHEMA_VERSION`), package
  version 2.0.0 (`labdata.__version__`).

### How this file cites the code

Every rule below is grounded in a named part of the code rather than a line
number, because line numbers rot silently: a function such as
`labdata.parsers.bibtex.parse_all_publications()`, a method such as
`Person.to_dict()`, a module-level constant such as `TEXT_FIELDS`, a JSON
Pointer into `schema/output.schema.json` such as `/$defs/person/required`, or
a `tests/COVERAGE.md` row key such as `config.people_file.missing`. A bare
statement is cited by its enclosing function.

Nothing yet checks that these references resolve; #63 proposes the test that
would.

---

## 1. Contract hierarchy

**The emitted document plus its published schema is normative.** Everything
else in this repository — the CLI's internals, the Python classes, the
bundled Jekyll templates — exists to produce that document.

**When the emitted document and the schema disagree, the schema wins and the
code is the bug.** A consumer that validates against the published schema and
is rejected by labdata's own output has found a defect in labdata, never in
itself.

**The CLI is the reference compiler.** Its flags, its exit codes and the
stream each kind of message goes to are public API.

Flags, as `labdata.cli.main()` defines them:

| Flag | Meaning |
|---|---|
| `--config PATH` | Required. The `lab.yaml` to compile. |
| `--format {yaml,json}` | Output format. Default `yaml`. |
| `--output PATH` | Write the document to `PATH`. |
| `--validate` | Report counts and problems, then exit without writing. |
| `--unresolved` | List author names that matched no person, then exit. |

**At least one** of `--output`, `--validate` or `--unresolved` is required —
not exactly one. `labdata.cli.main()` rejects only the case where all three
are absent, so combinations are accepted and resolved by **precedence**:
`--validate` is handled first and returns; `--unresolved` next; `--output`
only if neither was given. So `labdata --config c.yaml --validate --output
out.yml` runs validation and reports normally, but **does not write
`out.yml`**, and exits `0`. Verified by running both combinations.

Exit codes, as `labdata.cli.main()` returns them:

| Code | Meaning |
|---|---|
| `0` | Success. `--output` wrote the file; `--validate` found no errors; `--unresolved` reported. |
| `1` | Error. Configuration file missing, configuration failed to load, or `--validate` found unknown project ids or duplicate citation keys. |
| `2` | Usage error from the argument parser: a missing or unrecognised flag, or none of `--output` / `--validate` / `--unresolved`. |

**Streams and message shapes.** Ordinary reporting goes to **standard
output**: the counts, unresolved names and unknown project ids of
`--validate` and `--unresolved`, and, in output mode, the `Wrote …` line and
the entity counts that follow it. **Diagnostics** go to **standard error**,
in one of three shapes:

| Shape | Source |
|---|---|
| `Warning: …` | Problems with the input, from `labdata.parsers.bibtex._warn()` and `labdata.resolver.build_alias_index()`. |
| `<CODE> <file>:<key>:<field>: …` | A diagnostic carrying a stable code, described under *Diagnostic codes* below. Under `--validate` it appears on standard output beneath `Bibliography errors`; in the other modes the same text is prefixed with `Warning: ` on standard error. |
| `Error: …` | Configuration failures, from `labdata.cli.main()`: `Error: Configuration file not found: …` and `Error loading configuration: …`. |
| `usage: …` / `…: error: …` | Argument errors, in the argument parser's own format. |

There is no single prefix across all diagnostics, and a consumer that greps
for one will miss the other two.

**Unresolved authors are not errors.** `--validate` lists them and still
exits `0`. This is intended, not a gap: an author who is not in `people.yaml`
is usually an external collaborator, and #26 states the rule directly —
"unresolved external collaborators are never errors". Only unknown project
ids fail the run, because a project id naming no project is a typo in data
labdata does own.

> **Target (#26).** Two gaps in the above are real today.
> (a) An unhandled failure — a `.bib` file named in `lab.yaml` that does not
> exist, or a `year` field that is not a number — prints a Python traceback
> and also exits `1`, so `1` does not by itself distinguish a diagnosed error
> from a crash. Verified against `labdata.parsers.bibtex.parse_bibtex_file()`,
> which reads the file with no guard, and `entry_to_publication()`, which
> calls `int()` on the `year` field.
> (b) Diagnostic *text* is not stable, except where a diagnostic carries a
> code. Messages relayed from the BibTeX parser are passed through as that
> library phrased them (`labdata.parsers.bibtex.parse_bibtex_file()` relays
> each captured error), and labdata's own messages do not consistently name
> the file, entry key and field. Consumers may depend on the stream, the
> shapes above and any code in the registry below, not on the wording around
> them.

### Diagnostic codes

A diagnostic may carry a **stable code** so that tooling can recognise it
without depending on English wording. Codes obey three rules:

1. The form is `<COMPONENT>-<CONDITION>` in upper case, for example
   `BIB-DUPLICATE-KEY`, followed by a space, then `<file>:<key>:<field>`, then
   a colon and prose.
2. **Severity is not part of the code.** The same condition is already
   reported as an error by `--validate` and as a warning by the other modes,
   and #26 adds a `--strict` mode that raises severity further. A code says
   *what was found*, never how badly the run took it; severity is carried by
   the stream and the `Warning: ` prefix.
3. A published code is permanent. It is never reused for a different
   condition, and retiring one is a breaking change.

Codes in use:

| Code | Condition |
|---|---|
| `BIB-DUPLICATE-KEY` | The same citation key appears twice in one `.bib` file, or in two of the configured files. |

Most diagnostics do not carry a code yet. #26 adds them incrementally, and an
uncoded diagnostic is not a stable interface.

> **Version note (#26, PR #64).** Duplicate citation keys were invisible
> through commit `dd06e37`: the parser library kept the first entry, and a key
> repeated across two configured files passed `--validate` with exit `0`.
> Since PR #64 merged, `labdata.parsers.bibtex.parse_all_publications()`
> reports each duplicate under the `BIB-DUPLICATE-KEY` code, `--validate`
> exits `1`, and the other modes emit the same diagnostic as a warning and
> continue. The code was introduced as `E-BIB-DUPLICATE-KEY` and renamed to
> drop the severity prefix before any release, under rule 2 above.

> **Version note (#22, PR #61).** Through commit `cf9e055`, `--unresolved`
> printed `All authors resolved.` when no `people_file` was configured, where
> nothing had been attempted. Since PR #61 merged, the `--unresolved` branch
> of `labdata.cli.main()` prints `Author resolution is not configured (no
> people_file).` and exits `0`. `tests/COVERAGE.md` row
> `config.people_file.missing` records the current behaviour as `pass`.

**The Python API is convenience only.** Public: the names in `labdata.__all__`
— `assemble`, `AssemblyResult`, the models `LabData`, `Publication`, `Author`,
`Person`, `Project`, `Collaborator`, the config loader `LabDataConfig` with
`BibFile`, and the exporters `export_to_yaml` and `export_to_json`.

Private, and free to change without a version bump: `labdata.parsers.*`,
`labdata.loaders`, `labdata.resolver`, `labdata.cli`'s internals, and every
underscore-prefixed name. Importing them is unsupported. In particular, no
guarantee is made about which BibTeX or LaTeX library sits behind
`labdata.parsers`; that it is an adapter boundary is stated in the
`labdata.parsers.bibtex` module docstring.

The package version (`labdata.__version__`) and the document's
`schema_version` (`labdata.models.SCHEMA_VERSION`) are independent. Neither
can be derived from the other.

---

## 2. The text rule

**Every string in the emitted document that is meant for display is plain
Unicode text.** Not HTML, not Markdown, not escaped, not LaTeX. The document
also carries strings that are not display text at all — identifiers, URLs and
the `bibtex` record — and heading 4 below lists them.

**Text is untrusted.** A title may contain `<`, `&`, `"`, `*` or `$`, and
often does: `Informed RRT*` and `BIT*` are real paper titles. labdata does
not escape them and will not, because it does not know what they are being
escaped for. **Renderers are responsible for escaping** — for HTML bodies, for
HTML attributes, for shell arguments, for whatever they emit.

### What labdata converts, and what it does not

This is the part that must be read carefully, because labdata enforces the
rule in one place only.

The four headings below are **lenses, not a partition**. Conversion and fate
are separate stages: a field is first converted or not, and then emitted,
consumed into a derived field, or discarded. A field can therefore appear
under more than one heading, and several do. `journal` is converted (1) and
then consumed into `venue` (3). `series`, `publisher`, `address` and
`organization` are converted (1) and then used by nothing (3).
`publication.url` is copied unconverted (2) and is also a URL rather than
display text (4). Read each heading as a question to ask about a string, not
as a box the string lives in.

**1. Converted prose — the rule is enforced here.** Prose fields read from
BibTeX are converted from LaTeX to Unicode by
`labdata.parsers.latex.latex_to_text()`, so `C{\^o}t{\'e}` arrives as `Côté`
and `\textbf{Best Paper}` arrives as `Best Paper`. Exactly the fields in
`labdata.parsers.bibtex.TEXT_FIELDS` are converted — `title`, `abstract`,
`note`, `journal`, `booktitle`, `school`, `institution`, `type`, `series`,
`publisher`, `address`, `organization` — applied in `entry_fields()`. Author
name parts are converted the same way, in `person_name_parts()`.

Being converted is not the same as being emitted. Of these fields, `title`,
`abstract` and `note` are emitted under their own names; `journal`,
`booktitle`, `school`, `institution` and `type` are consumed by
`format_venue()` (§5) and reach the document only through `venue`; and
`series`, `publisher`, `address` and `organization` are converted and then
used by nothing, so they also appear under heading 3.

**2. Emitted without conversion — the rule is a requirement on the input.**
These strings do reach the document, exactly as written, and labdata neither
converts nor checks them:

- **The person and project strings supplied in YAML.**
  `labdata.loaders.load_people()` and `load_projects()` perform no conversion
  of any kind, so a person's `name`, `role`, `current_position` or
  `thesis_title`, and a project's `title` or `description`, are copied
  straight from `people.yaml` and `projects.yaml`. Not every YAML string is
  emitted — `aliases` and the configuration paths are not; see heading 3.
- **`publication.category`**, which comes from the `category` of the
  `bib_files` entry in `lab.yaml`, not from the `.bib` file
  (`labdata.config.LabDataConfig.from_yaml()`, then
  `labdata.parsers.bibtex.parse_all_publications()`).
- **`lab`**, copied through from `lab.yaml` unchanged
  (`LabDataConfig.from_yaml()`, then `LabData.to_dict()`).
- **`publication.url`**, the BibTeX `url` field, when it is not a video URL.

For these the plain-Unicode rule is a **requirement on the input, not a
guarantee labdata enforces**. If `people.yaml` says `name: "<b>Alice</b>"`,
or a `bib_files` category is `"**Journal** Papers"`, that string appears in
the document exactly as written and no diagnostic is raised. Verified
directly: a category of `<b>Cat</b> & **md**` is emitted unchanged. Authors
of input files are responsible for keeping these plain, and renderers should
escape them as they escape everything else.

**3. Read and acted on.** labdata reads each of these and does something with
it other than passing it through as display text: transforms it, consumes it
into a derived field, or reads it only to make a decision. None of them
reaches the document as a plain-text string under its own name, so the text
rule does not apply to the input itself — only to whatever it produces.
`/$defs/publication/properties` declares no `doi`, `eprint` or `project`.

| Input | What becomes of it |
|---|---|
| `doi` | Transformed into `doi_url` (`construct_doi_url()`). |
| `eprint` | Transformed into `arxiv_url` (`construct_arxiv_url()`). |
| `archivePrefix` (or `archiveprefix`) | Read only to decide whether `eprint` is an arXiv id (`construct_arxiv_url()`). |
| `project` | Parsed into the list `project_ids` (`parse_project_ids()`). |
| `url`, for a video host | Detected by `extract_video_url()` and emitted as `video_url` by `entry_to_publication()`, which then leaves `url` as `null`. |
| `author` | Parsed into the `authors` list (`parse_author_list()`); the name parts are converted under heading 1. |
| `year` | Emitted as the integer `year` — not a string — and drives the publication order (§3) and `venue`. |
| `volume`, `number` | Outside `TEXT_FIELDS`, so unconverted; consumed by `format_venue()` and not emitted separately. |
| `crossref` | Resolved by `resolve_crossref()`, which fills the child's missing fields from the parent and turns the parent's `title` into the child's `booktitle`. **`author` is not inherited**: `parse_author_list()` reads the raw entry rather than the resolved fields, so a child with no `author` of its own has an empty `authors` list. Verified directly. Not emitted as a property. |
| The citation key and the entry type | Become `bib_id` and `entry_type` (`entry_fields()`); see heading 4. |
| `journal`, `booktitle`, `school`, `institution`, `type` | Converted under heading 1, then consumed by `format_venue()`. |
| `series`, `publisher`, `address`, `organization` | Converted under heading 1, then used by nothing. |
| `person.aliases` | Read for matching by `labdata.resolver.build_alias_index()`, never emitted — `Person.to_dict()` has no `aliases` key. |
| `bib_dir`, `bib_files[].name`, `people_file`, `projects_file`, `pdf_base_url` | Configuration. Never emitted; `pdf_base_url` survives only inside the constructed `pdf_url`. |
| Any BibTeX field not named anywhere in this table or heading 1 — `pages`, `editor`, `month`, `isbn` and the rest | Not interpreted by labdata outside the `bibtex` record. `entry_fields()` copies it and `format_bibtex()` serializes it, but nothing reads its value, so it affects no other property (§5). Emitting more of them as first-class properties is #56. |

The fields named in that table and in heading 1 are the complete set labdata
*interprets* from a `.bib` entry; everything else falls in the last row.
Verified by enumerating the field names `labdata/parsers/bibtex.py` looks up.

"Not emitted" throughout that table means *not emitted as a property of the
publication*. Every field of the entry, read or not, also survives inside the
`bibtex` record, which is a re-serialization of the entry's data rather than a
set of first-class properties (§5).

**4. Not display text.** Some emitted strings are identifiers or machine
values, and the plain-text rule is beside the point for them: `bib_id`,
`entry_type`, `person_id`, every `*_url` including `publication.url`, and
every id in `project_ids`, `publication_ids` and `people_ids`. Also here is
**`publication.bibtex`**, which is a BibTeX record meant to be copied rather
than displayed, and which still contains LaTeX — see §5 for what it does and
does not preserve. `lab` is a YAML mapping rather than a string; its *values*
fall under heading 2.

`publication.category` is *not* in this group. It is a label a renderer
displays as a section heading as well as grouping by, so it is display text
and heading 2 applies to it in full.

### The one markup exception

**Math is left as TeX**, delimited by `$…$`, so that KaTeX or MathJax can
typeset it (`labdata.parsers.latex._CONVERTER` is built with
`math_mode='verbatim'`). This is the one place a text field is expected to
contain markup, and it applies only to the fields under heading 1.

### Two degraded cases

- When a field cannot be converted, labdata warns and falls back to
  `labdata.parsers.latex.strip_braces()`, keeping the text as written with
  its braces removed (`labdata.parsers.bibtex._convert()`). Such a value may
  still contain LaTeX commands. This is a degraded case, not a second
  contract: the document is still declared plain text, and the warning is the
  signal that one field did not make it.
- `\href{url}{text}` is rewritten to `text (url)` before conversion, in
  `labdata.parsers.latex.latex_to_text()`, because the converter cannot read
  it. Carrying link content into explicit fields is #27.

> **Target (#18).** `publication.venue` contains Markdown today. It is
> composed by `labdata.parsers.bibtex.format_venue()`, whose own docstring
> says "Uses Markdown (not HTML)": an article in journal `J` published in 2021
> yields the string `*J*, 2021`. This is the only place labdata *generates*
> markup into a text field — as distinct from the YAML strings above, which
> it merely passes through. #18 removes it; #56 replaces `venue` with a
> structured container so there is nothing left to compose.

---

## 3. Ordering

Every list in the document is covered here. A list not described as ordered
is **unordered**, and a consumer that depends on its order is depending on an
accident.

| List | Order |
|---|---|
| `publications` | `year` **descending**. Ties keep *read order* (below). The sort is the final statement of `labdata.parsers.bibtex.parse_all_publications()`. |
| `publication.authors` | The order the `author` field wrote them (`labdata.parsers.bibtex.parse_author_list()`). A terminal `and others` is BibTeX's "et al." and is dropped rather than emitted as an author. |
| `publication.project_ids` | The order the `project` field wrote them, comma-separated, whitespace trimmed, empty entries dropped (`labdata.parsers.bibtex.parse_project_ids()`). |
| `people` | The order of `people_file`. labdata does not sort people (`labdata.loaders.load_people()`, called by `labdata.assembler.assemble()`). |
| `projects` | The order of `projects_file`, likewise (`labdata.loaders.load_projects()`). |
| `person.publication_ids` | The order of the `publications` list, filtered to that person, first occurrence only (`labdata.resolver.compute_backlinks()`). |
| `project.publication_ids` | The order of the `publications` list, filtered to that project, first occurrence only (`compute_backlinks()`). |
| `project.people_ids` | Person id **ascending**, by Unicode code point (`compute_backlinks()` sorts the set it collects). |
| `collaborators` | `last_year` **descending**, then `publication_count` **descending**, then `name` **ascending** by Unicode code point (the sort in `labdata.assembler.assemble()`; `tests/COVERAGE.md` row `output.collaborators.order`). |
| `lab` | Unordered. It is a YAML mapping copied through; consumers read it by key. |

**Read order** is the order in which entries were parsed: the files in the
order `bib_files` lists them in `lab.yaml`, and within each file, the order
the entries appear in the source. `parse_all_publications()` accumulates
entries in that order before sorting. Because the publication sort is stable,
read order is the tie-breaker for publications of the same year, and it is a
promise, not an accident.

**Ties and missing sort keys.**

- Two publications of the same year appear in read order. Two entries with
  the same year in the same file appear in source order.
- A publication with **no `year` field is treated as year `0`**
  (`labdata.parsers.bibtex.entry_to_publication()` calls `int()` on the field
  with a default of `0`) and therefore sorts **last**.
- Two collaborators can only tie through all three keys if they share a name,
  and a name is their identity (§5), so the order is total.
- Sorting by "Unicode code point" means `Z` sorts before `a`, and `Ö` sorts
  after `z`. No locale collation is applied.

> **Target (#56).** `year: 0` for an absent year is silent corruption: it is
> indistinguishable from a genuine year `0` and it places the entry in a
> position that means nothing. #56 makes `year` nullable and emits a
> diagnostic instead. When it does, the sort position of a publication with
> no year changes, which is itself a breaking change under §6.

**Key order within an object is not part of the contract.** The YAML export
writes keys in insertion order (`labdata.exporters.export_to_yaml()` passes
`sort_keys=False`) and the JSON export does the same, but both formats define
objects as unordered and consumers must treat them that way.

**YAML and JSON carry the same document.** `--format yaml` and `--format
json` serialize the identical structure (`labdata.exporters.export_to_yaml()`
and `export_to_json()` both serialize `LabData.to_dict()`); neither is more
authoritative.

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

This rule is satisfied today by `Author.to_dict()`, `Publication.to_dict()`
(except `bibtex`), `Project.to_dict()` and `Collaborator.to_dict()`, each of
which emits every declared key unconditionally.

> **Target (#56).** Three deviations exist today, and each is a bug against
> the rule above rather than a second policy.
> (a) `Person.to_dict()` emits only `id`, `name`, `role`, `status`, `website`
> and `publication_count` unconditionally — the same six as
> `/$defs/person/required` — and **omits** `photo`, `email`, `co_advisor`,
> `start_year`, `publication_ids` and the alumni fields `end_year`, `degree`,
> `thesis_title` and `current_position` whenever their value is falsy. The
> alumni fields are additionally omitted for anyone whose `status` is not
> `alumni`. Verified: a person with no publications has no `publication_ids`
> key at all.
> (b) `Publication.to_dict()` omits `bibtex` when the entry could not be
> written back out as BibTeX.
> (c) `LabData.to_dict()` omits top-level `lab` when `lab.yaml` has no `lab`
> section — and, because it tests the value's truthiness rather than its
> presence, also when `lab.yaml` explicitly supplies an empty `lab: {}`.
> Verified: `lab: {}` produces a document with no `lab` key, so a consumer
> cannot tell "no header" from "an empty header".
> Fixing any of these changes the schema's `required` lists and the
> nullability of the affected properties, which is breaking under §6. #56 is
> the consolidated breaking change that normalises them.

**Where "absent" cannot happen at all.** The schema defines seven object
schemas. **Six are closed:** the document itself (`/additionalProperties`) and
each of `/$defs/author`, `/$defs/publication`, `/$defs/person`,
`/$defs/project` and `/$defs/collaborator` set `additionalProperties: false`.
Within those six, a property that is not declared cannot appear, and "absent"
always means a declared property with no value.

**The seventh, `lab`, is open.** `/properties/lab` declares only
`description` and `type: object`. It has no `properties` and no
`additionalProperties`, so any keys whatever validate inside it. The policy
above does not apply within `lab`: its keys are whatever `lab.yaml` supplied,
labdata declares none of them, and a consumer must probe for the ones it
wants rather than expect a fixed set. Giving `lab` a real structure is #56.

---

## 5. Input versus derived

**Input** fields come from the author's files and labdata carries them
through. **Derived** fields labdata computes. Derived fields are **read-only
outputs**: they must never be written back into `people.yaml`,
`projects.yaml` or a `.bib` file. Doing so makes the next compile read
labdata's own output as input, and a wrong derivation becomes permanent.

| Field | Origin |
|---|---|
| `schema_version` | Derived — a constant of the compiler (`labdata.models.SCHEMA_VERSION`). |
| `lab` | Input — the `lab` section of `lab.yaml`, copied unchanged (`LabDataConfig.from_yaml()`). |
| `publication.bib_id` | Input — the BibTeX citation key, **as written**. `labdata.parsers.bibtex.entry_fields()` preserves its case. |
| `publication.entry_type` | Input — the BibTeX entry type, **lowercased** by `entry_fields()`. Of it and `bib_id`, it is the only one that is case-folded. |
| `publication.title`, `abstract`, `note` | Input — BibTeX fields, converted from LaTeX to text (§2). `note` additionally has trailing `.` and whitespace trimmed (`labdata.parsers.bibtex.extract_note()`). |
| `publication.year` | Input — the BibTeX `year`, as an integer; `0` when absent (`entry_to_publication()`). |
| `publication.category` | Input — the `category` of the `bib_files` entry the file was listed under, not anything in the `.bib` file (`labdata.config.BibFile`, read by `parse_all_publications()`). |
| `publication.venue` | **Derived** — composed from `journal`, `booktitle`, `school`, `institution`, `type`, `number`, `volume`, `eprint` and `year` according to the entry type (`labdata.parsers.bibtex.format_venue()`). |
| `publication.url` | Input — the BibTeX `url`, but only when it is not a video URL (`entry_to_publication()`). |
| `publication.video_url` | **Derived** — the BibTeX `url`, when it names youtube.com, youtu.be or vimeo.com (`labdata.parsers.bibtex.extract_video_url()`). |
| `publication.doi_url` | **Derived** — `https://doi.org/` plus the `doi` field, unless `doi` is already a URL (`construct_doi_url()`). |
| `publication.arxiv_url` | **Derived** — `https://arxiv.org/abs/` plus the `eprint` field (`construct_arxiv_url()`). |
| `publication.pdf_url` | **Derived** — `pdf_base_url` plus the citation key plus `.pdf` (`resolve_pdf_url()`). |
| `publication.project_ids` | Input — the `project` field, split on commas (`parse_project_ids()`). |
| `publication.bibtex` | **Derived** — the entry re-serialized as BibTeX (`format_bibtex()`). See below. |
| `author.given`, `von`, `family`, `suffix`, `literal` | Input — the parts BibTeX split the name into, converted from LaTeX, with an equal-contribution marker removed (`person_name_parts()`). |
| `author.name` | **Derived** — the display form, built from the parts by abbreviating given names to initials: `A. J. van Last, Jr.` (`format_name()`). |
| `author.person_id` | **Derived** — the resolver's match against `people_file` (`labdata.resolver.resolve_authors()`). |
| `author.equal_contribution` | **Derived** — whether the entry wrote a `*` marker on any part of the name (`labdata.parsers.bibtex.marks_equal_contribution()`). |
| `person.*` except the two below | Input — the fields of `people_file` (`labdata.loaders.load_people()`). `aliases` is read for matching and is **not** emitted. |
| `person.publication_ids`, `publication_count` | **Derived** — back-links, and their count (`labdata.resolver.compute_backlinks()`). |
| `project.id`, `title`, `description`, `website`, `status` | Input — the fields of `projects_file` (`labdata.loaders.load_projects()`). |
| `project.publication_ids`, `people_ids` | **Derived** — back-links, and the people reached through them (`compute_backlinks()`). |
| `collaborators` | **Derived, entirely** — see below (`labdata.assembler.assemble()`). |

### Four derived fields that need more than a row

**`publication.bibtex` is re-serialized, not verbatim.** It is produced by
`format_bibtex()`, which calls pybtex's `Entry.to_string("bibtex")` on the
*parsed* entry. What survives is the set of fields and their values. What does
**not** survive is how they were written: field order, brace-versus-quote
delimiters, whitespace and indentation are all the serializer's, and
`@string` macros are gone — a field written `journal = j` comes back as
`journal = "Expanded Journal"`. Verified directly.

It is produced *before* crossref resolution and *before* LaTeX conversion, so
a field inherited from a parent entry is absent from it and LaTeX markup is
still present. Read it as "the entry's data, re-typeset", not as "the entry as
the author wrote it".

**`publication.pdf_url` is guessed for remote bases, never verified.** When
`pdf_base_url` begins with `http://` or `https://`, `resolve_pdf_url()`
constructs the URL unconditionally and does not fetch it; it may 404. When
`pdf_base_url` is a local path, the file's existence *is* checked and a
missing file yields `null`. So the guarantee differs by base: local is
checked, remote is not. Verifying remote links is #20.

**`collaborators` is a derived index over unresolved authorships, not a list
of people.** `assemble()` walks every publication's authors, and for each
author with no `person_id` increments a counter keyed by the author's
**display name**. Two consequences:

- The key is not an identity. Three different people who all write as
  `J. Smith` are one entry, with their publications merged.
- `publication_count` is the number of **unresolved authorship occurrences**,
  not the number of distinct publications. There is no per-publication
  deduplication, so one publication listing `J. Smith` twice — two different
  Smiths, or a duplicated author field — contributes `2`. Verified: a single
  entry with `author = {Smith, John and Smith, Jane}` and no `people.yaml`
  yields one collaborator `J. Smith` with `publication_count: 2`.

`last_year` is the greatest `year` of any publication contributing an
occurrence. #56 relabels `collaborators` as derived so it stops reading as an
authoritative list of humans.

**Unknown project ids are kept, not dropped.** A `project_ids` entry naming no
project in `projects_file` stays in the publication so the problem stays
visible, and `--validate` reports it and exits `1`
(`labdata.resolver.resolve_projects()` returns them; `labdata.cli.main()`
counts them as errors).

---

## 6. Version policy

The document carries a single integer, `schema_version`
(`labdata.models.SCHEMA_VERSION`, pinned in the schema at
`/properties/schema_version/const`). It has no minor component, because there
is nothing in the document a consumer would branch on below the level of "can
I still read this".

**A major change increments `schema_version`.** A change is major — breaking —
when it can make a conforming consumer reject the output or misinterpret it:

- **Adding, removing or renaming a property** of any of the six closed
  objects — the document itself and the five entity types (§4). *Adding* is
  breaking there because those objects set `additionalProperties: false`, so
  a consumer validating against the previous version rejects a document
  carrying a new key. That includes a new **top-level** property beside
  `publications`, `people`, `projects` and `collaborators`: the document is
  closed too, so a new entity collection is a breaking change on its own.
  **Inside `lab` this does not hold**: `/properties/lab` is the one open
  object, nothing inside it is declared, and adding a key there breaks no
  conforming consumer. Giving `lab` a declared structure would itself be a
  breaking change, because it would close a door that is currently open.
- **Changing a type**, including making a string an object or a scalar a list.
- **Changing nullability** — a property that could not be `null` now can, or
  the reverse.
- **Changing requiredness** — moving a property into or out of a `required`
  list such as `/$defs/publication/required`.
- **Changing meaning** while keeping the name and type. `venue` ceasing to
  carry Markdown is this kind of change even though it stays a string.
- **Changing an identifier or a relationship** — how `bib_id` or a person `id`
  is formed, or what `publication_ids` points at.
- **Changing an order that §3 promises.** Reordering `publications`, or moving
  where a publication with no year lands, is breaking. Changing the order of a
  list §3 calls unordered is not.

**A minor change does not increment it.** Minor changes are those that leave
every conforming document conforming and every conforming reading correct:
new CLI flags, new diagnostics, faster or clearer implementations,
documentation, and bug fixes whose output was already non-conforming.

**Published schemas are immutable and live at versioned paths.** A schema that
has been published is never edited. Version `N`'s schema stays reachable, byte
for byte, at its own path after version `N+1` ships, so a consumer pinned to
`N` keeps a stable target.

> **Target (#56).** This is not true today. There is one schema file, at the
> unversioned path `schema/output.schema.json`, and it is edited in place on
> every bump: `/properties/schema_version/const` currently asserts `3`. Its
> `/$id` points at `.../blob/main/schema/output.schema.json`, a mutable branch
> URL, which is unfit for a public contract. #56 moves the v4 schema to
> `schema/v4/output.schema.json` and keeps v3 reachable unchanged; #37 covers
> publishing the resulting URLs for outside consumers.

**Version history**, as recorded in the comment above
`labdata.models.SCHEMA_VERSION`:

| `schema_version` | Change |
|---|---|
| 1 | The original document. |
| 2 | Authors carry their structured name parts (#23). Breaking: the object is closed, so a v1 consumer rejects the new keys. |
| 3 | Authors carry `equal_contribution` (#46). Breaking, for the same reason. |

---

## 7. `@string` macros: last definition wins

BibTeX `@string` macros are expanded before a field reaches labdata. When one
file defines the same macro more than once, **the last definition wins**.

This matches classic BibTeX. It is not universal: some BibTeX parsers keep the
first definition instead, which is why the rule has to be written down rather
than assumed.

Verified: `tests/corpus/valid/strings.bib` defines `rss`, `cfx` and `jfx`
twice each, and `tests/COVERAGE.md` row `strings.repeat_last_wins` records
that the last definition is used and the first never appears in the output.

**Precisely: expansion is positional.** A definition applies to every use
*after* it in the same file, and a redefinition replaces it from that point
on. In the ordinary layout, where a file's `@string` block precedes its
entries, that is exactly "the last definition wins" for the whole file. It
differs only for an entry written *between* two definitions, which expands
with the earlier one — the definition that was in force where it was written.
Verified directly against a file with an entry between two definitions of the
same macro; `tests/corpus/valid/strings.bib` defines all three macros before
any entry uses them, so the corpus does not distinguish the two readings.

A redefinition is never silent. `labdata.parsers.bibtex._redefined_macros()`
finds them and `parse_bibtex_file()` reports each on standard error:

```
Warning: @string macro 'rss' is defined more than once; the last definition is used
```

Two things about that message. It is **globally worded** where the rule is
positional — "the last definition is used" is true of every use after the last
definition, which is the ordinary case, but not of an entry written between
two definitions. The rule above, not the message, is the contract. And it is
currently **one line per redefined macro per file**; collapsing a run's
redefinitions into a single summary line is tracked as `xfail #21` in
`tests/COVERAGE.md` row `strings.redefined_report`. Changing either is a code
change.

**Macros are scoped to the file that defines them.** Each `.bib` file is
parsed with its own parser instance in `parse_bibtex_file()`, so a macro
defined in one file is undefined in the next. A use of an undefined macro is
reported and expands to the empty string; the entry itself is kept, not
dropped. Verified directly. Making that diagnostic name the file, entry key
and field — rather than relaying the parser's own wording — is #26
(`tests/COVERAGE.md` row `strings.undefined`).

---

## 8. The entity boundary, and the evidence for it

The document describes exactly these entities:

```
schema_version, lab, people, publications, projects, collaborators (derived)
```

`lab` is the one entity labdata does not compute anything from. It is kept
deliberately: a document needs a header, and it is where contact information
lives.

The boundary is a finding, not an omission. The project's stated evidence is
two independent surveys of real academic lab websites — 27 groups and 18
groups, spanning robotics, biology, chemistry, physics, economics and public
health, across six countries — which found only three content types at or
above **85% prevalence**: people, publications, and projects or research
areas. Everything else fell below **70%**. The types that recur most often
below that line — news, openings, teaching — are prose or
institution-specific, with no shared structure to compile: there is no schema
for them that two labs would both accept, and nothing for a compiler to
check. The surveys themselves are not in this repository and are not
independently reproducible from it; the reasoning is recorded in #38, and #60
is the one experiment that could later change it.

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
| Alumni | Not a collection — a `status` on a person (`labdata.models.Person.status`). |
| Robots, platforms, facilities | Your site repository; one of 27 surveyed sites had such a page. |

**There is no generic extension mechanism and no `collections` escape hatch.**
What one would carry is mostly prose, and its one real service — catching
references that point at nothing — is delivered by #58 without the document
owning the payload.

---

## 9. What this file is not

It does not list the document's fields; `schema/output.schema.json` does, and
#56 revises that list for `schema_version` 4. It does not describe the Jekyll
templates in `site/`, which are one downstream consumer and move to their own
repository in #57. It does not describe the input formats `lab.yaml`,
`people.yaml` and `projects.yaml` beyond what §5 needs; schemas for those are
#37.

`tests/COVERAGE.md` is the case-by-case record of what labdata does with each
input, with the fixture and the test for each. Where it and this file disagree
about current behaviour, `tests/COVERAGE.md` is the one backed by a test.
