# Security

Canary is a research prototype. The demo server is intended for local use on `127.0.0.1`. It has no user authentication. Its optional benchmark endpoint can run a hardware collector on the server host. Do not expose this server directly to the public internet.

## Report a vulnerability

Use GitHub's private vulnerability reporting under the repository's Security tab when available. If that option is unavailable, open an issue that asks for a private contact without including exploit details or credentials. The maintainers will arrange a private report channel.

Include the affected revision, reproduction steps, impact, and proposed fix if known. Do not include private telemetry or live credentials. The project has no guaranteed security-response service level.

## Supported code

Security fixes target the latest release and the default branch. Historical experiments and their metrics remain immutable. Model and dataset access terms are separate from this policy.

## Data handling

Keep credentials, local device histories, cloud account files, and downloaded artifacts outside Git. Check source, Git history, and release metadata before publication. The public Backblaze read-only dataset credential is intentionally distinct from a user's private credentials.
