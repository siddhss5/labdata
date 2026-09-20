#!/usr/bin/env python3
"""Consumer probe: a person / project / work edge list.

    python examples/consumers/graph.py lab.json > graph.tsv

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test, and for why this probe cannot produce a complete graph today.

Output is tab separated, one record per line:

    node	person:aadams	Alice Adams
    edge	authored	person:aadams	work:brown2025tidy
"""

import json
import sys


def clean(text):
    """A label with no tab or newline in it, so one record stays one line."""
    return " ".join(str(text).split())


def person_nodes(doc):
    """{node id: label} for every co-author the document gives an identity to.

    A graph node needs an identifier, not a display string. The document
    gives every lab member an `id`. It gives a co-author who is not a lab
    member no identifier at all: they appear in `collaborators` keyed by
    their display name, which SPEC.md section 5 states is not an identity --
    three different people who all write as `J. Smith` are one entry. So
    keying a node on that name would merge people the document itself warns
    are distinct, and this probe does not do it.

    `collaborators[].id` is read here because that is where an identifier
    would naturally sit; it is absent today, so those entries yield no node.
    """
    nodes = {}
    for person in doc["people"]:
        nodes["person:" + person["id"]] = clean(person["name"])
    for collaborator in doc["collaborators"]:
        if collaborator.get("id"):
            nodes["person:" + collaborator["id"]] = clean(collaborator["name"])
    return nodes


def render(doc):
    people = person_nodes(doc)
    works = {"work:" + p["bib_id"]: clean(p["title"]) for p in doc["publications"]}
    projects = {"project:" + p["id"]: clean(p["title"]) for p in doc["projects"]}

    nodes = {}
    nodes.update(people)
    nodes.update(works)
    nodes.update(projects)

    edges = []
    for pub in doc["publications"]:
        work = "work:" + pub["bib_id"]
        for author in pub["authors"]:
            # `person_id` is the only field of an authorship that points at a
            # person. The schema defines it as the id of a matching person in
            # people.yaml, so for a co-author who is not a lab member it is
            # null and there is nothing else here to follow.
            node = "person:" + author["person_id"] if author.get("person_id") else None
            if node in people:
                edges.append(("authored", node, work))
        for project_id in pub["project_ids"]:
            project = "project:" + project_id
            if project in projects:
                edges.append(("part_of", work, project))
    for project in doc["projects"]:
        for person_id in project["people_ids"]:
            node = "person:" + person_id
            if node in people:
                edges.append(("member_of", node, "project:" + project["id"]))

    lines = ["\t".join(["node", node, label]) for node, label in nodes.items()]
    lines += ["\t".join(("edge",) + edge) for edge in edges]
    lines.append("")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: graph.py DOCUMENT\n")
        return 2
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    # Written as bytes so the edge list is UTF-8 whatever the locale says.
    sys.stdout.buffer.write(render(doc).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
