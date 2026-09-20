#!/usr/bin/env python3
"""Consumer probe: a LaTeX CV fragment, publications grouped by year.

    python examples/consumers/cv_tex.py lab.json > publications.tex

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test, and for why this probe cannot produce a correct CV entry today.
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


def full_name(author):
    """An author's name in full, from the parts the document splits it into.

    `name` is the document's display form and abbreviates given names to
    initials. A CV wants the full name, so this builds it from the parts,
    which the document emits on every author.
    """
    if author.get("literal"):
        return author["literal"]
    parts = [author.get(k) for k in ("given", "von", "family", "suffix")]
    return " ".join(p for p in parts if p)


def venue_parts(pub):
    """The venue as structured data, or None when the document composed it.

    Today `venue` is one pre-composed string with Markdown emphasis inside
    it -- `*Transactions on Robot Learning*, 4(2), 2025` -- so a LaTeX
    consumer has no venue name to put in `\\emph{}` and no volume or number
    to typeset beside it. Recovering them by taking that string apart, or by
    reading the verbatim export the document carries alongside it, would
    prove nothing about the document: see README.md.
    """
    venue = pub.get("venue")
    return venue if isinstance(venue, dict) else None


def bibliographic(pub, key):
    """A first-class bibliographic property, from the work or from its venue."""
    value = pub.get(key)
    if value is None:
        value = (venue_parts(pub) or {}).get(key)
    return value


def entry(pub):
    out = [r"\item %s." % tex(", ".join(full_name(a) for a in pub["authors"]))]
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

    for key in ("doi_url", "arxiv_url"):
        if pub.get(key):
            out.append(r"\newblock \url{%s}" % pub[key])
    return "\n".join(out)


def render(doc):
    by_year = {}
    for pub in doc["publications"]:
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
