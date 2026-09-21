# Examples

Minimal examples showing how to use labdata from the command line and from Python.

All examples use the fictional **Example Lab** in [`demo/`](demo/): four BibTeX files,
`people.yaml` and `projects.yaml`. Its people, works and projects, and their
example.org, DOI, arXiv and video links, are invented.
Run the commands below from this `examples/` directory.

## Command Line

```bash
# Generate YAML output
labdata --config config.yaml --output lab.yml

# Generate JSON output
labdata --config config.yaml --format json --output lab.json

# Validate data and see a summary
labdata --config config.yaml --validate

# List author names that couldn't be matched to lab members
labdata --config config.yaml --unresolved
```

## Python API

```python
from labdata import LabDataConfig, assemble, export_to_yaml

config = LabDataConfig.from_yaml("config.yaml")
data = assemble(config)
export_to_yaml(data, "lab.yml")
```

See `basic_usage.py` for a more complete example that inspects the assembled data.

## Configuration

See `config.yaml` for an annotated example of the configuration format. It points at
the files in `demo/`. [`demo/lab.yaml`](demo/lab.yaml) configures the same lab with paths
relative to the repository root.

## Consumer Probes

[`consumers/`](consumers/) holds five small programs that read the emitted
document and nothing else — an HTML page, a LaTeX CV fragment, a CSL-JSON
export, an edge list and a BibTeX re-emission. They are falsification tests
rather than examples to copy: four of them cannot be written against the
current schema, and that is the point. See [`consumers/README.md`](consumers/README.md).

## Demo Site

[labdata-site](https://github.com/siddhss5/labdata-site) is an optional
downstream renderer of labdata output. It keeps its own copy of the Example Lab
and builds the demo site from it.
