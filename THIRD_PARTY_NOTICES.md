# Third-party sources and notices

## Fit4Function

- Source: https://github.com/vector-engineering/fit4function
- Pinned commit: `6bfc2ebfe4abcd45cc6fe737e4700242a5090fee`
- Code license: BSD 3-Clause, copyright 2023 The Broad Institute, Inc.
- The upstream notice is preserved verbatim in `LICENSES/Fit4Function-BSD-3-Clause.txt`.
- Paper: https://doi.org/10.1038/s41467-024-50555-y (CC BY 4.0 article).
- Public input and derived-file identities: `docs/data_manifest.json`.

Code and article licenses must not be assumed to settle every dataset or resource's
redistribution terms. Raw research data and dependency binaries are not bundled
by the audit/export script. Public-read sources are documented in the existing
runbook and SRA/ENA manifests; any additional redistribution terms need checking
at the source before distributing those data.

## Literature metadata

Published capsid names, citations, roles and caveats come from
`docs/audit_data/literature_public_7mers.csv`. The retrospective report retains
citations and caveats. Publication does not grant a project license or imply
permission for every downstream use. No full papers are redistributed by 7.0.

## Python dependencies and system tools

Direct and optional packages are declared in `pyproject.toml`; versions and
transitive sources are resolved in `uv.lock`. The audit records actually installed
versions separately in `logs/audit_environment_requirements.txt`.

Core dependencies include NumPy, pandas, SciPy, scikit-learn, PyYAML, requests and
openpyxl. Optional packages include PyTorch, LightGBM, matplotlib and seaborn;
development uses pytest and Ruff. Refer to each installed distribution's LICENSE
or dist-info license files for its full applicable notices. Dependency packages
are installed separately, not vendored here.

Bowtie2 and the NCBI SRA Toolkit are optional external reconstruction tools. Their
presence/version in the current audit host is recorded, with null for unavailable
tools. No binary redistribution is authorized by this notice.

## Original project code

See `LICENSE_STATUS.md`; a project license has not been chosen by this audit.
