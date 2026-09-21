---
title: ""
permalink: /
layout: single
classes: wide
---

{% assign info = site.data.lab.lab %}
{% assign pubs = site.data.lab.works %}
{% assign people = site.data.lab.people %}
{% assign current = people | where: "status", "current" %}
{% assign alumni = people | where: "status", "alumni" %}
{% assign projects = site.data.lab.projects %}

{% if info %}
<div style="margin-bottom: 1.5em;">
  <h2 style="margin-bottom: 0.3em;">{{ info.name }}</h2>
  <div style="color: #555; margin-bottom: 0.8em;">{{ info.department }}, {{ info.university }}</div>
  <p style="font-size: 1.05em;">{{ info.description }}</p>
  <div>
    {% if info.website %}<a href="{{ info.website }}" class="btn btn--inverse btn--small" target="_blank">Website</a>{% endif %}
    {% if info.github %}<a href="{{ info.github }}" class="btn btn--inverse btn--small" target="_blank">GitHub</a>{% endif %}
    {% if info.youtube %}<a href="{{ info.youtube }}" class="btn btn--inverse btn--small" target="_blank">YouTube</a>{% endif %}
  </div>
</div>
<hr>
{% endif %}

<div style="margin-bottom: 2em; font-size: 1.05em;">
<strong>{{ pubs.size }}</strong> publications, <strong>{{ current.size }}</strong> current members, <strong>{{ alumni.size }}</strong> alumni, and <strong>{{ projects.size }}</strong> research projects.
</div>

## Browse

- [**Publications**]({{ '/publications/' | relative_url }}) — Full list of papers with search, abstracts, and BibTeX
- [**People**]({{ '/people/' | relative_url }}) — Current members, alumni, and collaborators
- [**Projects**]({{ '/projects/' | relative_url }}) — Research projects with linked publications

---

## Recent Publications

{% assign recent = pubs | slice: 0, 10 %}
{% for pub in recent %}
{% include publication.html pub=pub %}
{% endfor %}

[View all {{ pubs.size }} publications &rarr;]({{ '/publications/' | relative_url }})
