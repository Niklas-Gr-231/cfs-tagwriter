# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Public packaging and approval-triggered version guards, without network writes."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_distribution import build,release_notes,release_versions


class Distribution(unittest.TestCase):
    def test_tag_matches_app_and_never_accepts_shell_text(self):
        version=release_versions()['APP_VERSION']
        self.assertEqual(release_versions('v'+version)['APP_VERSION'],version)
        for tag in ('v0.0.0','main','v'+version+';echo example','v'+version+'-test'):
            with self.assertRaises(ValueError):release_versions(tag)

    def test_missing_change_description_is_rejected(self):
        with self.assertRaises(ValueError):release_notes('0.0.0')
        notes=release_notes(release_versions()['APP_VERSION'])
        self.assertIn('ältere',notes.casefold())
        self.assertNotIn('**3.6.0 ·',notes)

    def test_nonempty_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            original=Path(directory)/'existing.txt';original.write_text('keep')
            with self.assertRaises(ValueError):build(directory)
            self.assertEqual(original.read_text(),'keep')

    def test_source_directory_is_never_a_distribution_target(self):
        with self.assertRaises(ValueError):build(ROOT)
        with self.assertRaises(ValueError):build(ROOT/'dist')

    def test_version_mismatch_stops_before_any_build(self):
        with tempfile.TemporaryDirectory() as directory,patch('build_distribution.subprocess.run') as process:
            with self.assertRaises(ValueError):build(Path(directory)/'new','v0.0.0')
            process.assert_not_called()
            self.assertFalse(Path(directory,'new').exists())

    def test_public_assets_and_checksums_are_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            out=build(Path(directory)/'release')
            version=release_versions()['APP_VERSION']
            with zipfile.ZipFile(out/('CFS_Tagwriter_'+version+'_Weitergabe.zip')) as archive:
                self.assertIsNone(archive.testzip())
                for name in ('Start-Tagwriter.bat','Start-Tagwriter.command','Start-Tagwriter.sh','LICENSE',
                             'THIRD_PARTY_NOTICES.md','Beispielplatte/Filament-Swatch-Beispielplatte.3mf'):
                    self.assertIn(name,archive.namelist())
                self.assertIn('CFS_Tagwriter_'+version+'.py',archive.namelist())
            manifest=json.loads((out/('CFS_Tagwriter_'+version+'_Pruefsummen.json')).read_text())
            self.assertFalse(manifest['private_data_included'])
            for name,digest in manifest['sha256'].items():self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
