# Extended ingestion layout

Place literature PDFs in `.papers/` and writing guides in `.writing_guides/`.
Use CSV/TSV tables in `inputs/tables/` and describe them in `manifest.yaml`.
The new schemas live in `ingestion_schemas.py`; the existing schemas.py re-exports them for fresh projects.
Existing projects can import directly from ingestion_schemas without modifying schemas.py.
Candidate facts go in facts/candidates.json; the original facts/facts.json and inputs/facts.csv remain compatible with the existing CLI.
The new registries are templates, not automatically populated. The PDF and table readers are basic utilities; agent ingestion, approvals, configuration loading and new CLI commands are not implemented, with one exception: writing guides are read by `paperkit rules extract` (see the README).
The original wiki reads wiki/<citation-key>.md; wiki/sources and wiki/concepts are reserved for future migration.
Install PDF parsing support with python -m pip install pymupdf.
