# labdata specification

labdata is a compiler. It reads BibTeX and a little YAML and emits one
document describing a lab's works, people, projects and the links between
them.

This file states the parts of that contract a JSON Schema cannot express:
what the strings in the document are, what order the lists are in, what an
absent key means, which fields are computed, when the version changes, and
how a repeated `@string` macro resolves. `schema/v4/output.schema.json`
states the rest.

Everything here is normative unless it carries a `Target` note. A `Target`
note marks a rule that the emitted document does **not** satisfy today, and
names the issue that will make it true. Until that issue lands, the rule is
the intent and the note is the fact. A `Version note` marks behaviour that
changed at a known release boundary, and states both sides.

- Applies to: `schema_version` 4 (`labdata.models.SCHEMA_VERSION`), package
  version 3.0.0 (`labdata.__version__`).

### How this file cites the code

Every rule below is grounded in a named part of the code rather than a line
number, because line numbers rot silently: a function such as
`labdata.parsers.bibtex.parse_all_works()`, a method such as
`Person.to_dict()`, a module-level constant such as `TEXT_FIELDS`, a JSON
Pointer into `schema/v4/output.schema.json` such as `/$defs/person/required`, or
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

**If a consumer probe cannot be written from the emitted document alone, that
is a schema bug, not a probe bug.** The document is the whole contract, so a
consumer that needs a property the document does not carry has found a gap in
the document; the fix belongs in the schema, not in the consumer. Recovering
the property from `work.bibtex` does not close the gap, because that
record is an opaque re-serialization of the entry rather than a set of
first-class properties (§5), and neither does taking a composed string such
as `venue` apart. `examples/consumers/` holds five such probes — a plain HTML
page, a LaTeX CV fragment, a CSL-JSON export, a person/project/work edge list
and a BibTeX re-emission — each reading the document and nothing else, and
`tests/conformance/test_consumer_probes.py` runs every one of them against the
demo output. Under `schema_version` 3 four of them could not produce correct
output; `schema_version` 4 closed every one of those gaps but one. Their
failing assertions are marked `xfail(strict=True)` against **the issue that
owns the missing property**, and the one marker left is #24's: it asks for
two spellings of one external co-author to be joined, which a grouping keyed
on a name cannot do by construction. A strict `xfail` swallows every failure
in its test, including one in something the probe already does correctly, so
such a test is kept to the assertions that name the missing property — and,
for the prerequisites it cannot avoid relying on, the rule is: **every
prerequisite an xfailed test already satisfies is independently enforced by a
test that passes.** The xfailed identity test reads the graph's `authored`
edges; the passing `test_graph_is_well_formed` asserts that every one of them
matches the document, and the passing `test_identity_fixtures_are_present`
asserts that the works it is about are still there, so neither prerequisite
is checked only inside a marker. `examples/consumers/README.md` lists what is
left.

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
| `1` | Error. Configuration file missing, configuration failed to load, an entry carries `crossref`, or `--validate` found unknown project ids or duplicate citation keys. |
| `2` | Usage error from the argument parser: a missing or unrecognised flag, or none of `--output` / `--validate` / `--unresolved`. |

**Streams and message shapes.** Ordinary reporting goes to **standard
output**: the counts, unresolved names and unknown project ids of
`--validate` and `--unresolved`, and, in output mode, the `Wrote …` line and
the entity counts that follow it. **Diagnostics** go to **standard error**,
in one of three shapes:

| Shape | Source |
|---|---|
| `Warning: …` | Problems with the input, from `labdata.parsers.bibtex._warn()` and `labdata.resolver.build_alias_index()`. |
| `<CODE> <file>:<key>:<field>: …` | A diagnostic carrying a stable code, described under *Diagnostic codes* below. Under `--validate` it appears on standard output, beneath `Bibliography errors` when it fails the run and beneath `Warnings` when it does not; in the other modes a warning is prefixed with `Warning: ` on standard error and an error is written there unprefixed. |
| `Error: …` | Configuration failures, from `labdata.cli.main()`: `Error: Configuration file not found: …` and `Error loading configuration: …`. |
| `usage: …` / `…: error: …` | Argument errors, in the argument parser's own format. |

There is no single prefix across all diagnostics, and a consumer that greps
for one will miss the other two.

**Three severities, and the code says none of them.**
`labdata.assembler.AssemblyResult` carries the diagnostics in three lists,
because the run rather than the code decides how badly each is taken:
`fatal_errors` fail every mode, `bibliography_errors` fail `--validate` and
are warnings elsewhere, and `warnings` never fail anything. A `crossref`
field is fatal; a duplicate citation key fails validation; a missing year, a
risky grouping key and an unnamed lab header are warnings.

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
> which reads the file with no guard, and `entry_year()`, which calls `int()`
> on a `year` field that is present but is not a number.
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
| `BIB-CROSSREF-UNSUPPORTED` | An entry carries a `crossref` field. The diagnostic names the file, the entry key and the parent key; the entry is not emitted and the run fails, in every mode. |
| `BIB-YEAR-MISSING` | An entry has no `year` field. The work is emitted with `year: null` and sorts last. |
| `ID-GROUPING-SPANS-SPELLINGS` | One collaborator key grouped more than one distinct spelling of a name. Reported against the first authorship the key grouped. |
| `ID-GROUPING-INITIALS-AMBIGUOUS` | A collaborator key built from an initials-only name shares its initial and family name with at least one fuller key, so it could be any of them. Reported against the first authorship the key grouped. |
| `CONFIG-LAB-NAME-MISSING` | The `lab` header declares no `name`. A `lab` that is not a mapping at all is a different condition and is not reported under this code. |

