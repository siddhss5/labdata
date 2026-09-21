#!/usr/bin/env python3
"""Consumer probe: one BibTeX entry per work, re-emitted from the document.

    python examples/consumers/bibtex_roundtrip.py lab.json > works.bib

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test, and for the fields it cannot put back.

This is a **field-loss detector, not a value round trip.** LaTeX is converted
to Unicode on the way in and the conversion is deliberately one-way, so an
entry that wrote `C{\\^o}t{\\'e}` comes back as `Côté` and an entry that wrote
`\\textbf{Best Paper Award}` comes back without the command. Comparing values
would therefore assert something false. What is worth asking is narrower and
answerable: **is every field name the input entry carried still reachable as
a first-class property of the work?** Each field below is looked up where a
consumer would look for it, and a field that is nowhere is simply not
written, so the entry this probe emits is the entry the document can still
describe.

It does not read the re-serialized export the document carries beside these
properties. That record is an opaque copy of the entry for a reader to paste
into a reference manager, not a set of properties; mining it would let this
probe emit a complete entry while proving nothing whatever about the schema.

Two lookups are worth stating, because they are judgement rather than
mechanism:

- The venue. When the document gives a structured container, its name goes
  into the field that names the container for that entry type -- `journal`
  for an article, `booktitle` for a paper in a proceedings or a collection,
  `school` for a thesis, `institution` for a report, `organization` for a
  manual. When a document gives a pre-composed display string instead,
  nothing is taken out of it: a probe renders markup it was handed, it does
  not parse fields back out of a string the compiler composed.
- The identifiers. They are read from the map of scheme to identifiers and
  **never reconstructed from a link**, because a link built from an
  identifier is not invertible: a `doi` written as a URL in the input is
  passed through as the link unchanged, so there is no prefix a consumer can
  reliably strip. The map is also where a repeatable identifier has to live
  -- print and electronic ISSNs are two values of one field -- so a flat
  property is consulted as well, for a document that carries one.
  `archivePrefix` is not an identifier at all: it names the repository
  `eprint` belongs to, which is exactly what a scheme says, so both come
  from the one scheme that is not a bibliographic identifier. That recovers
  the scheme rather than the spelling the entry used: the document
  normalises the scheme to lower case, as it does the entry type, so an
  entry that wrote `arXiv` comes back as `arxiv`. This is a field-loss
  detector and not a value round trip, so a normalised value is the right
  answer here for the same reason a LaTeX-converted one is.
- The editors. They are people, not a string, so the document may carry them
  either as a parsed list beside the authors or as the raw field. Both are
  consulted, and a parsed list is written back out in BibTeX's own name order
  by the same function that writes the authors.
- The links. `url` is one input field the compiler routes by looking at the
  host, so the two properties it can land in are both consulted -- and so is
  a map from link kind to links, which is where a document that has stopped
  carrying `*_url` properties would keep it. **Only a link the document says
  came from the input counts.** A link record states its origin, over
  `input`, `sidecar`, `enrichment`, `inferred` and `derived`; a link the lab
  added from somewhere else is not evidence that the entry's own `url` field
  survived, and letting one stand in for it would make this probe hide a
  loss, which is the one thing it must never do. A record that states no
  origin is not counted either, for the same reason: the question is what the
  document *says*, and silence is not an answer.

Each of these is looked up in **every** place it could sit, not in one, and
the first that answers wins. That is what a real consumer would have to do,
and it is what keeps this probe honest in both directions: it cannot report
a field lost because it looked in only one of the places the field might be.
"""

import json
import sys


# Every field the probe knows how to name, in the order it writes them. Each
# is looked up as a first-class property of the work; the handful whose
# property is spelled differently are handled in `field_value` below.
FIELDS = (
    "author", "editor", "title", "booktitle", "chapter", "pages", "volume",
    "number", "edition", "series", "publisher", "organization", "institution",
    "school", "journal", "howpublished", "type", "address", "month", "year",
    "doi", "eprint", "archiveprefix", "isbn", "issn", "language", "keywords",
    "annote", "note", "abstract", "url",
)

# The scheme under which each identifier field would sit in a map from
# scheme to identifiers. `eprint` is not here: its scheme is whichever
# repository the entry named, so it is found rather than looked up.
IDENTIFIER_SCHEME = {"doi": "doi", "isbn": "isbn", "issn": "issn"}

# The schemes that identify a work rather than name a repository it sits in.
# An `eprint` is filed under the repository's own scheme, so the scheme that
# is none of these is the preprint's -- and it is also what `archivePrefix`
# said, which is why that field needs no property of its own.
NOT_A_REPOSITORY = frozenset(IDENTIFIER_SCHEME.values())

# The link kinds the BibTeX `url` field could have become, and the one origin
# that makes a link evidence that the input field reached the document.
URL_KINDS = ("url", "video")
FROM_INPUT = "input"

