# Public release audit

This audit covers the verified Canary source, preserved Git history, and unchanged experiment archives in [Bitarious/Canary](https://github.com/Bitarious/Canary).

## Source and Entire

Commit `bd87b0c` preserves the good local demo, presentation, and README on `release/canary-v0.1.0`. Remote main was inspected at `d5b67fd`. Its two newer benchmark-inference commits remain in Git ancestry, but their code is excluded from this release. The release merge keeps the verified local tree. The new public repository preserves this ancestry without changing the original repository. No source branch was force-pushed and no normal Git history was rewritten.

The user requested removal of Entire after the hackathon. The repository uninstall removed its agent hooks, Git hooks, local session state, metadata directory, and shadow branch. Three remaining local checkpoint refs and sixteen remote Entire-only refs were removed. Source branches, release tags, and model archives remain intact.

Old source commits can retain former recording configuration and commit trailers. Other clones and provider caches are outside this deletion. Normal Git history remains as requested.

## Secret and privacy review

Gitleaks 8.30.1 scanned normal source branches, tags, and remote-tracking history with redacted output. It reported one credential match. The value is Backblaze's intentionally public read-only dataset key, verified against the publisher's [Drive Stats access instructions](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data).

The scan passes with an exception restricted to that exact public key in `src/driftops/acquire.py`. All other default rules remain active. The exception is in `.gitleaks.toml`. No private credential was detected in that history scan. Automated scanning cannot establish that no secret exists.

Current setup, architecture, release, and handoff documents no longer depend on personal home directories or private deployment routes. Historical source commits remain unchanged. The original model and dataset evidence retains its provenance.

## Verification

The release code at `b284e65` passed these checks in a fresh local Git clone with a new locked Python environment:

| Check | Result |
| --- | --- |
| Native pilot rebuild | 3,000 records, 547,812 observations, 13,616 tasks |
| Core pytest suite | 97 passed, no skips |
| Separate demo API suite | 9 passed |
| Committed evidence integrity | 187 hashes passed |
| Browser evidence checks | Passed at 390×844, 768×1024, 1440×900, and 2560×1440 |
| Browser navigation | All three HQ laptops and a Site A server passed picking, geometry, camera, analysis, and return checks |
| Python source distribution and wheel | Built successfully; MIT metadata and upstream notices present |
| Pip compatibility requirements | Dry run against the locked environment required no changes |
| README SSD inference replay | All 16 saved GPU answers reproduced using the clean-checkout CPU environment |
| Current public documentation | Local links, anchors, and Bash syntax passed |
| Original release archives | All 15 archive hashes passed; 14 checkpoint files retained |
| Release metadata secret scan | 11,200 text files, 310,681,584 bytes; no findings |
| Clean source and normal history scans | No findings after the narrow public Backblaze key exception |

The browser harness stopped its temporary server and browser. Python dependencies came from the local package cache. Browser dependencies used the lockfile and a temporary Playwright Chromium download. The pipeline required no project credentials or GPU for these checks. The [GitHub-hosted verification run](https://github.com/Bitarious/Canary/actions/runs/34775866945) passed all three jobs at `193d5cc`: pilot, browser, and secrets.

An anonymous HTTPS clone of `Bitarious/Canary` contained all 32 normal source commits then present locally. Its fresh locked environment rebuilt the pilot and passed 97 core tests, nine demo API tests, and all 187 evidence hashes.

Training and paid compute were not started. Full model retraining remains a separate bounded experiment. The source and model archives preserve their independent revision and checksum identities.

## Publication boundary

The new `Bitarious/Canary` repository is public with `main` as its default branch. The original hackathon repository and its draft release remain unchanged by this publication.

The public `v2026.09.13` release contains all 17 original assets. GitHub asset sizes and SHA-256 digests match the local originals. Anonymous downloads of `SHA256SUMS`, `release-manifest.json`, and the complete 547,711,350-byte SSD model archive passed checksum verification. The experiment tag retains source commit `c372b6d`.

The `v0.1.0` source archive has its own manifest and checksums. Historical experiment manifests retain the original repository identity. These are provenance records, not the current download location.

Sources for release tooling: [MIT license](https://opensource.org/license/mit), [Playwright CI guidance](https://playwright.dev/docs/ci-intro), and [Gitleaks](https://github.com/gitleaks/gitleaks).
