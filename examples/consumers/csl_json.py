#!/usr/bin/env python3
"""Consumer probe: a CSL-JSON export.

    python examples/consumers/csl_json.py lab.json > lab.csl.json

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test, and for why this probe cannot produce a correct journal-article
record today.
"""

import json
import sys


# CSL types for the entry types the document emits. Anything else falls back
# to "document", which CSL defines for exactly that purpose.
CSL_TYPES = {
    "article": "article-journal",
    "inproceedings": "paper-conference",
    "conference": "paper-conference",
    "incollection": "chapter",
    "inbook": "chapter",
    "book": "book",
    "phdthesis": "thesis",
    "mastersthesis": "thesis",
    "techreport": "report",
    # A manual is an issued document with a version, which is what CSL's
    # "report" is for; CSL has no manual type and "document" would throw away
    # what the entry type said.
    "manual": "report",
    "unpublished": "manuscript",
    "misc": "document",
}


def csl_name(author):
    """One CSL name object, from the parts the document splits a name into.

    `name` is the document's display form and abbreviates the given name
    unconditionally, so it is lossy as a source. The parts preserve whatever
    the input supplied, which may itself be an initial: `given: "A."` where
    the entry wrote `Adams, A.` is correct CSL and not a missing property.
    """
    if author.get("literal"):
        return {"literal": author["literal"]}
    name = {}
    for csl_key, doc_key in (("given", "given"), ("family", "family"),
                             ("non-dropping-particle", "von"), ("suffix", "suffix")):
        if author.get(doc_key):
            name[csl_key] = author[doc_key]
    return name


def venue_parts(pub):
    """The venue as structured data, or None when the document composed it.

    A document that hands over a pre-composed display string instead gives no
    container title to put in `container-title` and no volume or number
    beside it. Taking that string apart, or reading the opaque re-serialized
    export the document carries alongside it, would prove nothing about the
    document: see README.md.
    """
    venue = pub.get("venue")
    return venue if isinstance(venue, dict) else None


def identifier(pub, scheme):
    """The first identifier the document files under one scheme, or None.

    CSL wants identifiers, not links. A link built from an identifier is not
    invertible -- a `doi` written as a URL in the input is passed through as
    the link unchanged -- so the identifier is read from the registry that
    holds identifiers, and never reconstructed from a link. A document that
    still carries the identifier as a flat property is read there too.
    """
    found = (pub.get("identifiers") or {}).get(scheme)
    if isinstance(found, str):
        found = [found]
    if found:
        return found[0]
    return pub.get(scheme)


def link_url(pub, *kinds):
    """The first URL the document files under any of these link kinds.

    Each kind is tried in turn, and a document that still carries a flat
    `<kind>_url` property is read there too, so a link is not reported
    missing because this looked in only one of the two places it could sit.
    """
    links = pub.get("links") or {}
    for kind in kinds:
        for record in links.get(kind) or []:
            if isinstance(record, dict) and record.get("url"):
                return record["url"]
        flat = pub.get(kind + "_url")
        if flat:
            return flat
    return None


def bibliographic(pub, key):
    """A first-class bibliographic property, from the work or from its venue."""
    value = pub.get(key)
    if value is None:
        value = (venue_parts(pub) or {}).get(key)
    return value


def record(pub):
    out = {
        "id": pub["bib_id"],
        "type": CSL_TYPES.get(pub["entry_type"], "document"),
        "title": pub["title"],
        "author": [csl_name(a) for a in pub["authors"]],
        "issued": {"date-parts": [[pub["year"]]]},
    }
    name = (venue_parts(pub) or {}).get("name")
    if name:
        out["container-title"] = name
    for csl_key, doc_key in (("volume", "volume"), ("issue", "number"),
                             ("publisher", "publisher"),
                             ("publisher-place", "address"),
                             ("collection-title", "series")):
        value = bibliographic(pub, doc_key)
        if value:
            out[csl_key] = str(value)
    pages = bibliographic(pub, "pages")
    if pages:
        out["page"] = str(pages).replace("--", "-")

    doi = identifier(pub, "doi")
    if doi:
        out["DOI"] = str(doi)
    for csl_key, doc_key in (("abstract", "abstract"), ("note", "note")):
        if pub.get(doc_key):
            out[csl_key] = pub[doc_key]
    # The work's own web page first, then whatever else it can be reached at.
    url = link_url(pub, "url", "pdf", "doi", "arxiv")
    if url is not None:
        out["URL"] = url
    return out


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: csl_json.py DOCUMENT\n")
        return 2
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    text = json.dumps([record(p) for p in doc["works"]],
                      indent=2, ensure_ascii=False, sort_keys=True)
    # Written as bytes so the export is UTF-8 whatever the locale says.
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
