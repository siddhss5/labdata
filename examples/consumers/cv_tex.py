#!/usr/bin/env python3
"""Consumer probe: a LaTeX CV fragment, works grouped by year.

    python examples/consumers/cv_tex.py lab.json > works.tex

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test, and for the rule it exists to test.
"""

import json
import sys


TEX_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def tex(text):
    return "".join(TEX_ESCAPES.get(c, c) for c in str(text))


def name_from_parts(author):
    """An author's name, assembled from the parts the document splits it into.

    The parts are read rather than `name`, which is the parts joined in
    reading order and so cannot be split back into them. They preserve
    whatever the input supplied: `Bob Brown` where the entry wrote
    `Brown, Bob`, and `A. Adams` where it wrote `Adams, A.`. Neither is a gap
    -- this returns the name the author's files gave, which is what a
    consumer should show.
    """
    if author.get("literal"):
        return author["literal"]
    parts = [author.get(k) for k in ("given", "von", "family", "suffix")]
    return " ".join(p for p in parts if p)


def venue_parts(pub):
    """The venue as structured data, or None when the document composed it.

    A document that hands over a pre-composed display string instead gives a
    LaTeX consumer no venue name to put in `\\emph{}`. Recovering one by
    taking that string apart, or by reading the opaque re-serialized export
    the document carries alongside it, would prove nothing about the
    document: see README.md.
    """
    venue = pub.get("venue")
    return venue if isinstance(venue, dict) else None


def bibliographic(pub, key):
    """A first-class bibliographic property, from the work or from its venue."""
    value = pub.get(key)
    if value is None:
        value = (venue_parts(pub) or {}).get(key)
    return value


def link_url(pub, kind):
    """The first URL the document files under one link kind, or None.

    A document that still carries a flat `<kind>_url` property is read there
    too, so this probe does not report a link lost because it looked in only
    one of the two places it could sit.
    """
    for record in (pub.get("links") or {}).get(kind) or []:
        if isinstance(record, dict) and record.get("url"):
            return record["url"]
    return pub.get(kind + "_url")


def entry(pub):
    out = [r"\item %s." % tex(", ".join(name_from_parts(a) for a in pub["authors"]))]
    out.append(r"\newblock %s." % tex(pub["title"]))

    where = []
    name = (venue_parts(pub) or {}).get("name")
    if name:
        where.append(r"\emph{%s}" % tex(name))
    volume = bibliographic(pub, "volume")
    number = bibliographic(pub, "number")
    if volume:
        where.append(tex(volume) + ("(%s)" % tex(number) if number else ""))
    pages = bibliographic(pub, "pages")
    if pages:
        where.append("pp.~%s" % tex(pages))
    where.append(tex(pub["year"]))
    out.append(r"\newblock %s." % ", ".join(where))

    for kind in ("doi", "arxiv"):
        url = link_url(pub, kind)
        if url:
            out.append(r"\newblock \url{%s}" % url)
    return "\n".join(out)


def render(doc):
    by_year = {}
    for pub in doc["works"]:
        by_year.setdefault(pub["year"], []).append(pub)
    out = ["% Publications, newest first. Include this file from a CV class."]
    for year in sorted(by_year, reverse=True):
        out.append(r"\section*{%s}" % tex(year))
        out.append(r"\begin{enumerate}")
        out += [entry(p) for p in by_year[year]]
        out.append(r"\end{enumerate}")
    out.append("")
    return "\n".join(out)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: cv_tex.py DOCUMENT\n")
        return 2
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    # Written as bytes so the fragment is UTF-8 whatever the locale says.
    sys.stdout.buffer.write(render(doc).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
