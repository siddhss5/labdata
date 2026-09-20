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


# The document composes the venue with Markdown emphasis (SPEC.md section 2,
# Target #18). Rendering markup the document handed us is not the same as
# recovering fields from it: after this substitution the page still cannot
# say what the journal's name is on its own.
EMPHASIS = re.compile(r"\*([^*]+)\*")

ROLES = {
    "professor": "Faculty",
    "postdoc": "Postdocs",
    "phd_student": "PhD Students",
    "ms_student": "MS Students",
}


def full_name(author):
    """An author's name in full, from the parts the document splits it into.

    `name` is the document's display form and abbreviates given names to
    initials, so a page that wants "Bob Brown" builds it from the parts.
    """
    if author.get("literal"):
        return author["literal"]
    parts = [author.get(k) for k in ("given", "von", "family", "suffix")]
    return " ".join(p for p in parts if p)


def venue_html(pub):
    """The venue, as HTML."""
    venue = pub.get("venue")
    if isinstance(venue, dict):
        head = "<em>%s</em>" % esc(venue.get("name") or "")
        rest = [str(venue[k]) for k in ("volume", "number", "pages") if venue.get(k)]
        return ", ".join([head] + [esc(r) for r in rest])
    return EMPHASIS.sub(r"<em>\1</em>", esc(venue or ""))


def esc(text):
    return html.escape(str(text), quote=True)


def link(url, label):
    return '<a href="%s">%s</a>' % (esc(url), esc(label))


def publication_html(pub):
    out = ["<li>"]
    out.append("<span>%s</span>" % ", ".join(esc(full_name(a)) for a in pub["authors"]))
    out.append('<span class="title">%s</span>' % esc(pub["title"]))
    out.append("<span>%s</span>" % venue_html(pub))
    out.append("<span>%s</span>" % esc(pub["year"]))
    if pub.get("note"):
        out.append("<span>%s</span>" % esc(pub["note"]))
    links = [link(pub[key], label) for key, label in
             (("pdf_url", "PDF"), ("doi_url", "DOI"), ("arxiv_url", "arXiv"),
              ("url", "Link"), ("video_url", "Video")) if pub.get(key)]
    if links:
        out.append("<span>%s</span>" % " ".join(links))
    if pub.get("abstract"):
        out.append("<p>%s</p>" % esc(pub["abstract"]))
    out.append("</li>")
    return "\n".join(out)


def person_html(person):
    out = ["<li>"]
    name = esc(person["name"])
    out.append(link(person["website"], person["name"]) if person.get("website")
               else "<span>%s</span>" % name)
    for key in ("degree", "thesis_title", "co_advisor", "current_position"):
        if person.get(key):
            out.append("<span>%s</span>" % esc(person[key]))
    out.append("<span>%s publications</span>" % esc(person["publication_count"]))
    out.append("</li>")
    return "\n".join(out)


def project_html(project):
    out = ["<li>"]
    out.append(link(project["website"], project["title"]) if project.get("website")
               else "<span>%s</span>" % esc(project["title"]))
    if project.get("description"):
        out.append("<p>%s</p>" % esc(project["description"]))
    out.append("<span>%s: %s works, %s people</span>"
               % (esc(project["status"]), len(project["publication_ids"]),
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
    for pub in doc["publications"]:            # already ordered, SPEC.md section 3
        if pub["category"] not in categories:
            categories.append(pub["category"])
    for category in categories:
        out.append("<h3>%s</h3>" % esc(category))
        out.append("<ul>")
        out += [publication_html(p) for p in doc["publications"]
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
    out += ["<li><span>%s</span></li>" % esc(c["name"]) for c in doc["collaborators"]]
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
