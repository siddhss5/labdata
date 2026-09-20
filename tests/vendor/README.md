# Vendored third-party files

Files copied into this repository from elsewhere, so the test suite can use
them without a network fetch. Nothing here is labdata's own work, and nothing
here is modified: each file is byte-for-byte the upstream file at the pinned
revision.

## `csl-data.json`

The published CSL-JSON input schema, used by
`tests/conformance/test_consumer_probes.py` to validate what
`examples/consumers/csl_json.py` emits.

| | |
|---|---|
| Upstream | <https://github.com/citation-style-language/schema> |
| Path there | `schemas/input/csl-data.json` |
| Pinned at | commit `40b3ce0bbbda517ad14b98c93a2c65ab4cde56a9` (2022-03-21), the newest commit to touch that file |
| Source URL | <https://raw.githubusercontent.com/citation-style-language/schema/40b3ce0bbbda517ad14b98c93a2c65ab4cde56a9/schemas/input/csl-data.json> |
| Retrieved | 2026-09-20 |
| SHA-256 | `23b2c062d7526060f4631bb04b4b3ba237e488484253e327bd00fa691861b811` |
| Licence | MIT (`LICENSE.txt` in the upstream repository) |
| Schema dialect | JSON Schema draft-07, which the existing `jsonschema>=4` test dependency supports |

Pinned by commit rather than by release: the newest release of that
repository, `v1.0.2`, predates this revision of the file.

Every `$ref` in it is local (`#/definitions/...`), so validating against it
resolves nothing over the network and the test suite stays offline.

To refresh it, download the file at a new commit, replace it unmodified, and
update every row above.
