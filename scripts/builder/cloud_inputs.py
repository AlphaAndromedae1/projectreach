#!/usr/bin/env python3
"""Your Custom Edition files for a cloud build, read from GitHub repository secrets.

The workflow .github/workflows/halopad-cloud-build.yml builds both editions on
GitHub's Apple silicon Mac runner, so no Mac of your own is needed. A fork of this
repository is public, so your files never go into it. Instead, three secrets hold:

  HALOCE_SETUP_URL        a private download link to your HaloCESetup.exe (or to a
                          .zip/.7z holding it; haloce-patch-1.0.10.exe may be beside it)
  HALO_PRODUCT_KEY        your Halo PC product key
  HALOPAD_BUILD_PASSWORD  the password that locks the finished build (12+ characters)

  check                   validate the three secrets without downloading anything
  fetch --out DIR         download and verify the installer into DIR and write your
                          product key to DIR/product-key.txt (mode 600), the layout
                          scripts/builder/build.sh reads

Nothing secret is printed. Links rewritten for direct download, and the reformatted
product key, are masked in the GitHub log as the secrets themselves are.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
SETUP_DOC = 'docs/BUILD-IN-THE-CLOUD.md'
MIN_PASSWORD = 12
ARCHIVE_MAGIC = (b'PK\x03\x04', b'7z\xbc\xaf\x27\x1c', b'Rar!\x1a\x07')


def installer_sha256():
    manifest = json.loads((ROOT / 'padmint.json').read_text())
    for item in manifest['inputs']:
        if item['type'] == 'pc-game-installer':
            return set(item['accepted_sha256'])
    raise RuntimeError('padmint.json lists no accepted Custom Edition installer')


def in_actions():
    return os.environ.get('GITHUB_ACTIONS') == 'true'


def mask(value):
    # Values derived from a secret are not masked automatically; mask before any use.
    if value and in_actions():
        print('::add-mask::' + value, flush=True)


def fail(message):
    print(('::error::' if in_actions() else 'error: ') + message, file=sys.stderr)
    sys.exit(2)


def direct_download_url(url):
    """Turn a Google Drive or Dropbox share link into a direct file download."""
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('HALOCE_SETUP_URL must be a web link starting with https://')
    host = parsed.hostname.lower()
    query = urllib.parse.parse_qs(parsed.query)
    if host in ('drive.google.com', 'docs.google.com', 'drive.usercontent.google.com'):
        found = re.search(r'/d/([A-Za-z0-9_-]{10,})', parsed.path)
        file_id = found.group(1) if found else (query.get('id') or [''])[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,}', file_id):
            raise ValueError('the Google Drive link has no file ID; use the file\'s "Share" > "Copy link"')
        # confirm=t skips Drive's "too large to scan for viruses" page.
        return ('https://drive.usercontent.google.com/download?' +
                urllib.parse.urlencode({'id': file_id, 'export': 'download', 'confirm': 't'})), file_id
    if host == 'dropbox.com' or host.endswith('.dropbox.com'):
        pairs = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                 if k not in ('dl', 'raw')]
        pairs.append(('dl', '1'))
        return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(pairs))), None
    return url.strip(), None


def normalize_key(key):
    """Halo's PIDGen reads 25 capital letters and digits; dashes and spaces are optional."""
    chars = re.sub(r'[\s-]', '', key or '').upper()
    if not re.fullmatch(r'[A-Z0-9]{25}', chars):
        raise ValueError('HALO_PRODUCT_KEY must be your 25-character Halo PC product key '
                         '(XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)')
    return '-'.join(chars[i:i + 5] for i in range(0, 25, 5))


def check_password(password):
    if len(password or '') < MIN_PASSWORD:
        raise ValueError(f'HALOPAD_BUILD_PASSWORD must be at least {MIN_PASSWORD} characters. Your build is '
                         'saved in this public repository\'s run, locked only by this password')


def missing_secrets(env):
    return [name for name in ('HALOCE_SETUP_URL', 'HALO_PRODUCT_KEY', 'HALOPAD_BUILD_PASSWORD')
            if not (env.get(name) or '').strip()]


