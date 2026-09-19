# Examples

Minimal examples showing how to use labdata from the command line and from Python.

All examples use the fictional **Example Lab** in [`demo/`](demo/): three BibTeX files,
`people.yaml` and `projects.yaml`. Every person, paper and URL in it is invented.
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
relative to the repository root, plus the `site` settings used to build the demo site.

## Jekyll Site

For a complete Jekyll site that renders labdata output, see the [`site/`](../site/) directory.
The live demo site is built from `demo/lab.yaml`.
