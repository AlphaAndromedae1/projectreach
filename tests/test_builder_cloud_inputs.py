"""The cloud build's secrets: share links, product key, password and the downloaded installer."""
import hashlib
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cloud_inputs', ROOT / 'scripts/builder/cloud_inputs.py')
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)

INSTALLER = b'MZ fixture installer'
PATCH = b'MZ fixture 1.10 update'
ACCEPTED = {hashlib.sha256(INSTALLER).hexdigest()}
GOOD = {'HALOCE_SETUP_URL': 'https://example.com/HaloCESetup.exe',
        'HALO_PRODUCT_KEY': 'abcde-fghij-klmno-pqrst-uvwxy',
        'HALOPAD_BUILD_PASSWORD': 'correct horse battery'}


class LinkTests(unittest.TestCase):
    def test_google_drive_share_links_download_directly(self):
        expected = 'https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOp&export=download&confirm=t'
        for link in ('https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing',
                     'https://drive.google.com/open?id=1AbCdEfGhIjKlMnOp',
                     'https://drive.google.com/uc?id=1AbCdEfGhIjKlMnOp&export=download'):
            self.assertEqual(cloud.direct_download_url(link), (expected, '1AbCdEfGhIjKlMnOp'))

    def test_google_drive_folder_or_bad_link_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no file ID'):
            cloud.direct_download_url('https://drive.google.com/drive/my-drive')

    def test_dropbox_share_link_downloads_directly(self):
        url, file_id = cloud.direct_download_url(
            'https://www.dropbox.com/scl/fi/abc/HaloCESetup.exe?rlkey=xyz&dl=0')
        self.assertEqual(url, 'https://www.dropbox.com/scl/fi/abc/HaloCESetup.exe?rlkey=xyz&dl=1')
        self.assertIsNone(file_id)

    def test_other_links_unchanged_and_non_web_rejected(self):
        self.assertEqual(cloud.direct_download_url(' https://example.com/a.exe '), ('https://example.com/a.exe', None))
        for link in ('file:///etc/passwd', 'HaloCESetup.exe', 'ftp://example.com/a.exe'):
            with self.assertRaisesRegex(ValueError, 'web link'):
                cloud.direct_download_url(link)


class KeyAndPasswordTests(unittest.TestCase):
    def test_key_normalized_for_pidgen(self):
        # pid.c reads capital letters and digits only.
        for key in ('abcde-fghij-klmno-pqrst-uvwxy', 'ABCDEFGHIJKLMNOPQRSTUVWXY', ' abcde fghij klmno pqrst uvwxy\n'):
            self.assertEqual(cloud.normalize_key(key), 'ABCDE-FGHIJ-KLMNO-PQRST-UVWXY')

    def test_bad_keys_rejected(self):
        for key in ('', 'ABCDE-FGHIJ-KLMNO-PQRST', 'ABCDE-FGHIJ-KLMNO-PQRST-UVWX!', 'A' * 26):
            with self.assertRaisesRegex(ValueError, '25-character'):
                cloud.normalize_key(key)

    def test_short_password_rejected(self):
        with self.assertRaisesRegex(ValueError, 'at least 12'):
            cloud.check_password('short')
        cloud.check_password('twelve chars')

    def test_check_names_missing_secrets_without_values(self):
        env = dict(GOOD, HALO_PRODUCT_KEY=' ', HALOPAD_BUILD_PASSWORD='')
        self.assertEqual(cloud.missing_secrets(env), ['HALO_PRODUCT_KEY', 'HALOPAD_BUILD_PASSWORD'])
        with mock.patch('sys.stderr') as stderr, self.assertRaises(SystemExit):
            cloud.check(env)
        written = ''.join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn('HALO_PRODUCT_KEY, HALOPAD_BUILD_PASSWORD', written)
        self.assertNotIn(GOOD['HALOCE_SETUP_URL'], written)


class CollectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = pathlib.Path(temp.name)
        self.out = self.base / 'out'
        self.out.mkdir()
        (self.base / 'dl').mkdir()
        self.download = self.base / 'dl' / 'download'

    def test_installer_exe_placed_by_hash(self):
        self.download.write_bytes(INSTALLER)
        found = cloud.collect(self.download, self.out, ACCEPTED)
        self.assertEqual(found, self.out / 'HaloCESetup.exe')
        self.assertEqual(found.read_bytes(), INSTALLER)

    def test_wrong_exe_rejected(self):
        self.download.write_bytes(PATCH)
        with self.assertRaisesRegex(ValueError, 'cannot replace it'):
            cloud.collect(self.download, self.out, ACCEPTED)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_web_page_explained(self):
        self.download.write_bytes(b'\n<!DOCTYPE html><html><body>Sign in</body></html>')
        with self.assertRaisesRegex(ValueError, 'web page'):
            cloud.collect(self.download, self.out, ACCEPTED)

    @unittest.skipUnless(shutil.which('7zz'), '7zz (brew install sevenzip) unpacks archives')
    def test_zip_with_nested_installer_and_patch(self):
        with zipfile.ZipFile(self.download, 'w') as archive:
            archive.writestr('Halo/Setup/HaloCESetup.exe', INSTALLER)
            archive.writestr('Halo/haloce-patch-1.0.10.exe', PATCH)
            archive.writestr('Halo/readme.txt', 'ignored')
        cloud.collect(self.download, self.out, ACCEPTED)
        self.assertEqual((self.out / 'HaloCESetup.exe').read_bytes(), INSTALLER)
        self.assertEqual((self.out / 'haloce-patch-1.0.10.exe').read_bytes(), PATCH)
        self.assertFalse((self.out / 'readme.txt').exists())


class FetchTests(unittest.TestCase):
    def test_fetch_writes_private_key_file_and_masks_derived_values(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / 'inputs'

            def fake_curl(args, **kwargs):
                pathlib.Path(args[args.index('-o') + 1]).write_bytes(INSTALLER)
                return subprocess.CompletedProcess(args, 0, '', '')

            with mock.patch.object(cloud, 'installer_sha256', return_value=ACCEPTED), \
                    mock.patch.object(cloud.subprocess, 'run', side_effect=fake_curl), \
                    mock.patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), \
                    mock.patch('sys.stdout') as stdout:
                cloud.fetch(GOOD, out)
            printed = ''.join(call.args[0] for call in stdout.write.call_args_list)
            self.assertIn('::add-mask::ABCDE-FGHIJ-KLMNO-PQRST-UVWXY', printed)
            self.assertIn('::add-mask::ABCDEFGHIJKLMNOPQRSTUVWXY', printed)
            key = out / 'product-key.txt'
            self.assertEqual(key.read_text(), 'ABCDE-FGHIJ-KLMNO-PQRST-UVWXY\n')
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual((out / 'HaloCESetup.exe').read_bytes(), INSTALLER)
            self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ['inputs'])

    def test_accepted_installer_is_padmints(self):
        self.assertEqual(cloud.installer_sha256(),
                         {'150e430dc54ffb265cbe96605ef8909c9ba0065fa11bdbf170bfd88391cf98ba'})


if __name__ == '__main__':
    unittest.main()
