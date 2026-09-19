# labdata

Most academic lab websites are a mess. Publications are added by hand, people pages go stale, and project links rot. Updating the site becomes one more chore that nobody wants to do, so it falls behind.

However, most academics already maintain excellent, up-to-date BibTeX files. labdata turns that BibTeX into a website. Add one custom tag (`project`) to your entries and labdata auto-generates publications, people, and project pages with full cross-referencing.

## How It Works

labdata has two parts:

1. **The `labdata` package** reads your `.bib` files plus optional `people.yaml` and `projects.yaml`, links authors to lab members and papers to projects, and writes a single YAML or JSON file. It has no opinion about how you render it.
2. **An optional Jekyll site template** in [`site/`](site/) turns that file into publications, people and project pages, and a GitHub Actions workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) builds and deploys it to GitHub Pages.

Keep your data and site in your own repository, install labdata there, and regenerate the site whenever your BibTeX changes. No manual HTML editing, no copy-paste errors, no drift between your papers and your website.

**[See a live example →](https://siddhss5.github.io/labdata/)** It is built from the fictional Example Lab in [`examples/demo/`](examples/demo/).

## What You Get

- **Publications page** with search, collapsible abstracts, BibTeX copy buttons, and DOI/arXiv links
- **People page** with current members, alumni, and external collaborators, all auto-detected from paper co-authorship
- **Projects page** with linked publications (tag papers in BibTeX with `project = {myproject}`)
- **Landing page** with your lab name, description, and links

The site uses the [Minimal Mistakes](https://mmistakes.github.io/minimal-mistakes/) Jekyll theme and deploys to GitHub Pages for free.

## Setup

### 1. Install labdata

```bash
pip install git+https://github.com/siddhss5/labdata.git
```

### 2. Write `lab.yaml`

In your own repository:

```yaml
lab:
  name: "My Lab"
  description: "What our lab does"
  university: "University Name"
  website: "https://mylab.example.org"

# Optional: settings for the Jekyll site template
site:
  url: "https://my-org.github.io"
  baseurl: "/my-lab-site"   # "" if the site is served from the domain root

bib_dir: "data/bib"
bib_files:
  - name: "journal.bib"
    category: "Journal Papers"
  - name: "conference.bib"
    category: "Conference Papers"

pdf_base_url: "https://mylab.example.org/pdfs"
people_file: "data/people.yaml"       # optional
projects_file: "data/projects.yaml"   # optional
```

Paths are relative to the directory you run `labdata` from. [`examples/demo/lab.yaml`](examples/demo/lab.yaml) is a complete example.

### 3. Add your data

- Put your `.bib` files in `data/bib/`
- Optionally create `data/people.yaml` for lab members (see below)
- Optionally create `data/projects.yaml` for research projects (see below)

Then check it:

```bash
labdata --config lab.yaml --validate
```

### 4. Build a site (optional)

Copy [`site/`](site/), [`scripts/generate_site_config.py`](scripts/generate_site_config.py) and [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) into your repository and point the workflow at your `lab.yaml`. To preview locally:

```bash
labdata --config lab.yaml --output site/_data/lab.yml
python scripts/generate_site_config.py lab.yaml site/_config.generated.yml
cd site && bundle install
bundle exec jekyll serve --config _config.yml,_config.generated.yml
```

Which file owns which setting:

| Setting | Where it comes from |
|---------|---------------------|
| Site title and description | `lab.name` and `lab.description` in `lab.yaml` |
| Site `url` and `baseurl` | the `site` section of `lab.yaml` |
| Theme, plugins and page layout | `site/_config.yml` |
| Navigation menu | `site/_data/navigation.yml` |

`scripts/generate_site_config.py` writes the `lab.yaml` values to `site/_config.generated.yml`, and Jekyll layers that file over the committed base config, `site/_config.yml`. `site/_config.generated.yml` and `site/_data/lab.yml` are generated at build time and are not committed.

### 5. Deploy

Enable GitHub Pages in your repo settings (Source: GitHub Actions) and push. The workflow generates the site data and config, builds the site with Jekyll, and deploys it.

## Data Files

### BibTeX (required)

Standard `.bib` files. labdata extracts the following standard BibTeX fields:

| Field | Used for |
|-------|----------|
| `title` | Publication title (LaTeX converted to Markdown) |
| `author` | Author list (auto-matched to lab members) |
| `year` | Sorting and grouping |
| `booktitle` / `journal` | Venue display |
| `doi` | DOI link button |
| `eprint` + `archivePrefix` | arXiv link button |
| `abstract` | Collapsible abstract panel |
| `note` | Highlighted note (e.g. "Best Paper Award") |
| `url` | Video link (if YouTube/Vimeo) or generic link |

All fields are also preserved in the copyable BibTeX button.

### The `project` tag

labdata introduces one custom BibTeX field: `project`. Add it to any entry to link that paper to a research project:

```bibtex
@inproceedings{morales2024pantry,
  title     = {Where Does This Go? Object Placement in Unfamiliar Kitchens},
  author    = {Morales, Diego and Tanaka, Mei and Chen, Wei and Quinn, Avery},
  booktitle = {Proceedings of the Conference on Robot Learning Systems},
  year      = {2024},
  eprint    = {2406.99812},
  archivePrefix = {arXiv},
  abstract  = {A robot that has never seen a kitchen must still guess where...},
  note      = {\textbf{Best Paper Award}},
  project   = {homebot}
}
```

This single tag is all labdata needs to auto-generate project pages with linked publications and contributing authors. You can assign multiple projects with commas: `project = {homebot, sharedcontrol}`.

### People (optional, `data/people.yaml`)

A list of lab members and alumni. The `aliases` field tells labdata how to match BibTeX author names to people:

```yaml
- id: "praman"
  name: "Priya Raman"
  aliases: ["P. Raman"]
  role: "phd_student"
  status: "current"
  website: "https://example.org/people/praman"
  co_advisor: "Nadia Haddad"
  start_year: 2021

- id: "riyer"
  name: "Ravi Iyer"
  aliases: ["R. Iyer"]
  role: "phd_student"
  status: "alumni"
  start_year: 2016
  end_year: 2022
  degree: "PhD"
  thesis_title: "Learning Grasp Affordances from Play"
  current_position: "Research Scientist, Example Robotics Inc."
```

### Projects (optional, `data/projects.yaml`)

```yaml
- id: "homebot"
  title: "Household Manipulation"
  description: "Robots that tidy up, fetch things and put them away in real homes."
  website: "https://example.org/projects/homebot"
  status: "active"
```

## Validation

```bash
# Check data quality
labdata --config lab.yaml --validate

# List author names that couldn't be matched to lab members
labdata --config lab.yaml --unresolved
```

## How Author Matching Works

labdata matches BibTeX author names to lab members in two passes:

1. **Exact alias match** — checks against the `aliases` list in `people.yaml` (after normalizing case, accents, and punctuation)
2. **Fuzzy fallback** — uses string similarity (threshold: 0.85) to catch minor spelling variations

Anyone not matched is listed as a collaborator. Use `labdata --unresolved` to review unmatched names and add aliases as needed.

## Python API

If you want to use labdata programmatically instead of (or in addition to) the Jekyll site:

```python
from labdata import LabDataConfig, assemble, export_to_yaml

config = LabDataConfig.from_yaml("lab.yaml")
data = assemble(config)

# Export to file
export_to_yaml(data, "lab.yml")

# Or work with the data directly
for pub in data.publications:
    authors = ", ".join(a.name for a in pub.authors)
    print(f"{pub.title} ({authors})")
```

The output is a single YAML/JSON file that works with Jekyll, Hugo, Flask, Eleventy, React, or anything else.

## Dependencies

- **bibtexparser** — BibTeX parsing
- **pyyaml** — YAML I/O

No network calls. All processing is local and offline.

## License

MIT License. Copyright (c) 2024 Personal Robotics Laboratory, University of Washington.
