"""Install this tool's pinned dependencies into its local environment."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def main():
    root = Path(__file__).resolve().parent
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or newer is required.')
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not node or not npm:
        raise SystemExit('Install Node.js 22 LTS or newer, reopen your terminal, then run python install.py again.')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 22:
        raise SystemExit('Node.js 22 or newer is required.')
    env_dir = root / '.venv'
    python = env_dir / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        print('Creating local Python environment...', flush=True)
        venv.EnvBuilder(with_pip=True).create(env_dir)
    print('Installing Python dependencies...', flush=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')], cwd=root, check=True)
    print('Installing Samsung Notes parser...', flush=True)
    subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=root, check=True)
    print('Ready. Run: python convert.py "your-file.sdocx"')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Installation failed: {error}') from error
