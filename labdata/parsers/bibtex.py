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
from pybtex.database.input.bibtex import Parser as PybtexParser

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

_STRING_DEFINITION = re.compile(r'@string\s*[{(]\s*([^\s=,{}()"]+)\s*=', re.IGNORECASE)
_COMMENT_COMMAND = re.compile(r'@comment[ \t]*(?=[{(])', re.IGNORECASE)


def _warn(message: str) -> None:
    """Report a problem with an input file in labdata's own voice.

    Parser messages are relayed as the library phrased them: naming the file,
    entry key and field of every diagnostic is #26.
    """
    print(f"Warning: {message}", file=sys.stderr)


# --- Reading the files -------------------------------------------------------

def _blank_comment_blocks(text: str) -> str:
    """Blank out ``@comment{...}`` bodies, keeping the line structure.

    BibTeX itself reads on to the next ``@`` after a ``@comment``, so an entry
    written inside one is a real entry to it. labdata treats a commented-out
    entry as commented out. Blanking rather than deleting keeps the line
    numbers in the parser's messages honest.
    """
    out = list(text)
    position = 0
    while True:
        match = _COMMENT_COMMAND.search(text, position)
        if not match:
            return "".join(out)
        opening = text[match.end()]
        closing = "}" if opening == "{" else ")"
        depth = 0
        end = match.end()
        while end < len(text):
            if text[end] == opening:
                depth += 1
            elif text[end] == closing:
                depth -= 1
                if depth == 0:
                    end += 1
                    break
            end += 1
        for i in range(match.start(), min(end, len(text))):
            if out[i] != "\n":
                out[i] = " "
        position = end


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


def parse_bibtex_file(path: str) -> Dict[str, Entry]:
    """Parse one BibTeX file into pybtex entries, keyed by citation key.

    Anything the parser has to say is captured and reported by labdata, so no
    library logging reaches the user.
    """
    text = _blank_comment_blocks(Path(path).read_text(encoding="utf-8-sig"))

    for name in _redefined_macros(text):
        _warn(f"@string macro '{name}' is defined more than once; "
              "the last definition is used")

    parser = PybtexParser()
    with pybtex.errors.capture() as errors:
        data = parser.parse_string(text)
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


def _is_others(person: Person) -> bool:
    """``and others``: BibTeX's "et al.", not a person."""
    return (not person.first_names and not person.middle_names
            and not person.prelast_names and not person.lineage_names
            and [name.lower() for name in person.last_names] == [OTHERS])


def format_person(person: Person, where: str) -> str:
    """Format one pybtex Person for display: ``F. M. van Last, Jr.``

    A name with no given part — a corporate author written ``{Some Lab}`` —
    keeps its full form, because there is nothing to abbreviate.
    """
    given = [_initials(_convert(part, where))
             for part in person.first_names + person.middle_names]
    surname = " ".join(_convert(part, where)
                       for part in person.prelast_names + person.last_names)
    name = " ".join([part for part in [*given, surname] if part])
    lineage = " ".join(_convert(part, where) for part in person.lineage_names)
    return f"{name}, {lineage}" if lineage else name


def parse_author_list(entry: Entry, where: str) -> List[Author]:
    """The entry's authors, in source order, with person_id unresolved."""
    authors = []
    for person in entry.persons.get("author", []):
        if _is_others(person):
            continue
        name = format_person(person, where)
        if name:
            authors.append(Author(name=name))
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
