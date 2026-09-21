---
title: "Publications"
permalink: /publications/
layout: single
classes: wide
---

<div style="margin-bottom: 1.5em;">
  <input type="text" id="pub-search" placeholder="Filter by title, author, venue, or keyword..." style="width: 100%; padding: 0.6em; font-size: 1em; border: 1px solid #ccc; border-radius: 4px;">
  <div id="pub-search-count" style="margin-top: 0.3em; font-size: 0.85em; color: #666;"></div>
</div>

{% assign pubs = site.data.lab.works %}
{% assign years = pubs | map: "year" | uniq | sort | reverse %}

{% for year in years %}
<div class="pub-year-section" data-year="{{ year }}">
<h2>{{ year }}</h2>

{% assign year_pubs = pubs | where: "year", year %}
{% assign categories = year_pubs | map: "category" | uniq %}

{% for category in categories %}
<div class="pub-category-section">
<h3>{{ category }}</h3>

{% assign cat_pubs = year_pubs | where: "category", category %}
{% for pub in cat_pubs %}
{% include publication.html pub=pub %}
{% endfor %}

</div>
{% endfor %}
</div>
{% endfor %}

<script>
document.addEventListener('DOMContentLoaded', function() {
  var searchInput = document.getElementById('pub-search');
  var countDisplay = document.getElementById('pub-search-count');
  var entries = document.querySelectorAll('.pub-entry');
  var yearSections = document.querySelectorAll('.pub-year-section');
  var catSections = document.querySelectorAll('.pub-category-section');
  var total = entries.length;

  searchInput.addEventListener('input', function() {
    var query = this.value.toLowerCase().trim();
    var shown = 0;

    entries.forEach(function(entry) {
      var text = entry.getAttribute('data-searchable') || '';
      var match = !query || text.indexOf(query) !== -1;
      entry.style.display = match ? '' : 'none';
      if (match) shown++;
    });

    // Hide empty category and year sections
    catSections.forEach(function(sec) {
      var visible = sec.querySelectorAll('.pub-entry[style=""], .pub-entry:not([style])');
      var hasVisible = Array.from(sec.querySelectorAll('.pub-entry')).some(function(e) {
        return e.style.display !== 'none';
      });
      sec.style.display = hasVisible ? '' : 'none';
    });

    yearSections.forEach(function(sec) {
      var hasVisible = Array.from(sec.querySelectorAll('.pub-entry')).some(function(e) {
        return e.style.display !== 'none';
      });
      sec.style.display = hasVisible ? '' : 'none';
    });

    countDisplay.textContent = query ? ('Showing ' + shown + ' of ' + total + ' publications') : '';
  });
});
</script>
