"""Build a source-only ZIP from an explicit list, never the workspace contents."""
from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
FILES = (
    '.gitignore', '.gitattributes', '.github/workflows/tests.yml',
    'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md',
    'convert.py', 'install.py', 'requirements.txt', 'package.json', 'package-lock.json',
    'chatgpt-prompt.txt', 'scripts/parse-sdocx.mjs', 'scripts/build_release.py',
    'tests/test_geometry.py', 'tests/test_conversion.py',
)


def build():
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit(f'Missing release files: {missing}')
    target = ROOT / 'dist' / f'sdocx-to-md-{VERSION}.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, f'sdocx-to-md-{VERSION}/{name}')
    print(f'Created {target} ({target.stat().st_size:,} bytes; {len(FILES)} files)')
    return target


if __name__ == '__main__':
    build()
