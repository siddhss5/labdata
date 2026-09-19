# Supported cases

Every case labdata supports, and every case it does not, with the fixture that
holds the input and the test that checks the behavior. The corpus is fictional
throughout (`tests/corpus/`); no real lab data is used anywhere.

## How to read this table

| Column | Meaning |
|---|---|
| Case | A stable ID. Fixtures mark it with `% CASE <id>` in a `.bib` file, or `# CASE <id>` in a YAML file. |
| Input | The input form, as it appears in the fixture. |
| Expected | What labdata is expected to do with it. |
| Fixture | The file holding the input. |
| Test | The assertion. `tests/conformance/` runs labdata only through `cli.main()` and the assembler. |
| Status | `pass` today, or `xfail #N` when the row describes behavior that issue #N still has to deliver. |

Input labdata does not support has a row too, and its expected behavior is a
warning or an error. Silently ignoring an input is never correct.

`tests/conformance/test_coverage_table.py` fails if a row has no `CASE` marker
in its fixture, if its test does not name the case, or if its status disagrees
with the `xfail` markers in the tests. `xfail` markers are `strict=True`, so
the case turns red once the linked issue is fixed and the marker is stale.

Cases that fail today are not fixed here (that is the linked issue's job):
#18 (LaTeX to plain text), #20 (unverified PDF links), #21 (one `@string`
summary), #22 (`--unresolved` with no people file), #23 (parser swap),
#24 (structured-name matching), #26 (precise diagnostics), #27 (explicit link
and award fields), #28 (`keywords` project tags).