Most diagnostics do not carry a code yet. #26 adds them incrementally, and an
uncoded diagnostic is not a stable interface.

> **Version note (#26, PR #64).** Duplicate citation keys were invisible
> through commit `dd06e37`: the parser library kept the first entry, and a key
> repeated across two configured files passed `--validate` with exit `0`.
> Since PR #64 merged, `labdata.parsers.bibtex.parse_all_works()`
> reports each duplicate under the `BIB-DUPLICATE-KEY` code, `--validate`
> exits `1`, and the other modes emit the same diagnostic as a warning and
> continue. The code was introduced as `E-BIB-DUPLICATE-KEY` and renamed to
> drop the severity prefix before any release, under rule 2 above.

> **Version note (#56, #65, PR for `schema_version` 4).** Through commit
> `78570e6`, the document's works were `publications`, the bibliography was
> one composed `venue` string, links and identifiers were five flat `*_url`
> properties, and an entry carrying `crossref` compiled with its parent's
> fields and none of its own authors. Since `schema_version` 4 the top level
> is `works`, the bibliography is structured, `links` and `identifiers` are
> open registries, `collaborators` is a declared grouping over unresolved
> authorships, and `crossref` is rejected under `BIB-CROSSREF-UNSUPPORTED`.
> The package version is 3.0.0; a consumer that needs the old document pins
> `schema_version` 3 and the schema at `schema/v3/output.schema.json`.

> **Version note (#22, PR #61).** Through commit `cf9e055`, `--unresolved`
> printed `All authors resolved.` when no `people_file` was configured, where
> nothing had been attempted. Since PR #61 merged, the `--unresolved` branch
> of `labdata.cli.main()` prints `Author resolution is not configured (no
> people_file).` and exits `0`. `tests/COVERAGE.md` row
> `config.people_file.missing` records the current behaviour as `pass`.

**The Python API is convenience only.** Public: the names in `labdata.__all__`
— `assemble`, `AssemblyResult`, the models `LabData`, `Work`, `Author`,
`Contributor`, `Venue`, `Link`, `Person`, `Project`, `Collaborator`, the
config loader `LabDataConfig` with `BibFile`, and the exporters
`export_to_yaml` and `export_to_json`. `Publication` was renamed to `Work` at
package version 3.0.0, with the document's `publications`.

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
then consumed into `venue.name` (3). `work.links[*][*].url` is built from
input (3) and is a URL rather than display text (4). Read each heading as a
question to ask about a string, not as a box the string lives in.

**1. Converted prose — the rule is enforced here.** Prose fields read from
BibTeX are converted from LaTeX to Unicode by
`labdata.parsers.latex.latex_to_text()`, so `C{\^o}t{\'e}` arrives as `Côté`
and `\textbf{Best Paper}` arrives as `Best Paper`. Exactly the fields in
`labdata.parsers.bibtex.TEXT_FIELDS` are converted — `title`, `abstract`,
`note`, `journal`, `booktitle`, `school`, `institution`, `type`, `series`,
`publisher`, `address`, `organization` — applied in `entry_fields()`. Name
parts are converted the same way, in `person_name_parts()`, for authors and
editors alike.

Being converted is not the same as being emitted. Of these fields, `title`,
`abstract`, `note`, `type`, `series`, `publisher`, `address` and
`organization` are emitted under their own names; `journal`, `booktitle`,
`school` and `institution` are consumed by `build_venue()` and reach the
document as `venue.name`, which is the one place labdata normalises across
entry types.

**2. Emitted without conversion — the rule is a requirement on the input.**
These strings do reach the document, exactly as written, and labdata neither
converts nor checks them:

- **The person and project strings supplied in YAML.**
  `labdata.loaders.load_people()` and `load_projects()` perform no conversion
  of any kind, so a person's `name`, `role`, `current_position` or
  `thesis_title`, and a project's `title` or `description`, are copied
  straight from `people.yaml` and `projects.yaml`. Not every YAML string is
  emitted — `aliases` and the configuration paths are not; see heading 3.
- **`work.category`**, which comes from the `category` of the `bib_files`
  entry in `lab.yaml`, not from the `.bib` file
  (`labdata.config.LabDataConfig.from_yaml()`, then
  `labdata.parsers.bibtex.parse_all_works()`).
- **`lab`**, copied through from `lab.yaml` unchanged
  (`LabDataConfig.from_yaml()`, then `LabData.to_dict()`).
- **The bibliographic parts** `volume`, `number`, `pages`, `chapter`, `month`,
  `edition` and `howpublished`, which are outside `TEXT_FIELDS` and are
  emitted as the entry wrote them.
- **Every identifier** in `identifiers`, and the `url` of a link whose
  `origin` is `input`.

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

| Input | What becomes of it |
|---|---|
| `doi` | Becomes `identifiers.doi`, with a resolver prefix taken off if it was written as a URL, and a link of kind `doi` built from it (`bare_doi()`, `build_identifiers()`, `build_links()`). |
| `eprint` | Becomes an identifier under the scheme `archivePrefix` names, and a link of kind `arxiv` when that scheme is arXiv (`build_identifiers()`, `build_links()`). |
| `archivePrefix` (or `archiveprefix`) | Becomes the **scheme** of the `eprint` identifier, and the `venue.name` of a preprint (`_archive_prefix()`). It has no property of its own, because naming the repository is what a scheme does. |
| `isbn`, `issn` | Become `identifiers.isbn` and `identifiers.issn` (`build_identifiers()`). |
| `project` | Parsed into the list `project_ids` (`parse_project_ids()`). |
| `url` | Becomes a link of kind `video` when it names youtube.com, youtu.be or vimeo.com, and of kind `url` otherwise, with `origin: input` (`is_video_url()`, `build_links()`). |
| `author` | Parsed into the `authors` list (`parse_author_list()`); the name parts are converted under heading 1. |
| `editor` | Parsed into the `editors` list (`parse_editor_list()`), resolved by the same machinery, and excluded from `work_count`, from `person.work_ids`, from a project's people and from `collaborators`. |
| `year` | Emitted as the integer `year` — not a string — or `null` with a `BIB-YEAR-MISSING` diagnostic when the entry supplied none. It drives the works order (§3). |
| `crossref` | **Rejected.** An entry carrying it is an error under `BIB-CROSSREF-UNSUPPORTED` that names the file, the entry key and the parent key; the entry is not emitted and the run fails in every mode (`parse_all_works()`). No field of any entry is filled in from any other entry. |
| `journal`, `booktitle`, `school`, `institution` | Converted under heading 1, then consumed by `build_venue()` into `venue.name`, with the `venue.kind` each implies. |
| The citation key and the entry type | Become `bib_id` (and `source.key`) and `entry_type` (`entry_fields()`); see heading 4. |
| `person.aliases` | Read for matching by `labdata.resolver.build_alias_index()`, never emitted — `Person.to_dict()` has no `aliases` key. |
| `bib_dir`, `people_file`, `projects_file`, `pdf_base_url` | Configuration. Never emitted; `pdf_base_url` survives only inside the constructed PDF link. `bib_files[].name` is emitted, as `work.source.file`. |
| Any BibTeX field named nowhere in this table or heading 1 — `keywords`, `annote`, `language` and the rest | Not interpreted by labdata outside the `bibtex` record. `entry_fields()` copies it and `format_bibtex()` serializes it, but nothing reads its value, so it affects no other property (§5). |

The fields named in that table and in heading 1 are the complete set labdata
*interprets* from a `.bib` entry; everything else falls in the last row.
Verified by enumerating the field names `labdata/parsers/bibtex.py` looks up,
and by the field-loss probe of #69, which re-emits a BibTeX entry from the
document's first-class properties and reports every field name that reached
none (`tests/COVERAGE.md` row `probe.field_loss`).

"Not emitted" throughout that table means *not emitted as a property of the
work*. Every field of the entry, read or not, also survives inside the
`bibtex` record, which is a re-serialization of the entry's data rather than
a set of first-class properties (§5).

**4. Not display text.** Some emitted strings are identifiers or machine
values, and the plain-text rule is beside the point for them: `bib_id`,
`source.key`, `entry_type`, `person_id`, `collaborator_key`, `venue.kind`,
every link `url`, `origin` and `verification.status`, every identifier in
`identifiers`, `resolution.status` and `resolution.method`, the `generator`
record, and every id in `project_ids`, `work_ids` and `people_ids`. Also here
is **`work.bibtex`**, which is a BibTeX record meant to be copied rather than
displayed, and which still contains LaTeX — see §5 for what it does and does
not preserve. `lab` is a YAML mapping rather than a string; its *values* fall
under heading 2.

`work.category` is *not* in this group. It is a label a renderer displays as
a section heading as well as grouping by, so it is display text and heading 2
applies to it in full. Neither is `collaborator.key`: it is an identifier,
but it is built from a name and is explicitly not an assertion about a human
(§5).

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

> **Version note (#18, #56).** Through `schema_version` 3,
> `venue` was composed with Markdown emphasis by
> `format_venue()` — an article in journal `J` published in 2021 yielded the
> string `*J*, 2021` — and it was the only place labdata *generated* markup
> into a text field, as distinct from the YAML strings above, which it merely
> passes through. `schema_version` 4 replaced it with a structured container
> and flat bibliographic properties, so there is nothing left to compose and
> nothing left to generate. `tests/COVERAGE.md` rows `output.no_markup` and
> the two tests behind it assert it: nothing in the demo document is Markdown
> or HTML, and the Markdown punctuation the corpus does carry is input text
> in a property whose value the input supplies. #18 remains open for the
> template side — `| escape`, attribute-safe escaping and the checks on
> rendered output.

---

## 3. Ordering

Every list in the document is covered here. A list not described as ordered
is **unordered**, and a consumer that depends on its order is depending on an
accident.

| List | Order |
|---|---|
| `works` | `year` **descending**, with works that have no year **last**. Ties keep *read order* (below). The sort is the final statement of `labdata.parsers.bibtex.parse_all_works()`. |
| `work.authors` | The order the `author` field wrote them (`labdata.parsers.bibtex.parse_author_list()`). A terminal `and others` is BibTeX's "et al." and is dropped rather than emitted as an author. `position` is that order, 1-based, and counts only the names that reach the document. |
| `work.editors` | The order the `editor` field wrote them, read the same way (`parse_editor_list()`). |
| `work.project_ids` | The order the `project` field wrote them, comma-separated, whitespace trimmed, empty entries dropped (`labdata.parsers.bibtex.parse_project_ids()`). |
| `people` | The order of `people_file`. labdata does not sort people (`labdata.loaders.load_people()`, called by `labdata.assembler.assemble()`). |
| `projects` | The order of `projects_file`, likewise (`labdata.loaders.load_projects()`). |
| `person.work_ids` | The order of the `works` list, filtered to that person's authorships, first occurrence only (`labdata.resolver.compute_backlinks()`). Editors are not authorships and do not appear. |
| `project.work_ids` | The order of the `works` list, filtered to that project, first occurrence only (`compute_backlinks()`). |
| `project.people_ids` | Person id **ascending**, by Unicode code point (`compute_backlinks()` sorts the set it collects). |
| `collaborators` | `last_year` **descending** with `null` last, then `work_count` **descending**, then `key` **ascending** by Unicode code point (the sort in `labdata.assembler.group_collaborators()`; `tests/COVERAGE.md` row `output.collaborators.order`). The key is the final tie-break rather than the name, because two keys can carry the same readable name, so only the key makes the order total. |
| `collaborator.authorships` | The order of the `works` list, then `position` within a work (`group_collaborators()`). |
| `collaborator.work_ids` | The same order, first occurrence only. |
| `collaborator.name_variants` | **Ascending** by Unicode code point. `collaborator.name` is the *first* spelling in document order, which need not be the first variant. |
| `links`, `identifiers` | **Unordered.** They are maps, and a consumer reads them by key and filters the list under it. The list under one key is in the order labdata built it, which is not promised. |
| `lab` | Unordered. It is a YAML mapping copied through; consumers read it by key. |

**Read order** is the order in which entries were parsed: the files in the
order `bib_files` lists them in `lab.yaml`, and within each file, the order
the entries appear in the source. `parse_all_works()` accumulates entries in
that order before sorting. Because the works sort is stable, read order is
the tie-breaker for works of the same year, and it is a promise, not an
accident.

**Ties and missing sort keys.**

- Two works of the same year appear in read order. Two entries with the same
  year in the same file appear in source order.
- A work with **no `year` field has `year: null`** and sorts **last**, which
  is where `year: 0` used to put it. The position is unchanged; what changed
  is that `null` is now distinguishable from a genuine year `0`, and that the
  entry is reported under `BIB-YEAR-MISSING`.
- Two collaborators can only tie through all three keys if they share a key,
  and a key is unique by construction, so the order is total.
- Sorting by "Unicode code point" means `Z` sorts before `a`, and `Ö` sorts
  after `z`. No locale collation is applied.

**Key order within an object is not part of the contract.** The YAML export
writes keys in insertion order (`labdata.exporters.export_to_yaml()` passes
`sort_keys=False`) and the JSON export does the same, but both formats define
objects as unordered and consumers must treat them that way.

**YAML and JSON carry the same document.** `--format yaml` and `--format
json` serialize the identical structure (`labdata.exporters.export_to_yaml()`
and `export_to_json()` both serialize `LabData.to_dict()`); neither is more
authoritative.

**The document is deterministic.** Nothing in it records when it was built:
`generator` carries the compiler's name and version and no timestamp, and a
link's `verification.checked_at` is `null` unless a committed cache supplied
it, because a build never fetches. Two runs over the same inputs with the
same package version produce the same bytes, which is what makes
`tests/corpus/expected/valid.yaml` a reviewable record rather than noise.

---

## 4. Absent versus null

**One policy, refined by the kind of object it applies to.** The refinement
is not a second policy: it is the same rule, read correctly for a container
whose keys are not declared in advance.

> **For a closed object**, every property the schema declares is **always
> present**. A value that does not apply, or was not supplied, is **`null`**.
> An absent key and a `null` key mean the same thing, and consumers must not
> read meaning into the difference.
>
> **Inside an open map** — `lab`, `links`, `identifiers` and every `derived`
> bag — only the keys that have values are present. Emitting nulls over an
> unbounded key set is meaningless: there is no list of the keys that might
> have applied, so "absent" there means exactly "no value", and a consumer
> probes for the key it wants.

A consumer may therefore treat `entry.get("photo")` and `entry["photo"]` as
equivalent on a person, and must not use `"photo" in entry` as a test for
whether a person has a photo. The test is whether the value is `null`. Inside
`links`, the opposite holds: `"pdf" in work["links"]` is exactly the test for
whether the work has a PDF link, and there is no `null` to check.

Two consequences worth stating outright:

- `author.person_id` is `null` when the name matched no person in
  `people_file`. That is an ordinary, expected value, not an error; the
  authorship then carries a `collaborator_key` instead, and exactly one of
  the two is non-null.
- An empty list is `[]`, never `null` and never absent. `project.people_ids`
  for a project with no works is `[]`, and `work.editors` is `[]` for an
  entry that names no editor.

This rule is satisfied by `Author.to_dict()`, `Contributor.to_dict()`,
`Work.to_dict()`, `Person.to_dict()`, `Project.to_dict()` and
`Collaborator.to_dict()`, each of which emits every declared key
unconditionally, and by `LabData.to_dict()`, which always emits `lab`.

> **Version note (#56).** Three deviations existed through `schema_version`
> 3, and each was a bug against the rule above rather than a second policy.
> (a) `Person.to_dict()` emitted only `id`, `name`, `role`, `status`,
> `website` and `publication_count` unconditionally and **omitted** `photo`,
> `email`, `co_advisor`, `start_year`, `publication_ids` and the alumni
> fields whenever their value was falsy, with the alumni fields additionally
> omitted for anyone whose `status` was not `alumni`. (b)
> `Publication.to_dict()` omitted `bibtex` when the entry could not be
> written back out as BibTeX. (c) `LabData.to_dict()` omitted top-level `lab`
> when `lab.yaml` had no `lab` section — and, because it tested the value's
> truthiness rather than its presence, also when `lab.yaml` supplied an empty
> `lab: {}`, so a consumer could not tell "no header" from "an empty header".
> All three are fixed in `schema_version` 4: every declared property is
> present, `bibtex` is `null` when it could not be produced, and `lab` is
> always emitted, `{}` when there is nothing in it. Fixing them changed the
> schema's `required` lists and the nullability of the affected properties,
> which is breaking under §6, which is why they waited for the bump.

**Where "absent" cannot happen at all.** The schema defines the document
itself and each entity type as **closed**: `/additionalProperties` and each
of `/$defs/authorship`, `/$defs/editorship`, `/$defs/work`, `/$defs/person`,
`/$defs/project`, `/$defs/collaborator`, `/$defs/venue`, `/$defs/link`,
`/$defs/resolution`, and the `source` and `generator` objects, set
`additionalProperties: false`. Within those, a property that is not declared
cannot appear, and "absent" always means a declared property with no value.

**The open ones are `lab`, `links`, `identifiers` and `derived`.**
`/properties/lab` declares a handful of properties for documentation only and
keeps `additionalProperties: true`, so any keys whatever validate inside it:
its keys are whatever `lab.yaml` supplied, and a consumer must probe for the
ones it wants rather than expect a fixed set. `/$defs/linkMap` and
`/$defs/identifierMap` constrain the *value* under any key — a list of link
records, a unique list of identifier strings — and leave the key set open, so
a new link kind or identifier scheme is not a breaking change.
`/$defs/derived` constrains nothing; see §5 for who owns it.

## 5. Input versus derived

**Input** fields come from the author's files and labdata carries them
through. **Derived** fields labdata computes. Derived fields are **read-only
outputs**: they must never be written back into `people.yaml`,
`projects.yaml` or a `.bib` file. Doing so makes the next compile read
labdata's own output as input, and a wrong derivation becomes permanent.

| Field | Origin |
|---|---|
| `schema_version` | Derived — a constant of the compiler (`labdata.models.SCHEMA_VERSION`). |
| `generator` | Derived — the compiler's name, its package version and the schema version (`LabData.to_dict()`). No timestamp. |
| `lab` | Input — the `lab` section of `lab.yaml`, copied unchanged (`LabDataConfig.from_yaml()`), and always emitted. |
| `work.bib_id`, `work.source.key` | Input — the BibTeX citation key, **as written**. `labdata.parsers.bibtex.entry_fields()` preserves its case. |
| `work.source.file` | Input — the `name` of the `bib_files` entry the file was listed under, never a path (`parse_all_works()`). |
| `work.entry_type` | Input — the BibTeX entry type, **lowercased** by `entry_fields()`. Of it and `bib_id`, it is the only one that is case-folded. |
| `work.title`, `abstract`, `note` | Input — BibTeX fields, converted from LaTeX to text (§2). `note` additionally has trailing `.` and whitespace trimmed (`labdata.parsers.bibtex.extract_note()`). |
| `work.year` | Input — the BibTeX `year`, as an integer; `null` when the entry supplied none, with a diagnostic (`entry_year()`). |
| `work.category` | Input — the `category` of the `bib_files` entry the file was listed under, not anything in the `.bib` file (`labdata.config.BibFile`, read by `parse_all_works()`). |
| `work.venue` | **Derived** — the first of `journal`, `booktitle`, `school` and `institution` the entry wrote, as `name`, with the `kind` that field and the entry type imply; a preprint's repository when the entry has only an `eprint`; `null` when it names no container (`labdata.parsers.bibtex.build_venue()`). See below. |
| `work.volume`, `number`, `pages`, `series`, `edition`, `publisher`, `address`, `organization`, `chapter`, `month`, `howpublished`, `type` | Input — the BibTeX fields of those names, under BibTeX's names and with BibTeX's meanings (`FLAT_FIELDS`, read in `entry_to_work()`). Those in `TEXT_FIELDS` are converted from LaTeX (§2); the rest are emitted as written. |
| `work.identifiers` | **Derived** — a map from scheme to identifiers, built from `doi`, `eprint` with `archivePrefix`, `isbn` and `issn` (`build_identifiers()`). A `doi` written as a resolver URL has that prefix taken off. |
| `work.links` | **Derived** — a map from kind to link records, built from the entry's `url`, from `pdf_base_url` and from the identifiers above (`build_links()`). See below. |
| `work.project_ids` | Input — the `project` field, split on commas (`parse_project_ids()`). |
| `work.bibtex` | **Derived** — the entry re-serialized as BibTeX, or `null` when that failed (`format_bibtex()`). See below. |
| `author.given`, `von`, `family`, `suffix`, `literal` | Input — the parts BibTeX split the name into, converted from LaTeX, with an equal-contribution marker removed (`person_name_parts()`). An entry writing `Brown, B.` yields `given: "B."`, and that is correct, not a gap. |
| `author.name` | **Derived** — the parts joined in reading order (`readable_name()`). *A readable form of the input name, not a citation form*: it does not abbreviate, expand or normalise. |
| `author.position` | **Derived** — where the authorship sits in its work's list, 1-based, counting only the names that reach the document. |
| `author.person_id` | **Derived** — the resolver's match against `people_file` (`labdata.resolver.resolve_authors()`). |
| `author.collaborator_key` | **Derived** — the key of the grouping an unresolved authorship fell into (`labdata.assembler.group_collaborators()`). Exactly one of it and `person_id` is non-null. |
| `author.resolution` | **Derived** — `status` over `resolved` and `unresolved`, and `method` over `exact` and `fuzzy`, or `null` when nothing matched (`resolve_authors()`). Both are open strings. |
| `author.equal_contribution` | **Derived** — whether the entry wrote a `*` marker on any part of the name (`labdata.parsers.bibtex.marks_equal_contribution()`). |
| `work.editors[*]` | The same, minus `collaborator_key` and `equal_contribution`. An editor that matched nobody is simply `person_id: null` (`parse_editor_list()`). |
| `person.*` except the two below | Input — the fields of `people_file` (`labdata.loaders.load_people()`). `aliases` is read for matching and is **not** emitted. |
| `person.work_ids`, `work_count` | **Derived** — back-links over authorships, and their count (`labdata.resolver.compute_backlinks()`). Editors are not authorships and are not counted. |
| `project.id`, `title`, `description`, `website`, `status` | Input — the fields of `projects_file` (`labdata.loaders.load_projects()`). |
| `project.work_ids`, `people_ids` | **Derived** — back-links, and the people reached through them (`compute_backlinks()`). |
| `collaborators` | **Derived, entirely** — see below (`labdata.assembler.group_collaborators()`). |
| `derived` | Reserved for labdata; empty today. See below. |

### Six derived regions that need more than a row

**`work.venue` normalises across entry types, and is `null` when it cannot.**
`build_venue()` takes the first of `journal`, `booktitle`, `school` and
`institution` that the entry wrote, in that order, as the venue's `name`.
The `kind` follows from the field, and for `booktitle` from the entry type as
well: `journal` for a journal, `conference` for `@inproceedings`,
`@conference` and `@proceedings`, `book` for `@incollection`, `@inbook` and
`@book`, `other` for any other entry type carrying a `booktitle`, and
`institution` for a `school` or an `institution`. An entry with none of the
four but with an `eprint` gets `{kind: "repository", name: <archivePrefix>}`,
defaulting to `arXiv`, because the repository is what the preprint's
container is. Anything else gets `null`: labdata does not invent a container
the entry did not name. `kind` is an **open string**, deliberately not a JSON
Schema enum, so a new work type (#31) needs no version bump.

**`work.links` keeps a link that failed verification, and says so.**
`build_links()` files links by kind — `url` and `video` from the entry's own
`url` field, with `origin: input`; `pdf` from `pdf_base_url`; `doi` and
`arxiv` built from the identifiers — and each record carries
`{url, label, origin, verification}`. `origin` is an open string over
`input`, `sidecar`, `enrichment`, `inferred` and `derived`, and only `input`
means the entry's own field supplied the link. `verification.status` is
`unchecked`, `verified` or `missing`.

**A build never fetches.** `verification` is set only from a local filesystem
check or from a committed cache, never from a network fetch, because a fetch
would cost determinism and make the document depend on the weather. So a
local `pdf_base_url` yields `verified` or `missing`, a remote one yields
`unchecked`, and `checked_at` is `null` in every case v4 produces — only a
committed cache could supply a time. Three states replace a null: "no base
configured" is no link at all, "the file is not there" is `missing`, and
"nobody has looked" is `unchecked`. Verifying a remote link is #20.

A link does **not** name the identifier it was built from. That is redundant
with its kind and its origin, and it would be a cross-record constraint JSON
Schema cannot express and labdata would have to police by hand.

**`work.bibtex` is re-serialized, not verbatim.** It is produced by
`format_bibtex()`, which calls pybtex's `Entry.to_string("bibtex")` on the
*parsed* entry. What survives is the set of fields and their values. What does
**not** survive is how they were written: field order, brace-versus-quote
delimiters, whitespace and indentation are all the serializer's, and
`@string` macros are gone — a field written `journal = j` comes back as
`journal = "Expanded Journal"`. Verified directly.

It is produced *before* LaTeX conversion, so LaTeX markup is still present.
Read it as "the entry's data, re-typeset", not as "the entry as the author
wrote it", and never as a source of properties: nothing in labdata reads a
value back out of it, and a consumer probe that mined it would prove nothing
about the document (§1).

**`collaborators` is a grouping over unresolved authorships, not a list of
people.** `group_collaborators()` walks every work's authorships and, for
each one with no `person_id`, computes a key and files the occurrence under
it. What that buys, and what it does not:

- **The authorship is the primary contributor record.** It is addressed by
  `(work.bib_id, author.position)`, both emitted, with no hash and no new
  identifier, so two people who write their names identically are never
  merged at this level. `collaborator.authorships` lists the occurrences each
  key grouped, so **a consumer that distrusts the grouping can ignore it and
  work from occurrences.** That property is what makes the grouping safe to
  publish.
- **`key` is a lookup key, not an identity.** A name-derived value used as an
  *id* is a human-identity claim however it is described, because that is how
  consumers use it — a template writes `/collaborators/{{ id }}` and the
  disclaimer never reaches the reader. The key is a readable slug of the
  normalised name plus an **always-present** short digest of
  `name_kind + NUL + normalized_name`, for example `rachel-ross-0797b357`.
  The digest is always there rather than added on collision, so adding an
  unrelated collaborator can never change an existing key. A name that leaves
  no slug behind is keyed on the digest alone.
- **People and collaborators occupy separate namespaces.** A graph writes
  `person:aadams` and `collaborator:rachel-ross-0797b357`, never both under
  `person:`. An unresolved string is never labelled a person.
- **`grouped_by` names the policy.** It is `normalized_name` in v4, and an
  open string, so #25 can emit `explicit` or `orcid` without a bump.
- **`name_kind` is `personal` or `literal`, not `person`/`organization`.**
  Brace protection in BibTeX means "do not parse this", which covers
  organisations but also mononyms, so the document must not assert
  corporate-ness.
- **`work_count` is deduplicated per work; `authorship_count` counts
  occurrences.** One work listing two authorships under one key contributes
  `1` and `2` respectively.
- **The policy is #24's.** v4 ships today's policy against the new full-name
  key, which removes most of the merge risk for free but also over-splits:
  one person written `Priya Patel` on two works and `P. Patel` on a third is
  two keys. Both rates are policy, and #24 tunes them. What v4 adds is that
  the remaining risk is **reported** rather than silent:
  `ID-GROUPING-SPANS-SPELLINGS` when one key grouped more than one spelling,
  and `ID-GROUPING-INITIALS-AMBIGUOUS` when an initials-only key could be any
  of several fuller ones.

**`derived` is labdata's, and it is not an extension mechanism.** Every
closed entity carries a `derived` object with `additionalProperties: true`.
Every key inside it is **reserved for labdata**. Consumers must tolerate keys
they do not know — that is the point of it — and must not write their own,
because a key they invent can collide with one labdata adds later. A key
**graduating out of `derived` into a named property is still a major
change**, for the same reason any new property is: the entity is closed. It
is **not** a general extension mechanism and not a place to park data the
schema declined to model; §8 says why there is no such mechanism. Today every
`derived` bag is `{}` in both the demo and the corpus, and
`tests/COVERAGE.md` row `output.derived_is_empty` asserts it so the region
cannot quietly fill.

**Unknown project ids are kept, not dropped.** A `project_ids` entry naming no
project in `projects_file` stays on the work so the problem stays visible, and
`--validate` reports it and exits `1`
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

- **Adding, removing or renaming a property** of any closed object — the
  document itself and each entity type (§4). *Adding* is breaking there
  because those objects set `additionalProperties: false`, so a consumer
  validating against the previous version rejects a document carrying a new
  key. That includes a new **top-level** property beside `works`, `people`,
  `projects` and `collaborators`: the document is closed too, so a new entity
  collection is a breaking change on its own. **Inside an open map this does
  not hold**: `lab`, `links`, `identifiers` and every `derived` bag declare
  no key set, and adding a key there breaks no conforming consumer. Giving
  one of them a declared structure would itself be breaking, because it would
  close a door that is currently open.
- **Changing a type**, including making a string an object or a scalar a list.
- **Changing nullability** — a property that could not be `null` now can, or
  the reverse.
- **Changing requiredness** — moving a property into or out of a `required`
  list such as `/$defs/work/required`.
- **Changing meaning** while keeping the name and type.
- **Changing an identifier or a relationship** — how `bib_id` or a person
  `id` is formed, what `work_ids` points at, or which namespace a reference
  addresses.
- **Changing an order that §3 promises.** Reordering `works`, or moving where
  a work with no year lands, is breaking. Changing the order of a list §3
  calls unordered is not.

**A minor change does not increment it.** Minor changes are those that leave
every conforming document conforming and every conforming reading correct:
new CLI flags, new diagnostics, faster or clearer implementations,
documentation, and bug fixes whose output was already non-conforming. A new
value of an open string — a `venue.kind`, a link `origin`, a
`resolution.status`, a `grouped_by` — is minor by construction, which is why
those vocabularies are documented here rather than enumerated in the schema.

### What a schema version freezes, and what it does not

**A schema version freezes the *shape*, the *target namespace*, the *meaning*
and the *guarantees* of a relationship — not every result an implementation
produces.** `author.person_id` is frozen as "the id of a person in
`people.yaml`, or null": its type, the namespace it points into, and the
promise that it is never widened to reach anything else. It is **not** frozen
as "whichever person labdata matched on the day version 4 shipped".

So a **resolver correction** — a change that makes the matcher better satisfy
the documented matching policy, without changing the shape, the namespace or
the meaning of the relationship — is a package-level behaviour change
recorded as a **Version note** here, not a `schema_version` bump. A consumer
that needs byte-identical compilation pins the **package** version; one that
needs to read the document pins `schema_version`. The two are independent, and
this is why.

The precedent is already in this file. PR #61 changed what `--unresolved`
prints when no `people_file` is configured, and PR #64 made duplicate citation
keys an error where they had been invisible; both changed behaviour a user
could observe, both are recorded above as Version notes, and neither
incremented `schema_version`. The same reading is what lets #24 change how
authors resolve without a fifth version.

What that does **not** license: changing `person_id` to point at a
collaborator, making it a list, allowing it to carry something other than a
person's id, or reordering a list §3 promises. Those are shape, namespace,
meaning and guarantees, and each of them is a bump.

**Published schemas are immutable and live at versioned paths.** A schema that
has been published is never edited. Version `N`'s schema stays reachable, byte
for byte, at its own path after version `N+1` ships, so a consumer pinned to
`N` keeps a stable target. `schema/v3/output.schema.json` and
`schema/v4/output.schema.json` are those paths, and
`tests/COVERAGE.md` row `output.versioned_schema` asserts that the older one
still resolves and still says `3`.

**The `$id` is a pinned tag URL.** v4's `$id` is
`https://raw.githubusercontent.com/siddhss5/labdata/schema-v4/schema/v4/output.schema.json`.
The rule that makes it a contract rather than a guess: **the `schema-v4` tag
is created when this version ships and is never moved.** A branch URL such as
`blob/main` is not usable — it serves an HTML page rather than the schema, so
no consumer can ever have resolved v3's `$id` — and this repository's Pages
deploy is not usable either, because #57 removes it. A commit SHA would be
genuinely immutable rather than immutable by convention, but a commit cannot
reference its own SHA, so the file that introduces a version cannot carry one;
the tag is the closest thing that can be written down at the time the file is
written. Each later version gets its own tag, at its own path, under the same
rule.

**Version history**, as recorded in the comment above
`labdata.models.SCHEMA_VERSION`:

| `schema_version` | Change |
|---|---|
| 1 | The original document. |
| 2 | Authors carry their structured name parts (#23). Breaking: the object is closed, so a v1 consumer rejects the new keys. |
| 3 | Authors carry `equal_contribution` (#46). Breaking, for the same reason. |
| 4 | One consolidated breaking change (#56): `publications` becomes `works`, the bibliography is structured, `links` and `identifiers` are open registries, `collaborators` is a declared grouping over unresolved authorships, every closed object declares every property it can carry, and `crossref` is rejected (#65). |

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
schema_version, generator, lab, people, works, projects,
collaborators (a derived grouping)
```

`lab` is the one entity labdata does not compute anything from. It is kept
deliberately: a document needs a header, and it is where contact information
lives.

The boundary is a finding, not an omission. The project's stated evidence is
two independent surveys of real academic lab websites — 27 groups and 18
groups, spanning robotics, biology, chemistry, physics, economics and public
health, across six countries — which found only three content types at or
above **85% prevalence**: people, works, and projects or research
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
| Press and media coverage | A typed link on the work it covers: `links` is an open map from kind to links, so #27 adds the kind without a version bump. |
| Galleries, photos and videos | Your site repository; a video already reaches the document as a link of kind `video`. |
| Awards and honours | An attribute of the work, today `work.note`; #27 moves it out of `note`. |
| Funding and grants | Your site repository. Nothing in the document depends on it. |
| Software and datasets | Not a separate collection — they are kinds of *work*, added by #31. |
| Alumni | Not a collection — a `status` on a person (`labdata.models.Person.status`). |
| Robots, platforms, facilities | Your site repository; one of 27 surveyed sites had such a page. |

**There is no generic extension mechanism and no `collections` escape hatch.**
What one would carry is mostly prose, and its one real service — catching
references that point at nothing — is delivered by #58 without the document
owning the payload. `derived` is not that hatch either: it is labdata's own
(§5), and the open maps `links` and `identifiers` are open over *their own*
vocabularies, not over arbitrary content.

---

## 9. What this file is not

It does not list the document's fields; `schema/v4/output.schema.json` does.
It does not describe the Jekyll templates in `site/`, which are one
downstream consumer and move to their own repository in #57. It does not describe the input formats `lab.yaml`,
`people.yaml` and `projects.yaml` beyond what §5 needs; schemas for those are
#37.

`tests/COVERAGE.md` is the case-by-case record of what labdata does with each
input, with the fixture and the test for each. Where it and this file disagree
about current behaviour, `tests/COVERAGE.md` is the one backed by a test.
