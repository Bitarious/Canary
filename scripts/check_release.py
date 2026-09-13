"""Check bundled release evidence and required public-project files without downloads."""

import hashlib
import json
from pathlib import Path


def check(root):
    for name in ('LICENSE', 'NOTICE', 'README.md', 'CONTRIBUTING.md', 'SECURITY.md',
                 'CHANGELOG.md', 'CITATION.cff', 'docs/architecture.md', 'docs/reproduction.md'):
        if not (root / name).is_file():
            raise ValueError(f'Required release file is missing: {name}')
    evidence = root / 'results/2026-09-13'
    entries = (evidence / 'SHA256SUMS').read_text().splitlines()
    for line in entries:
        expected, name = line.split(maxsplit=1)
        path = (evidence / name.lstrip('*')).resolve()
        if not path.is_relative_to(evidence.resolve()) or not path.is_file():
            raise ValueError('Evidence checksum path is invalid')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'Evidence checksum mismatch: {name}')
    catalog = json.loads((evidence / 'model-catalog.json').read_text())
    print(f'Checked {len(entries)} evidence hashes and required release files')
    return catalog


if __name__ == '__main__':
    check(Path(__file__).resolve().parents[1])
