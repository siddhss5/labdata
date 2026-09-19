---
title: "Projects"
permalink: /projects/
layout: single
classes: wide
---

{% assign projects = site.data.lab.projects %}
{% assign pubs = site.data.lab.publications %}

{% if projects.size == 0 %}
<p><em>No projects data configured yet. Add a <code>projects_file</code> to your labdata config to populate this page.</em></p>
{% else %}

{% for project in projects %}
<div id="{{ project.id }}" style="margin-top: 2.5em;">

<h2 style="display: inline; margin-right: 0.5em;">{{ project.title }}</h2>
{% if project.status == "active" %}
  {% if project.website %}
    <a href="{{ project.website }}" target="_blank" class="btn btn--success btn--small">Active</a>
  {% else %}
    <span class="btn btn--success btn--small">Active</span>
  {% endif %}
{% else %}
  <span class="btn btn--secondary btn--small">{{ project.status | capitalize }}</span>
{% endif %}
<a href="{{ '/projects/' | relative_url }}#{{ project.id }}" class="btn btn--info btn--small">{{ project.id }}</a>

{% if project.description %}
<p style="margin-top: 0.8em;">{{ project.description }}</p>
{% endif %}

{% if project.publication_ids.size > 0 %}
<details>
<summary style="cursor: pointer; font-size: 1.17em; font-weight: bold; margin-top: 0.5em; margin-bottom: 0.5em;">Publications ({{ project.publication_ids.size }})</summary>
<div style="margin-top: 0.8em;">
{% for pub_id in project.publication_ids %}
  {% assign pub = pubs | where: "bib_id", pub_id | first %}
  {% if pub %}
<div style="margin-bottom: 1.2em;">
  <div>
    {% if pub.pdf_url %}
      <a href="{{ pub.pdf_url }}">{{ pub.title }}</a>
    {% else %}
      {{ pub.title }}
    {% endif %}
  </div>
  <div style="font-size: 0.9em; color: #494e52;">
    {% for author in pub.authors %}{{ author.name }}{% unless forloop.last %}, {% endunless %}{% endfor %}
  </div>
  <div style="font-size: 0.9em; color: #494e52;">
    {{ pub.venue | markdownify | remove: "<p>" | remove: "</p>" }}
  </div>
  {% if pub.note or pub.url or pub.video_url %}
  <div style="font-size: 0.9em; margin-top: 0.2em;">
    {% if pub.url %}<a href="{{ pub.url }}" style="margin-right: 0.6em;">Website</a>{% endif %}
    {% if pub.video_url %}<a href="{{ pub.video_url }}" style="margin-right: 0.6em;">Video</a>{% endif %}
    {% if pub.note %}<strong>{{ pub.note | markdownify | remove: "<p>" | remove: "</p>" }}</strong>{% endif %}
  </div>
  {% endif %}
</div>
  {% endif %}
{% endfor %}
</div>
</details>
{% endif %}

</div>
{% endfor %}

{% endif %}
