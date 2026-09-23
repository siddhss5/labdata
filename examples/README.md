# Examples

Minimal examples showing how to use sslabdata from the command line and from Python.

All examples use the fictional **Example Lab** in [`demo/`](demo/): four BibTeX files,
`people.yaml` and `projects.yaml`. Its people, works and projects, and their
example.org, DOI, arXiv and video links, are invented.
Run the commands below from this `examples/` directory.

## Command Line

```bash
# Generate YAML output
sslabdata --config config.yaml --output lab.yml

# Generate JSON output
sslabdata --config config.yaml --format json --output lab.json

# Validate data and see a summary
sslabdata --config config.yaml --validate

# List author names that couldn't be matched to lab members
sslabdata --config config.yaml --unresolved
```

## Python API

```python
from sslabdata import LabDataConfig, assemble, export_to_yaml

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

[`consumers/`](consumers/) holds three small programs that read the emitted
document and nothing else — a LaTeX CV fragment, a CSL-JSON export and an edge
list. They are falsification tests rather than examples to copy: a probe that
cannot be written from the document alone is a schema bug. See
[`consumers/README.md`](consumers/README.md).

## Demo Site

[sslabdata-site](https://github.com/siddhss5/sslabdata-site) is an optional
downstream renderer of sslabdata output. It keeps its own copy of the Example Lab
and builds the demo site from it.
