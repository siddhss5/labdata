"""
BibTeX parsing pipeline.

pybtex reads the files — @string macros, BibTeX's own name splitting, entry
order — and this module maps its Entry and Person objects onto labdata's
Publication model: crossref resolution, per-field LaTeX conversion (latex.py),
display rules and diagnostics.

Together with latex.py this is the adapter: no other module imports pybtex or
pylatexenc, and nothing here lets a library object or a library message reach
the rest of labdata.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pybtex.errors
from pybtex.database import Entry, Person
from pybtex.database.input.bibtex import LowLevelParser, Parser as PybtexParser, SkipEntry
from pybtex.scanner import PybtexSyntaxError

from .latex import latex_to_text, strip_braces
from ..models import Author, Publication


# Field values that hold prose and are converted from LaTeX to plain text.
# Everything else (url, doi, eprint, project, ...) is data, and is kept raw.
TEXT_FIELDS = frozenset({
    "title", "abstract", "note", "journal", "booktitle", "school",
    "institution", "type", "series", "publisher", "address", "organization",
})

# A name list ending in "and others" means "et al."; it is not an author.
OTHERS = "others"

# Equal contribution is written as a star on one part of a name, in one of
# these four forms. It is an annotation rather than part of the name, so it is
# taken off the part before the name is read and recorded on the author
# instead. Other author annotations — corresponding author, affiliation
# numbers, daggers — are not read.
#
# A star, caret or dollar written with a backslash in front of it is escaped
# text rather than the start of a marker: `Brown\*` is a name with a star in
# it. The accent in `C{\^o}t{\'e}$^{*}$` is escaped the same way, and the
# marker after it is not, which is how that name keeps working.
_WRITTEN = r"\$\^\{\*\}\$|\^\{\*\}|\\textsuperscript\s*\{\*\}"
_MARKER = rf"(?<!\\)(?:{_WRITTEN}|\*)"

# A marker at the end of a name part, on its own or in a brace group of its
# own: BibTeX grouping such as `Brown{$^{*}$}` protects the marker from the
# name, and does not make it part of it. Only a form that brings its own
# command is unwrapped, because a lone `{*}` is how any other command takes
# its argument — the star in `Brown\^{*}` is an accented star, not a marker.
EQUAL_CONTRIBUTION = re.compile(
    rf"(?:(?<!\\)\{{\s*(?:{_WRITTEN})\s*\}}|{_MARKER})\s*$")

_STRING_DEFINITION = re.compile(r'@string\s*[{(]\s*([^\s=,{}()"]+)\s*=', re.IGNORECASE)

# The command name pybtex is about to read, when that name is `comment`.
_COMMENT_COMMAND = re.compile(r'\s*comment\s*[{(]', re.IGNORECASE)


def _warn(message: str) -> None:
    """Report a problem with an input file in labdata's own voice.

    Parser messages are relayed as the library phrased them: naming the file,
    entry key and field of every diagnostic is #26.
    """
    print(f"Warning: {message}", file=sys.stderr)


# --- Reading the files -------------------------------------------------------

def _redefined_macros(text: str) -> List[str]:
    """The ``@string`` macros this text defines more than once, in source order.

    pybtex takes the last definition, as BibTeX does, and says nothing about
    it. labdata reports it instead of letting a redefinition pass unnoticed.
    Collecting every redefinition of a run into one message is #21.
    """
    seen: set = set()
    repeated: List[str] = []
    for match in _STRING_DEFINITION.finditer(text):
        name = match.group(1).lower()
        if name in seen:
            if name not in repeated:
                repeated.append(name)
        else:
            seen.add(name)
    return repeated


class _CommentSkippingParser(LowLevelParser):
    """pybtex's tokenizer, with a balanced ``@comment{...}`` group stepped over.

    pybtex raises ``SkipEntry`` for ``@comment`` before reading the body, so
    the scanner resumes just inside the group and an entry written there is a
    real entry to it — BibTeX behaves the same way. labdata treats a
    commented-out entry as commented out, so the group is consumed here, at
    the parser's own position and with the parser's own scanner. Nothing else
    in the file is read by labdata, which is why the shape of a value or of a
    neighbouring command cannot be got wrong.

    Only a *balanced* group is consumed. Prose that merely mentions
    ``@comment{`` does not close, so the position is put back and pybtex reads
    the file as it always would: at worst a commented-out entry stays visible,
    never a real entry disappears.
    """

    def parse_command(self):
        # pybtex raises SkipEntry for a @comment, and also for an entry that
        # `wanted_entries` filters out — which leaves the scanner somewhere
        # quite different. Only the first is ours to recover from, so the
        # command is identified before the parser reads it.
        comment = _COMMENT_COMMAND.match(self.text, self.pos) is not None
        try:
            return super().parse_command()
        except SkipEntry:
            if comment:
                position, lineno = self.pos, self.lineno
                if not self._skip_comment_group():
                    self.pos, self.lineno = position, lineno
            raise

    def _skip_comment_group(self) -> bool:
        """Consume the ``@comment`` body just opened. False if it never closes."""
        closing = self.RBRACE if self.text[self.pos - 1] == "{" else self.RPAREN
        while True:
            token = self.skip_to([closing, self.LBRACE])
            if token is None:
                return False
            if token.pattern is closing:
                return True
            try:
                for _ in self.parse_string(self.RBRACE):
                    pass
            except PybtexSyntaxError:
                return False


class _Parser(PybtexParser):
    """pybtex's BibTeX parser, reading ``@comment`` groups as comments.

    ``Parser.parse_string`` names ``LowLevelParser`` directly, so swapping the
    tokenizer means restating that loop. It is the one place labdata touches a
    pybtex internal; ``pybtex~=0.26`` is pinned, which is the mitigation #23
    already names for this.
    """

    def parse_string(self, text: str):
        self.unnamed_entry_counter = 1
        self.command_start = 0
        commands = _CommentSkippingParser(
            text,
            keyless_entries=self.keyless_entries,
            handle_error=self.handle_error,
            want_entry=self.data.want_entry,
            filename=self.filename,
            macros=self.macros,
        )
        for command, arguments in commands:
            kind = command.lower()
            if kind == "preamble":
                self.process_preamble(*arguments)
            elif kind != "string":
                self.process_entry(command, *arguments)
        return self.data


def parse_bibtex_file(path: str) -> Dict[str, Entry]:
    """Parse one BibTeX file into pybtex entries, keyed by citation key.

    Anything the parser has to say is captured and reported by labdata, so no
    library logging reaches the user.
    """
    text = Path(path).read_text(encoding="utf-8-sig")

    for name in _redefined_macros(text):
        _warn(f"@string macro '{name}' is defined more than once; "
              "the last definition is used")

    with pybtex.errors.capture() as errors:
        data = _Parser().parse_string(text)
    for error in errors:
        _warn(str(error))

    return data.entries


# --- pybtex objects → labdata values ----------------------------------------

def _convert(value: str, where: str) -> str:
    """Convert one field from LaTeX, keeping the raw text if that fails."""
    try:
        return latex_to_text(value)
    except Exception:  # noqa: BLE001 - never drop an entry over one field
        _warn(f"{where}: could not read the LaTeX in this field; "
              "keeping the text as written")
        return strip_braces(value)


def _initials(given: str) -> str:
    """Abbreviate one given name: ``Alice`` → ``A.``, ``Grace-Ann`` → ``G.-A.``"""
    parts = [part for part in given.split("-") if part]
    return "-".join(f"{part[0]}." for part in parts)


def _name_parts(person: Person) -> List[str]:
    """Every part of a pybtex name, as written in the file."""
    return (list(person.first_names) + list(person.middle_names)
            + list(person.prelast_names) + list(person.last_names)
            + list(person.lineage_names))


def _without_marker(part: str) -> str:
    """One name part with its equal-contribution markers taken off the end.

    Stripping repeats, because a name written ``Brown$^{*}$*`` carries the
    marker twice and taking one off would leave the other in the name.
    """
    while True:
        stripped = EQUAL_CONTRIBUTION.sub("", part, count=1)
        if stripped == part:
            return part
        part = stripped


def marks_equal_contribution(person: Person) -> bool:
    """True when any part of this name carries an equal-contribution marker.

    Given, family, von and suffix are all read: BibTeX splits the name before
    labdata sees it, so which part the star landed on is the author's choice
    of where to write it, not a different meaning.
    """
    return any(_without_marker(part) != part for part in _name_parts(person))


def _is_others(person: Person) -> bool:
    """``and others``: BibTeX's "et al.", not a person."""
    return (not person.first_names and not person.middle_names
            and not person.prelast_names and not person.lineage_names
            and [name.lower() for name in person.last_names] == [OTHERS])


def _is_literal(person: Person) -> bool:
    """A corporate author: one brace-protected unit, with no given name."""
    return (not person.first_names and not person.middle_names
            and not person.prelast_names and not person.lineage_names
            and len(person.last_names) == 1
            and person.last_names[0].startswith("{")
            and person.last_names[0].endswith("}"))


def person_name_parts(person: Person, where: str) -> Dict[str, Optional[str]]:
    """One pybtex Person as the parts BibTeX split it into, converted to text.

    ``given``, ``von``, ``family`` and ``suffix`` are BibTeX's four parts; a
    corporate name comes back as ``literal`` instead, with the other four
    unset. An empty part is ``None`` rather than ``""``, so the output says
    "this name has no such part" rather than "it is blank".

    An equal-contribution marker is not part of the name and does not appear
    in any part; ``marks_equal_contribution`` reports it separately.
    """
    def text(parts) -> Optional[str]:
        joined = " ".join(_convert(_without_marker(part), where)
                          for part in parts).strip()
        return joined or None

    if _is_literal(person):
        return {"given": None, "von": None, "family": None, "suffix": None,
                "literal": text(person.last_names)}
    return {
        "given": text(person.first_names + person.middle_names),
        "von": text(person.prelast_names),
        "family": text(person.last_names),
        "suffix": text(person.lineage_names),
        "literal": None,
    }


def format_name(parts: Dict[str, Optional[str]]) -> str:
    """The display form of a name, derived from its parts: ``F. M. van Last, Jr.``

    A corporate name keeps its full form, because there is nothing to
    abbreviate.
    """
    if parts["literal"]:
        return parts["literal"]
    given = parts["given"] or ""
    initials = " ".join(_initials(part) for part in given.split())
    name = " ".join(part for part in (initials, parts["von"], parts["family"]) if part)
    suffix = parts["suffix"]
    return f"{name}, {suffix}" if suffix and name else (name or suffix or "")


def parse_author_list(entry: Entry, where: str) -> List[Author]:
    """The entry's authors, in source order, with person_id unresolved.

    Each author carries the parts BibTeX split its name into as well as the
    display form, and whether the entry marked it as an equal contribution.
    Matching on those parts is #24; the resolver still reads only the display
    name, which is why the marker has to come off the name itself.
    """
    persons = list(entry.persons.get("author", []))
    if persons and _is_others(persons[-1]):
        persons.pop()             # a terminal "and others" is BibTeX's et al.

    authors = []
    for person in persons:
        parts = person_name_parts(person, where)
        name = format_name(parts)
        if name:
            authors.append(Author(
                name=name,
                equal_contribution=marks_equal_contribution(person),
                **parts))
    return authors


def resolve_crossref(fields: Dict[str, str], entries: Dict[str, Entry]) -> Dict[str, str]:
    """Fill in a child entry's missing fields from the entry it cross-refers to.

    The parent's ``title`` becomes the child's ``booktitle``, which is what a
    ``@proceedings`` parent means to an ``@inproceedings`` child; the parent's
    own title is not copied over the child's.
    """
    parent_key = fields.get("crossref")
    if not parent_key:
        return fields

    parent = entries.get(parent_key.lower())
    if parent is None:
        _warn(f"crossref '{parent_key}' names an entry that is not defined")
        return fields

    parent_fields = {name.lower(): value for name, value in parent.fields.items()}
    resolved = dict(fields)
    for name, value in parent_fields.items():
        if name not in ("title", "crossref"):
            resolved.setdefault(name, value)
    if "booktitle" not in fields and "title" in parent_fields:
        resolved["booktitle"] = parent_fields["title"]
    return resolved


def entry_fields(
    bib_id: str,
    entry: Entry,
    entries: Dict[str, Entry],
    source: str,
) -> Dict[str, str]:
    """The entry's fields: crossref resolved, prose converted from LaTeX.

    ``ENTRYTYPE`` and ``ID`` are included so the display rules below read one
    plain dictionary and know nothing about pybtex.
    """
    fields = {name.lower(): value for name, value in entry.fields.items()}
    fields = resolve_crossref(fields, entries)
    read = {
        name: _convert(value, f"{source}:{bib_id}:{name}") if name in TEXT_FIELDS else value
        for name, value in fields.items()
    }
    read["ENTRYTYPE"] = entry.type.lower()
    read["ID"] = bib_id
    return read


def format_bibtex(bib_id: str, entry: Entry) -> Optional[str]:
    """The entry written back out as BibTeX, for readers to copy.

    This is the entry as it was read, before crossref and LaTeX conversion,
    so fields labdata does not display are preserved rather than rewritten.
    """
    try:
        return entry.to_string("bibtex").strip()
    except Exception:  # noqa: BLE001 - a copyable string is not worth an entry
        _warn(f"{bib_id}: could not write this entry back out as BibTeX")
        return None


# --- Display rules -----------------------------------------------------------

def format_authors_string(authors: List[Author]) -> str:
    """Format a list of Authors into a display string.

    Uses 'and' for 2 authors, commas + 'and' for 3+.
    """
    names = [a.name for a in authors]
    if len(names) <= 2:
        return ' and '.join(names)
    return ', '.join(names[:-1]) + ', and ' + names[-1]


def format_venue(entry: dict) -> str:
    """Format venue string from a read BibTeX entry. Uses Markdown (not HTML)."""
    typ = entry.get("ENTRYTYPE", "")
    year = entry.get("year", "")

    if typ == "phdthesis":
        return f"PhD thesis, {entry.get('school', '')}, {year}"
    elif typ == "mastersthesis":
        return f"Masters thesis, {entry.get('school', '')}, {year}"
    elif typ == "techreport":
        kind = entry.get("type", "Technical Report")
        num = entry.get("number", "")
        inst = entry.get("institution", "")
        note = kind
        if num:
            note += f" {num}"
        note += f", {inst}, {year}"
        return note
    elif typ == "misc":
        arxiv_id = entry.get("eprint")
        if arxiv_id:
            return f"*arXiv:{arxiv_id}*, {year}"
    elif typ == "article":
        journal = entry.get("journal", "")
        vol = entry.get("volume", "")
        num = entry.get("number", "")
        note = f"*{journal}*"
        if vol:
            note += f", {vol}"
            if num:
                note += f"({num})"
        if year:
            note += f", {year}"
        return note
    elif typ == "inproceedings":
        conf = entry.get("booktitle", "")
        return f"*{conf}*, {year}" if conf else str(year)

    return str(year)


def extract_note(entry: dict) -> Optional[str]:
    """Extract and format the note field."""
    note = entry.get("note", "").strip().rstrip('. ')
    if not note:
        return None
    return note


def extract_video_url(entry: dict) -> Optional[str]:
    """Extract video URL if the entry's URL points to a video platform."""
    url = entry.get("url", "")
    if url and any(p in url for p in ["youtube.com", "youtu.be", "vimeo.com"]):
        return url
    return None


def construct_doi_url(entry: dict) -> Optional[str]:
    """Construct a DOI URL from the doi field."""
    doi = entry.get("doi")
    if doi:
        doi = doi.strip()
        if doi.startswith("http"):
            return doi
        return f"https://doi.org/{doi}"
    return None


def construct_arxiv_url(entry: dict) -> Optional[str]:
    """Construct an arXiv URL from the eprint field."""
    eprint = entry.get("eprint")
    if eprint:
        prefix = entry.get("archivePrefix", entry.get("archiveprefix", ""))
        if prefix.lower() == "arxiv" or not prefix:
            return f"https://arxiv.org/abs/{eprint}"
    return None


def parse_project_ids(entry: dict) -> List[str]:
    """Parse the project field from a BibTeX entry."""
    project_field = entry.get("project", "").strip()
    if not project_field:
        return []
    project_field = project_field.strip('{}')
    return [p.strip() for p in project_field.split(',') if p.strip()]


def resolve_pdf_url(bib_id: str, pdf_base_url: Optional[str]) -> Optional[str]:
    """Construct a PDF URL for a given bib entry."""
    if not pdf_base_url:
        return None
    base = pdf_base_url.rstrip('/')
    pdf_path = f"{base}/{bib_id}.pdf"
    if pdf_base_url.startswith(('http://', 'https://')):
        return pdf_path
    return pdf_path if Path(pdf_path).exists() else None


def entry_to_publication(
    bib_id: str,
    entry: Entry,
    category: str,
    entries: Optional[Dict[str, Entry]] = None,
    pdf_base_url: Optional[str] = None,
    source: str = "",
) -> Publication:
    """Convert one pybtex Entry to a Publication dataclass."""
    fields = entry_fields(bib_id, entry, entries or {}, source)

    url = fields.get("url", "")
    video_url = extract_video_url(fields)

    return Publication(
        bib_id=bib_id,
        title=fields.get("title", ""),
        authors=parse_author_list(entry, f"{source}:{bib_id}:author"),
        year=int(fields.get("year", 0)),
        venue=format_venue(fields),
        category=category,
        entry_type=fields["ENTRYTYPE"],
        abstract=fields.get("abstract"),
        note=extract_note(fields),
        pdf_url=resolve_pdf_url(bib_id, pdf_base_url),
        doi_url=construct_doi_url(fields),
        arxiv_url=construct_arxiv_url(fields),
        url=url if url and not video_url else None,
        video_url=video_url,
        project_ids=parse_project_ids(fields),
        bibtex=format_bibtex(bib_id, entry),
    )


def parse_all_publications(
    bib_dir: str,
    bib_files: list,
    pdf_base_url: Optional[str] = None,
) -> List[Publication]:
    """Parse all configured BibTeX files and return a flat list of Publications.

    Every file is read first, so a ``crossref`` may point at a parent in
    another file.

    Args:
        bib_dir: Directory containing the BibTeX files
        bib_files: List of dicts with 'name' and 'category' keys
        pdf_base_url: Base URL/path for PDFs

    Returns:
        List of Publication objects, sorted by year descending
    """
    read: List[Tuple[str, str, Entry, str]] = []
    entries: Dict[str, Entry] = {}
    for bib_file in bib_files:
        name = bib_file['name'] if isinstance(bib_file, dict) else bib_file.name
        category = bib_file['category'] if isinstance(bib_file, dict) else bib_file.category
        path = f"{bib_dir}/{name}"
        for bib_id, entry in parse_bibtex_file(path).items():
            read.append((path, bib_id, entry, category))
            entries.setdefault(bib_id.lower(), entry)

    publications = [
        entry_to_publication(bib_id, entry, category, entries, pdf_base_url, path)
        for path, bib_id, entry, category in read
    ]
    publications.sort(key=lambda p: p.year, reverse=True)
    return publications
