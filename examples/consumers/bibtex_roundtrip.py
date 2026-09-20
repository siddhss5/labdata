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
  manual. When the document gives a pre-composed display string instead, as
  it does today, nothing is taken out of it: a probe renders markup it was
  handed, it does not parse fields back out of a string the compiler
  composed.
- The identifiers. A DOI and an arXiv id reach the document only as the links
  built from them, and those links are not invertible: a `doi` written as a
  URL in the input is passed through unchanged, so there is no prefix a
  consumer can reliably strip, and the arXiv link drops the prefix field that
  said which repository the id belongs to. So `doi` and `eprint` are looked
  up as properties, like everything else, and are not reconstructed from a
  link. `url` is different and is not a judgement call: it is one input field
  the compiler routes to one of two properties by looking at the host, so
  both are consulted and exactly one of them holds it.
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

    `name` is the document's display form and abbreviates the given name
    unconditionally, so it is lossy as a source. The parts preserve whatever
    the input supplied -- an initial where the entry wrote one -- which is
    exactly what belongs back in the field.
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


def field_value(publication, field):
    """What the document can put in one field of the entry, or None."""
    if field == "author":
        return " and ".join(author_name(a) for a in publication["authors"]) or None
    if field == "url":
        return publication.get("url") or publication.get("video_url")
    if field == CONTAINER_FIELD.get(publication["entry_type"]):
        name = (venue_parts(publication) or {}).get("name")
        if name:
            return name
    value = publication.get(field)
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
    return "\n\n".join(entry(p) for p in doc["publications"]) + "\n"


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
