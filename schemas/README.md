# Schemas (version 1)

JSON Schemas for the files the harness writes. Change a schema only together with a version bump and a migration note.

| Schema | Validates |
| --- | --- |
| [`run-artifact-v1.json`](run-artifact-v1.json) | One run artifact (one library, one profile, one run) |
| [`provenance-v1.json`](provenance-v1.json) | The provenance block inside each run artifact |
| [`artifact-manifest-v1.json`](artifact-manifest-v1.json) | The per-suite `artifact-manifest.json` written by aggregation |

`classifier/verify_manifest.py` validates each manifest and every run it references against these schemas (needs `jsonschema`, installed by `make venv`).

```bash
make verify-manifest LOG_DIR=logs/suite-pace-<timestamp> MANIFEST=suites/pace.json
```