## `@string` macros and BibTeX structure
Rule: when a macro is defined more than once, **the last definition wins**, as
in BibTeX itself. `strings.bib` defines `rss`, `cfx` and `jfx` twice each, and
the second definition is the one that reaches the output.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `strings.macro` | `booktitle = rss`, with `@string{rss = ...}` | The macro is expanded into the venue | `tests/corpus/valid/strings.bib` | `test_valid_corpus.py::test_strings` | pass |
| `strings.repeat_last_wins` | `rss` defined twice | The last definition is used; the first never appears in the output | `tests/corpus/valid/strings.bib` | `test_valid_corpus.py::test_strings` | pass |
| `strings.redefined_report` | Three macros redefined in one file | One summary message names all three; nothing is printed for macros defined once | `tests/corpus/valid/strings.bib` | `test_valid_corpus.py::test_redefined_strings_reported_once` | xfail #21 |
| `strings.concat` | `"Joined " # "Title"` and `"Proceedings of the " # cfx` | The parts are concatenated, macros expanded | `tests/corpus/valid/strings.bib` | `test_valid_corpus.py::test_strings` | pass |
| `strings.macro_journal` | `journal = jfx # " Letters"` | The journal is the expanded macro plus the literal suffix | `tests/corpus/valid/strings.bib` | `test_valid_corpus.py::test_strings` | pass |
| `strings.undefined` | `booktitle = nosuchmacro`, which no `@string` defines | Warning naming the file, key, field and macro; the entry and its neighbours are kept | `tests/corpus/invalid/undefined_string/macro.bib` | `test_invalid_corpus.py::test_kept` | xfail #23, #26 |
| `structure.comment_lines` | A `%` comment line between entries | Ignored; the entries around it are read | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_comments_and_preamble_are_not_publications` | pass |
| `structure.comment_entry` | `@comment{...}` wrapping something that looks like an entry | Not a publication; the entries around it are read | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_comments_and_preamble_are_not_publications` | pass |
| `structure.preamble` | `@preamble{"..."}` | Not a publication; the entries around it are read | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_comments_and_preamble_are_not_publications` | pass |
| `structure.uppercase` | `@ARTICLE` with `TITLE`, `AUTHOR`, `JOURNAL`, `YEAR` | Read exactly as the lower-case spelling is | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `structure.value_quoted` | Field values in `"quotes"` | Read like braced values | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `structure.value_braced` | Field values in `{braces}`, including a doubly braced title | Read; the braces themselves never reach the output | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `structure.value_numeric` | Unquoted numeric `year`, `volume`, `number` | Read like quoted values | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `structure.crossref` | A child entry with `crossref` to a `@proceedings` parent | Missing fields come from the parent: the parent's year, and its title as the booktitle | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | xfail #23 |
| `structure.bom_crlf` | A file with a UTF-8 BOM and CRLF line endings | Read normally; the BOM is not part of the first key, accents still decode | `tests/corpus/valid/encoding.bib` | `test_valid_corpus.py::test_structure` | pass |
| `structure.unclosed_brace` | An entry whose `title` brace is never closed | Warning naming the file and key; the entries before and after it are still read | `tests/corpus/invalid/unclosed_brace/broken.bib` | `test_invalid_corpus.py::test_kept` | xfail #26 |
| `structure.duplicate_key_file` | The same citation key twice in one file | Error naming the file and the repeated key | `tests/corpus/invalid/duplicate_key_same_file/dup.bib` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `structure.duplicate_key_across` | The same citation key in two files | Error naming both files and the repeated key | `tests/corpus/invalid/duplicate_key_across_files/first.bib` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `structure.missing_year` | An entry with no `year` | Warning naming the file, key and field | `tests/corpus/invalid/missing_year/noyear.bib` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `structure.year_not_number` | `year = {in press}` | Warning naming the file, key and field; the entry and its neighbours are kept | `tests/corpus/invalid/year_not_number/badyear.bib` | `test_invalid_corpus.py::test_reports` | xfail #26 |
| `structure.missing_journal` | An `@article` with no `journal` | Warning naming the file, key and field; the entry is kept | `tests/corpus/invalid/missing_journal/nojournal.bib` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `structure.missing_booktitle` | An `@inproceedings` with no `booktitle` | Warning naming the file, key and field; the entry is kept | `tests/corpus/invalid/missing_booktitle/nobooktitle.bib` | `test_invalid_corpus.py::test_exit` | xfail #26 |

## Entry types
Every type labdata has a venue rule for, plus one it does not.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `types.article` | `@article` with `journal`, `volume`, `number` | Venue: journal, volume(number), year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.inproceedings` | `@inproceedings` with `booktitle` | Venue: booktitle, year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.phdthesis` | `@phdthesis` with `school` | Venue: PhD thesis, school, year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.mastersthesis` | `@mastersthesis` with `school` | Venue: Masters thesis, school, year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.techreport` | `@techreport` with `type`, `number`, `institution` | Venue: type and number, institution, year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.techreport_default` | `@techreport` with only `institution` | Venue: a default report label, institution, year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.misc_arxiv` | `@misc` with `eprint` | Venue: the arXiv identifier and year | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.misc` | `@misc` with no venue fields | Venue: the year alone | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `types.unsupported` | `@book`, a type labdata has no venue rule for | Warning naming the file, key and type; the entry is kept | `tests/corpus/invalid/unsupported_entry_type/book.bib` | `test_invalid_corpus.py::test_reports` | xfail #26 |

## Fields read
Every BibTeX field labdata reads. Fields it does not read (`pages`,
`publisher`, ...) are still preserved in the copyable `bibtex` output field.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `fields.journal` | `journal` | Shown in the venue | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.volume` | `volume` | Shown in the venue | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.number` | `number` | Shown in the venue | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.booktitle` | `booktitle` | Shown in the venue | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.school` | `school` | Shown in the venue of a thesis | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.institution` | `institution` | Shown in the venue of a report | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.type` | `type` | Shown in the venue of a report | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.eprint` | `eprint` | Becomes `arxiv_url` | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.archiveprefix` | `archivePrefix = {arXiv}` | Confirms `eprint` is an arXiv identifier | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.doi` | `doi` | Becomes `doi_url` | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.url` | `url` | Becomes `video_url` for a known video host, otherwise `url` | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.project` | `project = {homebot}` | Becomes `project_ids` | `tests/corpus/valid/projects.bib` | `test_valid_corpus.py::test_structure` | pass |
| `fields.unread` | `pages` and `publisher`, which labdata does not read | Not dropped: they stay in the `bibtex` field | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_structure` | pass |

