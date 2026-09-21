#!/usr/bin/env python3
"""Consumer probe: one HTML page, built from the emitted document alone.

    python examples/consumers/plain_html.py lab.json > lab.html

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test.
"""

import html
import json
import re
import sys


# A document that hands over a pre-composed venue string writes its emphasis
# in Markdown. Rendering markup the document handed us is not the same as
# recovering fields from it: after this substitution the page still cannot
# say what the journal's name is on its own.
EMPHASIS = re.compile(r"\*([^*]+)\*")

# The links a page offers, in the order a reader wants them, with the label
# each gets. The document files links by kind and may carry several of one
# kind, so every record under a kind is rendered rather than only the first.
LINK_KINDS = (("pdf", "PDF"), ("doi", "DOI"), ("arxiv", "arXiv"),
              ("url", "Link"), ("video", "Video"))

# What the page prints beside the venue name, from the work's own properties.
PLACEMENT = ("volume", "number", "pages")

ROLES = {
    "professor": "Faculty",
    "postdoc": "Postdocs",
    "phd_student": "PhD Students",
    "ms_student": "MS Students",
}


def name_from_parts(author):
    """An author's name, assembled from the parts the document splits it into.

    `name` is the document's display form and abbreviates the given name
    unconditionally, so it is lossy as a source. The parts preserve whatever
    the input supplied: `Bob Brown` where the entry wrote `Brown, Bob`, and
    `A. Adams` where it wrote `Adams, A.`. Neither is a gap -- this returns
    the name the author's files gave, which is what a consumer should show.
    """
    if author.get("literal"):
        return author["literal"]
    parts = [author.get(k) for k in ("given", "von", "family", "suffix")]
    return " ".join(p for p in parts if p)


def venue_html(pub):
    """Where the work appeared, as HTML: the container emphasised, then its
    placement in it.

    The emphasis is the page's, not the document's. A structured venue gives
    the container's name and nothing else, so what a reader sees is composed
    here -- which is the point: a consumer that wants a different citation
    style can compose a different one.
    """
    venue = pub.get("venue")
    if not isinstance(venue, dict):
        return EMPHASIS.sub(r"<em>\1</em>", esc(venue or ""))
    parts = ["<em>%s</em>" % esc(venue.get("name") or "")]
    parts += [esc(pub[key]) for key in PLACEMENT if pub.get(key)]
    return ", ".join(parts)


def esc(text):
    return html.escape(str(text), quote=True)


def link(url, label):
    return '<a href="%s">%s</a>' % (esc(url), esc(label))


def publication_html(pub):
    # Each entry gets the document's id and each field a class, so a reader
    # can link to one work and the test can check this entry's authors
    # against this entry's authors rather than searching the whole page.
    out = ['<li class="publication" id="work-%s">' % esc(pub["bib_id"])]
    out.append('<span class="authors">%s</span>'
               % ", ".join(esc(name_from_parts(a)) for a in pub["authors"]))
    out.append('<span class="title">%s</span>' % esc(pub["title"]))
    out.append('<span class="venue">%s</span>' % venue_html(pub))
    out.append('<span class="year">%s</span>' % esc(pub["year"]))
    if pub.get("note"):
        out.append("<span>%s</span>" % esc(pub["note"]))
    filed = pub.get("links") or {}
    links = [link(record["url"], label)
             for kind, label in LINK_KINDS
             for record in filed.get(kind) or [] if record.get("url")]
    if links:
        out.append("<span>%s</span>" % " ".join(links))
    if pub.get("abstract"):
        out.append("<p>%s</p>" % esc(pub["abstract"]))
    out.append("</li>")
    return "\n".join(out)


def person_html(person):
    out = ['<li class="person" id="person-%s">' % esc(person["id"])]
    out.append('<span class="name">%s</span>'
               % (link(person["website"], person["name"]) if person.get("website")
                  else esc(person["name"])))
    for key in ("degree", "thesis_title", "co_advisor", "current_position"):
        if person.get(key):
            out.append("<span>%s</span>" % esc(person[key]))
    out.append("<span>%s works</span>" % esc(person["work_count"]))
    out.append("</li>")
    return "\n".join(out)


def project_html(project):
    out = ['<li class="project" id="project-%s">' % esc(project["id"])]
    out.append('<span class="name">%s</span>'
               % (link(project["website"], project["title"]) if project.get("website")
                  else esc(project["title"])))
    if project.get("description"):
        out.append("<p>%s</p>" % esc(project["description"]))
    out.append("<span>%s: %s works, %s people</span>"
               % (esc(project["status"]), len(project["work_ids"]),
                  len(project["people_ids"])))
    out.append("</li>")
    return "\n".join(out)


def render(doc):
    lab = doc.get("lab") or {}
    title = lab.get("name") or "Lab"
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>",
           '<meta charset="utf-8">', "<title>%s</title>" % esc(title),
           "</head>", "<body>", "<h1>%s</h1>" % esc(title)]
    if lab.get("description"):
        out.append("<p>%s</p>" % esc(lab["description"]))

    out.append("<h2>Publications</h2>")
    categories = []
    for pub in doc["works"]:                   # already ordered, SPEC.md section 3
        if pub["category"] not in categories:
            categories.append(pub["category"])
    for category in categories:
        out.append("<h3>%s</h3>" % esc(category))
        out.append("<ul>")
        out += [publication_html(p) for p in doc["works"]
                if p["category"] == category]
        out.append("</ul>")

    out.append("<h2>People</h2>")
    for role, heading in ROLES.items():
        members = [p for p in doc["people"] if p.get("role") == role]
        if not members:
            continue
        out.append("<h3>%s</h3>" % esc(heading))
        out.append("<ul>")
        out += [person_html(p) for p in members]
        out.append("</ul>")

    out.append("<h2>Collaborators</h2>")
    out.append("<ul>")
    # No id on these. A collaborator's `key` is a lookup key over grouped
    # authorships and explicitly not an assertion about a human, so this page
    # does not turn it into the address of a person's entry. A page that
    # wants collaborator pages should read the key knowing what it is.
    out += ['<li class="collaborator"><span class="name">%s</span></li>' % esc(c["name"])
            for c in doc["collaborators"]]
    out.append("</ul>")

    out.append("<h2>Projects</h2>")
    out.append("<ul>")
    out += [project_html(p) for p in doc["projects"]]
    out.append("</ul>")

    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: plain_html.py DOCUMENT\n")
        return 2
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    # Written as bytes so the page is UTF-8 whatever the locale says.
    sys.stdout.buffer.write(render(doc).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
