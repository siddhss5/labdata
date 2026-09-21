#!/usr/bin/env python3
"""Consumer probe: a person / project / work edge list.

    python examples/consumers/graph.py lab.json > graph.tsv

Standard library only. Reads the document named on the command line and
nothing else. See README.md in this directory for the rule this probe exists
to test, and for why this probe cannot produce a complete graph today.

Output is tab separated, one record per line:

    node	person:aadams	Alice Adams
    node	collaborator:t-turner-9d9cc45d	Trent Turner
    edge	authored	person:aadams	work:brown2025tidy	3
    edge	part_of	work:brown2025tidy	project:homebot
    edge	member_of	person:aadams	project:homebot

An `authored` edge carries a fourth column, the authorship's position in its
work's author list. It is there because a work lists *authorships*, not
contributors: two different people written alike are two authorships of one
work, and without the position the two records would be one line and the
distinction would be gone from the output whatever the document said.

This is also where the identity questions are asked, because the node and
edge sets below are already what those questions are about. A graph has to
decide, for every co-author, whether two authorships are one contributor or
two -- the same external person written two ways is one node with an edge to
each of their works, two different people who write their names alike are two
authorships of one work that must stay apart, and two people who merely share
an initial and a surname are two nodes. The tests in
tests/conformance/test_consumer_probes.py put those cases to this probe. It
answers none of them today, and it does not guess: the only thing the
document offers to key a co-author on is the display name, and keying on that
is exactly the merge the document itself warns against.

Two namespaces, never one. `people` is a list of humans; `collaborators` is a
*grouping over unresolved authorships*, which is not the same kind of thing
and must not be labelled as if it were. So a lab member is `person:<id>` and
a group is `collaborator:<key>`, and an unresolved string is never labelled a
person. Both sides work: `people` carries ids and an authorship that resolved
carries `person_id`, while `collaborators` carries a `key` and an authorship
that resolved to nobody carries the `collaborator_key` of the grouping it
fell into.
"""

import json
import sys


def clean(text):
    """A label with no tab or newline in it, so one record stays one line."""
    return " ".join(str(text).split())


def contributor_nodes(doc):
    """{node id: label} for everyone an authorship could point at.

    A lab member has an `id` in `people`. A co-author who is not one reaches
    the graph only through `collaborators`, whose entries are read here for
    a `key` -- the lookup key a grouping offers, as against an `id`, which
    would be a claim about a human that a name-derived value cannot support.
    """
    nodes = {}
    for person in doc["people"]:
        nodes["person:" + person["id"]] = clean(person["name"])
    for collaborator in doc["collaborators"]:
        key = collaborator.get("key")
        if key:
            nodes["collaborator:" + key] = clean(collaborator["name"])
    return nodes


def contributor_of(author):
    """The node one authorship points at, or None if it points at nothing.

    An authorship references exactly one contributor. `person_id` is defined
    by the schema as the id of the matching person in people.yaml and means
    nothing else, so it is never widened to reach a collaborator;
    `collaborator_key` is the reference an authorship that matched nobody
    would carry. Neither is inferred from a name.
    """
    if author.get("person_id"):
        return "person:" + author["person_id"]
    if author.get("collaborator_key"):
        return "collaborator:" + author["collaborator_key"]
    return None


def position_of(author, index):
    """Where in its work's author list one authorship sits, 1-based.

    `position` is read when the document declares it. Otherwise the index is
    used, and that is faithful rather than a guess: the document states that
    `work.authors` is in the order the entry wrote them (SPEC.md section 3),
    so the index is that order and nothing is being invented.
    """
    return str(author.get("position") or index)


def render(doc):
    contributors = contributor_nodes(doc)
    works = {"work:" + p["bib_id"]: clean(p["title"]) for p in doc["works"]}
    projects = {"project:" + p["id"]: clean(p["title"]) for p in doc["projects"]}

    nodes = {}
    nodes.update(contributors)
    nodes.update(works)
    nodes.update(projects)

    edges = []
    for pub in doc["works"]:
        work = "work:" + pub["bib_id"]
        for index, author in enumerate(pub["authors"], 1):
            node = contributor_of(author)
            if node in contributors:
                edges.append(("authored", node, work, position_of(author, index)))
        for project_id in pub["project_ids"]:
            project = "project:" + project_id
            if project in projects:
                edges.append(("part_of", work, project))
    for project in doc["projects"]:
        for person_id in project["people_ids"]:
            node = "person:" + person_id
            if node in contributors:
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
