# Bundled public Backblaze pilot

This 1.2 MB Parquet extract contains the 3,000-drive, July–December 2024
`ST8000NM0055` pilot used by DriftOps. Each row is an actual daily observation.
It is bundled so a fresh clone can prepare the same TimeNet dataset without
network acquisition or account credentials.

Source: [Backblaze Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data).
Credit Backblaze when using the data. Backblaze permits derivative works but
does not permit selling the raw dataset. The source terms apply to these data;
they do not inherit a software license from this repository.

The accompanying manifest records the exact Iceberg snapshot, query selection,
date bounds, columns, checksum, and limitations. See
[data preparation](../../docs/data-preparation.md) for details.

`driftops prepare` validates the checksum, installs a working copy under `data/`,
builds TimeF, and verifies every record and task. Re-running it verifies and
reuses the existing version. It does not fit a model or create cloud resources.