# The field that names the container, per entry type. A structured venue's
# name belongs in this one.
CONTAINER_FIELD = {
    "article": "journal",
    "inproceedings": "booktitle",
    "conference": "booktitle",
    "incollection": "booktitle",
    "inbook": "booktitle",
    "phdthesis": "school",
    "mastersthesis": "school",
    "techreport": "institution",
    "manual": "organization",
}


def clean(value):
    """A value with its whitespace collapsed, so one field stays one line."""
    return " ".join(str(value).split())


def author_name(author):
    """One name in BibTeX's own order, from the parts the document splits it
    into.

    The parts are read rather than `name`, which is the parts joined in
    reading order and so cannot be split back into them. They preserve
    whatever the input supplied -- an initial where the entry wrote one --
    which is exactly what belongs back in the field.
    """
    if author.get("literal"):
        return "{%s}" % author["literal"]
    family = " ".join(p for p in (author.get("von"), author.get("family")) if p)
    parts = [p for p in (family, author.get("suffix"), author.get("given")) if p]
    return ", ".join(parts)


def venue_parts(publication):
    """The venue as structured data, or None when the document composed it."""
    venue = publication.get("venue")
    return venue if isinstance(venue, dict) else None


def scheme_map(publication):
    """The document's map from identifier scheme to identifiers, or empty."""
    found = publication.get("identifiers")
    return found if isinstance(found, dict) else {}


def repository_scheme(publication):
    """The scheme an `eprint` sits under, or None when the work has none.

    Found rather than looked up, because the scheme *is* the repository: an
    arXiv preprint is under `arxiv` and one in any other repository is under
    that repository's own scheme. Reconstructing a fixed `arXiv` here would
    make this probe answer for a field it had not read.
    """
    for scheme in scheme_map(publication):
        if scheme not in NOT_A_REPOSITORY:
            return scheme
    return None


def identifier_value(publication, field):
    """One identifier field, from the scheme map. A scheme may hold several.

    Unlike a link, an identifier carries no origin: the map is scheme to
    identifiers and says nothing about where each came from. So there is no
    provenance to check here, and none is invented.
    """
    scheme = (repository_scheme(publication) if field == "eprint"
              else IDENTIFIER_SCHEME.get(field))
    found = scheme_map(publication).get(scheme)
    if isinstance(found, str):
        found = [found]
    return ", ".join(str(one) for one in found) if found else None


def name_list(people):
    """A list of parsed names joined the way a BibTeX name field joins them."""
    return " and ".join(author_name(person) for person in people) or None


def link_value(publication, kinds):
    """The first link under any of ``kinds`` that came from the input.

    A link the document attributes to enrichment, a sidecar or its own
    derivation says nothing about whether the entry's field survived, so it
    is not read as though it did. Neither is a record that states no origin.
    """
    links = publication.get("links")
    if not isinstance(links, dict):
        return None
    for kind in kinds:
        for record in links.get(kind) or []:
            if not isinstance(record, dict) or record.get("origin") != FROM_INPUT:
                continue
            if record.get("url"):
                return record["url"]
    return None


def field_value(publication, field):
    """What the document can put in one field of the entry, or None.

    Every place the field could sit is consulted, first answer wins.
    """
    if field == "author":
        return name_list(publication["authors"])
    if field == "editor" and publication.get("editors"):
        return name_list(publication["editors"])
    if field == "url":
        return (publication.get("url") or publication.get("video_url")
                or link_value(publication, URL_KINDS))
    if field == "archiveprefix":
        return repository_scheme(publication)
    if field == CONTAINER_FIELD.get(publication["entry_type"]):
        name = (venue_parts(publication) or {}).get("name")
        if name:
            return name
    value = publication.get(field)
    if value is None:
        value = identifier_value(publication, field)
    if value is None:
        value = (venue_parts(publication) or {}).get(field)
    return value


def entry(publication):
    """One BibTeX entry, carrying every field the document still has."""
    written = []
    for field in FIELDS:
        value = field_value(publication, field)
        if value is None or value == "":
            continue
        written.append("  %s = {%s}" % (field, clean(value)))
    head = "@%s{%s," % (publication["entry_type"], publication["bib_id"])
    return "\n".join([head, ",\n".join(written), "}"] if written else [head, "}"])


def render(doc):
    return "\n\n".join(entry(p) for p in doc["works"]) + "\n"


def main(argv):
    if len(argv) != 2:
        # Named from argv rather than written out: the static check in
        # tests/conformance/test_consumer_probes.py forbids a probe from
        # carrying the name of the format it emits in a string it evaluates.
        sys.stderr.write("usage: %s DOCUMENT\n" % argv[0])
        return 2
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    # Written as bytes so the output is UTF-8 whatever the locale says.
    sys.stdout.buffer.write(render(doc).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