def check(env):
    missing = missing_secrets(env)
    if missing:
        fail('add these repository secrets first: ' + ', '.join(missing) +
             f'. Settings > Secrets and variables > Actions > New repository secret. Steps: {SETUP_DOC}')
    try:
        direct_download_url(env['HALOCE_SETUP_URL'])
        normalize_key(env['HALO_PRODUCT_KEY'])
        check_password(env['HALOPAD_BUILD_PASSWORD'])
    except ValueError as error:
        fail(f'{error}. Steps: {SETUP_DOC}')
    print('Your build secrets are set: installer link, product key and build password.')


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def kind(path):
    with path.open('rb') as source:
        head = source.read(512)
    if head.startswith(b'MZ'):
        return 'exe'
    if head.startswith(ARCHIVE_MAGIC):
        return 'archive'
    if re.search(rb'<(!doctype html|html|head)\b', head.lstrip()[:64], re.IGNORECASE):
        return 'html'
    return 'other'


def collect(download, out, accepted):
    """Place the accepted installer (and any other .exe, such as the 1.10 update) in out."""
    found = None
    if kind(download) == 'exe':
        candidates = [download]
    elif kind(download) == 'archive':
        extracted = download.parent / 'extracted'
        # No password prompt: an encrypted archive fails instead of waiting for input.
        result = subprocess.run(['7zz', 'x', '-y', '-bd', '-o' + str(extracted), str(download)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            detail = (result.stderr.strip().splitlines() or ['no message'])[-1]
            raise ValueError(f'the downloaded archive could not be unpacked (7-Zip: {detail}). '
                             'Use an archive without a password')
        candidates = sorted(p for p in extracted.rglob('*') if p.is_file() and not p.is_symlink()
                            and p.suffix.lower() == '.exe')
    elif kind(download) == 'html':
        raise ValueError('the link returned a web page, not your file. Share the file as "Anyone with the link" '
                         'and use a direct download link (Google Drive and Dropbox share links are converted for you)')
    else:
        raise ValueError('the link did not return HaloCESetup.exe or a .zip/.7z/.rar holding it')
    for path in candidates:
        if digest(path) in accepted:
            if found is None:
                found = out / 'HaloCESetup.exe'
                shutil.move(str(path), found)
        elif path != download:
            # The builder recognizes the free 1.10 update by its hash; unknown files are ignored.
            target = out / path.name
            if not target.exists():
                shutil.move(str(path), target)
    if found is None:
        raise ValueError('no original Halo Custom Edition 1.00 installer (HaloCESetup.exe) with the supported '
                         'checksum was found at HALOCE_SETUP_URL. The 1.10 update patch cannot replace it')
    return found


def fetch(env, out):
    check(env)
    url, file_id = direct_download_url(env['HALOCE_SETUP_URL'])
    mask(url)
    mask(file_id)
    key = normalize_key(env['HALO_PRODUCT_KEY'])
    mask(key)
    mask(key.replace('-', ''))
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        download = pathlib.Path(temp) / 'download'
        print('Downloading your Custom Edition installer from HALOCE_SETUP_URL...', flush=True)
        # The link stays out of curl's messages (-sS prints only the error) and the log.
        result = subprocess.run(['curl', '-fL', '-sS', '--proto', '=https,http', '--retry', '3',
                                 '--retry-delay', '5', '--connect-timeout', '30', '-o', str(download), url],
                                stderr=subprocess.PIPE, text=True)
        if result.returncode or not download.is_file():
            fail('could not download HALOCE_SETUP_URL (' + (result.stderr.strip().replace(url, '<link>') or
                 f'curl exit {result.returncode}') + '). Check the link opens in a private browser window')
        try:
            installer = collect(download, out, installer_sha256())
        except ValueError as error:
            fail(f'{error}. Steps: {SETUP_DOC}')
    key_file = out / 'product-key.txt'
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(key + '\n')
    print(f'Verified the original installer ({installer.stat().st_size // (1024 * 1024)} MB) and wrote your '
          'product key for the build. Neither is saved in the repository or the run\'s artifact.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    get = sub.add_parser('fetch')
    get.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.command == 'check':
        check(os.environ)
    else:
        fetch(os.environ, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
