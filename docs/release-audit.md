# Public release preparation audit

This audit covers the secured local Canary source and existing experiment archives. It does not claim that the GitHub repository or its draft artifact release is already public.

## Source and Entire

Commit `bd87b0c` preserves the good local demo, presentation, and README on `release/canary-v0.1.0`. Remote main was inspected at `d5b67fd`. Its two newer benchmark-inference commits were kept separate. No source branch was force-pushed and no normal Git history was rewritten.

The user requested removal of Entire after the hackathon. The repository uninstall removed its agent hooks, Git hooks, local session state, metadata directory, and shadow branch. Three remaining local checkpoint refs and sixteen remote Entire-only refs were removed. Source branches, release tags, and model archives remain intact.

Old source commits can retain former recording configuration and commit trailers. Other clones and provider caches are outside this deletion. Normal Git history remains as requested.

## Secret and privacy review

Gitleaks 8.30.1 scanned normal source branches, tags, and remote-tracking history with redacted output. It reported one credential match. The value is Backblaze's intentionally public read-only dataset key, verified against the publisher's [Drive Stats access instructions](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data).

The scan passes with an exception restricted to that exact public key in `src/driftops/acquire.py`. All other default rules remain active. The exception is in `.gitleaks.toml`. No private credential was detected in that history scan. Automated scanning cannot establish that no secret exists.

Current setup, architecture, release, and handoff documents no longer depend on personal home directories or private deployment routes. Historical source commits remain unchanged. The original model and dataset evidence retains its provenance.

## Verification

Final source, browser, package, and artifact checks are recorded here after completion. Training and paid compute are outside this release-preparation task.

## Publication boundary

The repository was private and `v2026.09.13` was a draft at inspection. Anonymous clone and artifact download must be checked after publication. The original experiment archives must not be replaced merely to update source release notes.

Sources for release tooling: [MIT license](https://opensource.org/license/mit), [Playwright CI guidance](https://playwright.dev/docs/ci-intro), and [Gitleaks](https://github.com/gitleaks/gitleaks).
