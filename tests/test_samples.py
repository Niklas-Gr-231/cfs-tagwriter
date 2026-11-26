# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bundled geometry, attribution, offline export and failure preservation."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as E
import zipfile
import cfs_samples as samples

NS={'c':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}


class SamplePlate(unittest.TestCase):
    def test_four_distinct_meshes_and_original_layout(self):
        with zipfile.ZipFile(io.BytesIO(samples.sample_bytes())) as archive:
            self.assertIsNone(archive.testzip())
            root=E.fromstring(archive.read('3D/3dmodel.model'))
        self.assertEqual(root.get('unit'),'millimeter')
        self.assertLessEqual({m.get('name') for m in root.findall('c:metadata',NS)},{'Title','Designer','Description','Copyright','LicenseTerms','Application','CreationDate','ModificationDate','Rating'})
        objects=root.findall('c:resources/c:object',NS)
        items=root.findall('c:build/c:item',NS)
        self.assertEqual(len(objects),4);self.assertEqual(len(items),4)
        self.assertEqual({o.get('id') for o in objects},{i.get('objectid') for i in items})
        expected=[(101.042426,108.084847,1),(101.042416,150.000005,1),(101.042416,191.915163,1),(198.957584,108.084837,1)]
        for item,position in zip(items,expected):self.assertEqual(tuple(map(float,item.get('transform').split()[9:])),position)
        first=None
        for obj in objects:
            mesh=obj.find('c:mesh',NS)
            if first is None:first=E.tostring(mesh)
            self.assertEqual(E.tostring(mesh),first)
            vertices=mesh.find('c:vertices',NS);triangles=mesh.find('c:triangles',NS)
            self.assertGreater(len(vertices),100);self.assertGreater(len(triangles),100)
            for triangle in triangles:
                self.assertTrue(all(0<=int(triangle.get(k))<len(vertices) for k in ('v1','v2','v3')))
            self.assertAlmostEqual(max(float(p.get('x')) for p in vertices)-min(float(p.get('x')) for p in vertices),92)
            self.assertAlmostEqual(max(float(p.get('y')) for p in vertices)-min(float(p.get('y')) for p in vertices),36)

    def test_attribution_and_no_private_slicer_settings_or_external_assets(self):
        with zipfile.ZipFile(io.BytesIO(samples.sample_bytes())) as archive:
            self.assertEqual(set(archive.namelist()),{'[Content_Types].xml','_rels/.rels','3D/3dmodel.model','Metadata/ATTRIBUTION.txt'})
            for name in archive.namelist():
                text=archive.read(name).decode()
                for forbidden in ('source_file','filament_settings_id','printer_select_mac','project_settings.config','/home/','/Users/'):
                    self.assertNotIn(forbidden,text)
            notice=archive.read('Metadata/ATTRIBUTION.txt').decode()
            for required in ('Mr.Brom','9percent','makerworld.com','BY-NC-SA','creativecommons.org/licenses/by-nc-sa/4.0/','keine Versionsnummer'):
                self.assertIn(required,notice)
            rels=E.fromstring(archive.read('_rels/.rels'))
            self.assertEqual(len(rels),1)
            self.assertEqual(rels[0].get('Target'),'/3D/3dmodel.model')

    def test_export_works_offline_and_needs_no_printer(self):
        with tempfile.TemporaryDirectory() as directory,patch('urllib.request.urlopen',side_effect=AssertionError('Export must stay offline')):
            target=Path(directory)/'Musterplatte.3mf'
            self.assertEqual(samples.export_swatch(target),target)
            self.assertEqual(target.read_bytes(),samples.sample_bytes())
            self.assertEqual(list(Path(directory).iterdir()),[target])

    def test_invalid_extension_or_builtin_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):samples.export_swatch(Path(directory)/'wrong.gcode')
        with self.assertRaises(ValueError):samples.export_swatch(samples.ASSETS/samples.SAMPLE_NAME)

    def test_failed_export_preserves_existing_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'existing.3mf';target.write_bytes(b'existing project')
            with patch('cfs_samples.os.replace',side_effect=OSError('Disk failure')):
                with self.assertRaises(OSError):samples.export_swatch(target)
            self.assertEqual(target.read_bytes(),b'existing project')
            self.assertEqual(list(Path(directory).iterdir()),[target])

    def test_corrupt_asset_does_not_replace_existing_project(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'existing.3mf';target.write_bytes(b'keep this')
            with patch('cfs_samples.SAMPLE_SHA256','0'*64):
                with self.assertRaises(ValueError):samples.export_swatch(target)
            self.assertEqual(target.read_bytes(),b'keep this')