## Name forms
Author names as they appear in `.bib` files. `name` below is the `authors[].name`
field of the output.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `names.last_first` | `Adams, Alice` | Name `A. Adams`, resolved to the person | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.first_last` | `Bob Brown` | Name `B. Brown`, resolved to the person | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.particle_last_first` | `van den Berg, Victor` | The particle stays with the surname: `V. van den Berg` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.particle_first_last` | `Rupert de la Cruz` | The particle stays with the surname: `R. de la Cruz` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #23 |
| `names.suffix` | `Smith, Jr., John` | The suffix is kept and is not mistaken for a given name | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #23 |
| `names.corporate` | `{Example Robotics Consortium}` | Kept as one name, without its braces, and not abbreviated | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #23 |
| `names.corporate_escaped` | `{AT\&T Research}` | Kept as one name, with `\&` decoded to `&` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #23 |
| `names.hyphenated` | `Green, Grace-Ann` | Both halves of the given name are kept: `G.-A. Green` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #23 |
| `names.accent_tex` | `C{\^o}t{\'e}, Carol` | Name `C. Côté`, resolved to the person | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.accent_utf8` | `Côté, Carol` in raw UTF-8 | Same output as the TeX spelling, resolved to the same person | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.others` | `... and others` | The real authors are resolved; `others` is not emitted as an author | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #23 |
| `names.equal_contribution` | `Brown, Bob$^{*}$ and Davis, Dave*` | The marker does not corrupt the name or block resolution | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.equal_contribution_marker` | `$^{*}$` and a trailing `*` on author names | The output records which authors are marked as contributing equally | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #46 |
| `names.same_initial_alex` | `Kim, Alex`, who declares the alias `A. Kim` | Resolves to `akim` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `names.same_initial_alan` | `Kim, Alan`, who declares no alias | Resolves to `alankim`, not to the other Kim | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #24 |
| `names.initials_ambiguous` | `Kim, A.`, which fits both Kims | Not resolved to either; listed for a human to resolve | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #24 |

## Identity resolution
Every way an author name can be matched to a person, and what happens when it
cannot be.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `identity.alias` | A name matching a declared `aliases` entry | Resolved to that person | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_names` | pass |
| `identity.full_name` | A full name matching `name`, with no aliases declared | Resolved to that person | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #24 |
| `identity.normalized` | `DAVIS, D` — different case and punctuation | Resolved: matching ignores case, accents and periods | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `identity.fuzzy` | `Davis, Dave M.`, close to a person's name but not equal | Not auto-linked; reported as a suggestion for a human | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | xfail #24 |
| `identity.external` | A co-author who is in no people file | Left unresolved and counted as a collaborator | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_names` | pass |
| `identity.ambiguous_alias` | Two people declaring the same alias | Warning naming both ids and the alias; the name resolves to neither | `tests/corpus/invalid/ambiguous_alias/people.yaml` | `test_invalid_corpus.py::test_reports` | xfail #26 |

## LaTeX and text
Titles, abstracts and notes are meant to reach the site as plain Unicode text,
with `$...$` math left as TeX for KaTeX or MathJax. Markdown metacharacters in
the source text are not markup and must survive unchanged.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `latex.textbf` | `A \textbf{Bold} Claim` | Plain text `A Bold Claim`, with no Markdown `**` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #18 |
| `latex.nested` | `\textbf{a {B} c}` and `\emph{d \textbf{e} f}` | Plain text, with the nested braces and macros resolved | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #18 |
| `latex.accent_braced` | `Caf{\'e}` and `M{\"u}nchen` | `Café` and `München` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.caron_space` | `Ha{\v c}ek on {\v c}` | `Haček on č` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.dotless_i` | `Mar\'\i a` | `María` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.ampersand` | `Pick \& Place` | `Pick & Place` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.percent` | `A 50\% Speedup` | `A 50% Speedup` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.underscore` | `robot\_arm` | `robot_arm` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.endash` | `1--10` | `1–10` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.emdash` | `Robots---and People` | `Robots—and People` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.quotes` | ` ``Tidy'' ` | Typographic quotes `“Tidy”` | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #23 |
| `latex.star_braced` | `{RRT}*` | `RRT*`: the star is kept and the braces are dropped | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.star_plain` | `BIT*` | `BIT*`: the star is kept | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.star_braced_whole` | `{BIT*}` | `BIT*`: the star is kept | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.math` | `$O(n \log n)$` | Left as TeX, delimiters and all, for the renderer | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.html_special` | `< > & " '` in a title | Kept as characters in the data; escaping is the renderer's job | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.markdown_punctuation` | `[a link](x)`, `` `code` ``, `# heading`, `*emphasis*` | Kept verbatim: they are text, not markup | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.unicode_raw` | Raw CJK and emoji | Passed through unchanged | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.abstract` | An abstract with accents, math and `\emph` | Same rules as a title: plain text with math left as TeX | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | xfail #18 |
| `latex.note_href` | `note = {Code at \href{url}{our site}}` | The link and its text both survive; the entry is never dropped | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_latex` | pass |
| `latex.unknown_macro` | `\fictionalmacro{Strange}` | Warning naming the file, key and field; the text is kept, not silently mangled | `tests/corpus/invalid/unknown_macro/macro.bib` | `test_invalid_corpus.py::test_reports` | xfail #26 |

## Links

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `links.doi_bare` | `doi = {10.5555/corpus.0001}` | `doi_url` is the DOI resolver URL | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.doi_url` | `doi = {https://doi.org/10.5555/corpus.0002}` | Same URL, not doubled up | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.arxiv_prefixed` | `eprint` with `archivePrefix = {arXiv}` | `arxiv_url` points at the abstract page | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.arxiv_unprefixed` | `eprint` with no `archivePrefix` | `arxiv_url` points at the abstract page | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.youtube` | `url` on youtube.com | Becomes `video_url`, not `url` | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.vimeo` | `url` on vimeo.com | Becomes `video_url`, not `url` | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.url` | `url` on any other host | Becomes `url`, not `video_url` | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.pdf.local_present` | `pdf_base_url` is a local directory holding `<key>.pdf` | `pdf_url` points at the file | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.pdf.local_missing` | `pdf_base_url` is a local directory with no `<key>.pdf` | `pdf_url` is null: no button for a file that is not there | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | pass |
| `links.pdf.remote_guess` | `pdf_base_url` is a remote URL, nothing says the PDF exists | No guessed `pdf_url` for an unverified paper | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_remote_pdf_url_not_guessed` | xfail #20 |
| `links.note_link_award` | A `note` holding both an `\href` and an award | Both survive; the award is available as its own field | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_links` | xfail #27 |

## Projects

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `projects.single` | `project = {homebot}` | One project id; the project back-links the paper | `tests/corpus/valid/projects.bib` | `test_valid_corpus.py::test_projects` | pass |
| `projects.multiple` | `project = {homebot, sharedarm}` | Both ids, in source order; both projects back-link the paper | `tests/corpus/valid/projects.bib` | `test_valid_corpus.py::test_projects` | pass |
| `projects.none` | No project tag | Empty `project_ids` | `tests/corpus/valid/projects.bib` | `test_valid_corpus.py::test_projects` | pass |
| `projects.keywords` | `keywords = {project:sharedarm, manipulation}` | The namespaced keyword is read as a project tag | `tests/corpus/valid/projects.bib` | `test_valid_corpus.py::test_projects` | xfail #28 |
| `projects.undefined` | A tag no `projects.yaml` entry defines | Error naming the file, key, field and tag; `--validate` exits non-zero | `tests/corpus/invalid/undefined_project/tagged.bib` | `test_invalid_corpus.py::test_reports` | xfail #26 |
| `projects.duplicate_id` | The same project id twice in `projects.yaml` | Error naming the file and the repeated id | `tests/corpus/invalid/duplicate_project_id/projects.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `projects.invalid_status` | `status: sometimes` | Warning naming the file, project and field | `tests/corpus/invalid/invalid_project_status/projects.yaml` | `test_invalid_corpus.py::test_reports` | xfail #26 |

## People file

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `people.duplicate_id` | The same person id twice in `people.yaml` | Error naming the file and the repeated id | `tests/corpus/invalid/duplicate_person_id/people.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `people.invalid_role` | `role: wizard`, outside the roles the site groups by | Warning naming the file, person and field | `tests/corpus/invalid/invalid_person_role/people.yaml` | `test_invalid_corpus.py::test_reports` | xfail #26 |
| `people.invalid_status` | `status: retired`, neither current nor alumni | Warning naming the file, person and field | `tests/corpus/invalid/invalid_person_status/people.yaml` | `test_invalid_corpus.py::test_reports` | xfail #26 |
| `people.missing_name` | A person with an `id` but no `name` | Error naming the file, the person and the missing field | `tests/corpus/invalid/people_missing_name/people.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `people.not_a_list` | A mapping where labdata expects a list of people | Error naming the file | `tests/corpus/invalid/people_not_a_list/people.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |

## Config keys
Every key of `lab.yaml`, present, missing and wrong-typed. Wrong-typed and
missing-file cases each live in their own `tests/corpus/invalid/` folder.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `config.lab.present` | A `lab:` section | Copied into the output as `lab` | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_present` | pass |
| `config.lab.missing` | No `lab:` section | Accepted; the output has no `lab` key | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_lab_missing` | pass |
| `config.lab.wrong_type` | `lab: "Corpus Lab"`, a string | Error naming the file and the key | `tests/corpus/invalid/config_lab_type/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.site` | A `site:` section, read by the site config script | Accepted by labdata and not copied into the output | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_present` | pass |
| `config.bib_dir.present` | `bib_dir: "."` | The `.bib` files are read from that directory | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_present` | pass |
| `config.bib_dir.missing` | No `bib_dir` | Error naming the missing key | `tests/corpus/invalid/config_bib_dir_missing/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.bib_dir.wrong_type` | `bib_dir` as a list | Error naming the file and the key | `tests/corpus/invalid/config_bib_dir_type/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.bib_files.present` | `bib_files` with a name and category each | Each file is read and its category lands on every publication in it | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_present` | pass |
| `config.bib_files.missing` | No `bib_files` | Warning naming the key; an empty publication list is not silently normal | `tests/corpus/invalid/config_bib_files_missing/lab.yaml` | `test_invalid_corpus.py::test_reports` | xfail #26 |
| `config.bib_files.wrong_type` | `bib_files` as a string | Error naming the file and the key | `tests/corpus/invalid/config_bib_files_type/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.bib_files.name_missing` | A `bib_files` entry with no `name` | Error naming the file, the section and the missing key | `tests/corpus/invalid/config_bib_file_no_name/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.bib_files.category_missing` | A `bib_files` entry with no `category` | Error naming the file, the section and the missing key | `tests/corpus/invalid/config_bib_file_no_category/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.bib_files.not_found` | A `bib_files` entry naming a file that is not there | Error naming the missing file | `tests/corpus/invalid/bib_file_not_found/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.pdf_base_url.present` | `pdf_base_url` pointing at a local directory | PDF links are built from it | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_pdf_base_url_present` | pass |
| `config.pdf_base_url.missing` | No `pdf_base_url` | Accepted; no publication gets a `pdf_url` | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_pdf_base_url_missing` | pass |
| `config.pdf_base_url.wrong_type` | `pdf_base_url: 42` | Error naming the file and the key | `tests/corpus/invalid/config_pdf_base_url_type/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.people_file.present` | `people_file` pointing at a people list | People are loaded and authors are resolved against them | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_people_file_present` | pass |
| `config.people_file.missing` | No `people_file` | Accepted; every author is a collaborator, and `--unresolved` says resolution is not configured | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_people_file_missing` | xfail #22 |
| `config.people_file.not_found` | `people_file` naming a file that is not there | Error naming the key and the missing file | `tests/corpus/invalid/people_file_not_found/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.people_file.wrong_type` | `people_file` as a list | Error naming the file and the key | `tests/corpus/invalid/config_people_file_type/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.projects_file.present` | `projects_file` pointing at a project list | Projects are loaded and tags are validated against them | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_projects_file_present` | pass |
| `config.projects_file.missing` | No `projects_file` | Accepted; no projects, and project tags are kept on publications | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_config_projects_file_missing` | pass |
| `config.projects_file.not_found` | `projects_file` naming a file that is not there | Error naming the key and the missing file | `tests/corpus/invalid/projects_file_not_found/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.projects_file.wrong_type` | `projects_file` as a list | Error naming the file and the key | `tests/corpus/invalid/config_projects_file_type/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |
| `config.unknown_key` | A misspelled key such as `people_fil` | Warning naming the file and the unknown key | `tests/corpus/invalid/config_unknown_key/lab.yaml` | `test_invalid_corpus.py::test_reports` | xfail #26 |
| `config.not_a_mapping` | A `lab.yaml` holding a list | Error naming the file | `tests/corpus/invalid/config_not_a_mapping/lab.yaml` | `test_invalid_corpus.py::test_exit` | xfail #26 |

## CLI flags and output formats

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `cli.config` | `labdata` with no `--config` | Usage error naming `--config` | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_config_required` | pass |
| `cli.config_not_found` | `--config` naming a file that is not there | Error naming the file; exits non-zero | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_config_not_found` | pass |
| `cli.mode.required` | `--config` alone, with no mode flag | Usage error naming `--output`, `--validate` and `--unresolved` | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_mode_required` | pass |
| `cli.output` | `--output site/_data/lab.yml` | Writes the file, creating parent directories | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_output_creates_parent_dirs` | pass |
| `cli.format.yaml` | `--format yaml`, and the default with no `--format` | YAML holding the same data as `--format json` | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_format` | pass |
| `cli.format.json` | `--format json` | JSON holding the same data as the YAML export | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_format` | pass |
| `cli.format.invalid` | `--format xml` | Usage error naming the bad value; no file is written | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_format_invalid` | pass |
| `cli.validate` | `--validate` | Counts of publications, people and projects, plus any unresolved authors and unknown projects | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_validate` | pass |
| `cli.unresolved` | `--unresolved` | Lists exactly the author names that did not resolve | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_unresolved` | pass |
| `cli.unresolved_none` | `--unresolved` when every author resolves | Lists nobody | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_unresolved_none` | pass |
| `cli.help` | `--help` | Names every flag | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_help` | pass |

## Messages labdata prints
Every message labdata can print on its own behalf. Tests match on the file,
key, field and value in a message, never on its English wording, so rewording
a message does not break them.

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `diag.wrote` | A successful `--output` run | Names the file written and the counts | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_output_creates_parent_dirs` | pass |
| `diag.validation_passed` | `--validate` with nothing wrong | Reports success and exits zero | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_validate` | pass |
| `diag.unresolved_authors` | `--validate` or `--unresolved` with external co-authors | Lists them; unresolved externals are not errors | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_unresolved` | pass |
| `diag.all_resolved` | `--unresolved` with nothing to report | Says so without listing anyone | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_unresolved_none` | pass |
| `diag.unknown_projects` | `--validate` with a tag no project defines | Error listing the tag; exits non-zero | `tests/corpus/invalid/undefined_project/lab.yaml` | `test_invalid_corpus.py::test_exit` | pass |
| `diag.ambiguous_alias` | Two people declaring one alias | One warning naming both person ids | `tests/corpus/invalid/ambiguous_alias/people.yaml` | `test_invalid_corpus.py::test_reports` | pass |
| `diag.config_error` | A `lab.yaml` labdata cannot load | One error message, no traceback; exits non-zero | `tests/corpus/invalid/config_not_a_mapping/lab.yaml` | `test_invalid_corpus.py::test_exit` | pass |
| `diag.config_not_found` | `--config` naming a file that is not there | Names the file; exits non-zero | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_config_not_found` | pass |
| `diag.mode_required` | No mode flag | Names the flags that would be valid | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_mode_required` | pass |
| `diag.format_invalid` | `--format xml` | Names the bad value and the valid ones | `tests/corpus/valid/lab.yaml` | `test_config_cli.py::test_cli_format_invalid` | pass |

## Output fields
Every field of the generated `lab.yml` / `lab.json`, and the checks on the file
as a whole. The structure is defined by
[`schema/output.schema.json`](../schema/output.schema.json).

| Case | Input | Expected | Fixture | Test | Status |
|---|---|---|---|---|---|
| `output.schema_version` | Any run | The output carries `schema_version` | `tests/corpus/valid/lab.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.lab` | A `lab:` section in the config | Copied through to `lab` | `tests/corpus/valid/lab.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.bib_id` | The citation key | `bib_id` | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.title` | `title` | `title`, as plain text | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.authors` | `author` | `authors`: a list of `{name, person_id}`, in source order | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.year` | `year` | `year`, as an integer | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.venue` | The venue fields for the entry type | `venue`, the formatted venue string | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.category` | The `bib_files` category of the file the entry came from | `category` | `tests/corpus/valid/lab.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.entry_type` | The `@type` of the entry | `entry_type`, lower-cased | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.abstract` | `abstract` | `abstract`, or null | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.note` | `note` | `note`, or null | `tests/corpus/valid/latex.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.pdf_url` | A PDF that exists under `pdf_base_url` | `pdf_url`, or null | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.doi_url` | `doi` | `doi_url`, or null | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.arxiv_url` | `eprint` | `arxiv_url`, or null | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.url` | `url` that is not a video | `url`, or null | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.video_url` | `url` on a known video host | `video_url`, or null | `tests/corpus/valid/links.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.project_ids` | `project` or namespaced `keywords` | `project_ids` | `tests/corpus/valid/projects.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.publication.bibtex` | The whole entry | `bibtex`, the copyable source, including fields labdata does not read | `tests/corpus/valid/structure.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.id` | `id` in `people.yaml` | `id` | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.name` | `name` | `name` | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.role` | `role` | `role`, or null | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.status` | `status` | `status` | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.website` | `website` | `website`, or null | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.photo` | `photo` | `photo`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.email` | `email` | `email`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.co_advisor` | `co_advisor` | `co_advisor`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.start_year` | `start_year` | `start_year`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.end_year` | `end_year` on an alumnus | `end_year`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.degree` | `degree` on an alumnus | `degree`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.thesis_title` | `thesis_title` on an alumnus | `thesis_title`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.current_position` | `current_position` on an alumnus | `current_position`, when set | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.publication_count` | Papers the person appears on | `publication_count`, equal to the length of `publication_ids` | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.person.publication_ids` | Papers the person appears on | `publication_ids`, in publication order | `tests/corpus/valid/people.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.id` | `id` in `projects.yaml` | `id` | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.title` | `title` | `title` | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.description` | `description` | `description`, or null | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.website` | `website` | `website`, or null | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.status` | `status` | `status` | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.publication_ids` | Papers tagged with the project | `publication_ids` | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.project.people_ids` | Authors of those papers who are lab members | `people_ids`, sorted | `tests/corpus/valid/projects.yaml` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.collaborator.name` | An author who resolved to nobody | `name` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.collaborator.publication_count` | Papers that name the collaborator | `publication_count` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.collaborator.last_year` | The most recent of those papers | `last_year` | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_output_fields` | pass |
| `output.collaborators.order` | Several collaborators | Sorted by last year, then paper count, then name | `tests/corpus/valid/names.bib` | `test_valid_corpus.py::test_collaborators_order` | pass |
| `output.schema` | The valid corpus output | Validates against the JSON Schema, which rejects unknown fields | `tests/corpus/valid/lab.yaml` | `test_output_format.py::test_valid_corpus_matches_schema` | pass |
| `output.demo_schema` | The Example Lab demo output | Validates against the same schema, in both formats | `examples/demo/lab.yaml` | `test_output_format.py::test_demo_matches_schema` | pass |
| `output.yaml_json_same` | The same run exported twice | The YAML and JSON exports hold the same data | `tests/corpus/valid/lab.yaml` | `test_output_format.py::test_yaml_and_json_hold_the_same_data` | pass |
| `output.full` | The whole valid corpus | Matches `tests/corpus/expected/valid.yaml`, compared as parsed data | `tests/corpus/valid/lab.yaml` | `test_output_format.py::test_full_output` | pass |
