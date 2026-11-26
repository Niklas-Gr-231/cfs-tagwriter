# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/creality-cfs-writer'))
from cfs_codec import load_materials


class SlicerImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def write(self, name, obj):
        p = self.root / name
        p.write_text(json.dumps(obj))
        return p
    def profile(self, **extra):
        return {'from':'User','name':'HISPD PETG Sunlu Rot 0.4','base_id':'GFSA04',
                'filament_id':'00003','filament_vendor':['Sunlu'],'filament_type':['PETG'],
                'default_filament_colour':['#BC2726'],'nozzle_temperature':['245'],
                'filament_flow_ratio':['0.9375'],'pressure_advance':['0.052'], **extra}
    def test_profile_without_explicit_code_loads_without_fabricated_mapping(self):
        item, = load_materials(self.write('rot.json',self.profile()))
        self.assertEqual(item['id'],'')
        self.assertEqual(item['mapping_status'],'missing')
        self.assertEqual(item['color'],'#BC2726')
        self.assertEqual(item['profile_metadata'],{'nozzle_temperature':'245','flow_ratio':'0.9375','pressure_advance':'0.052'})
    def test_explicit_notes_code_is_declared_not_verified(self):
        p=self.write('rot.json',self.profile(filament_notes=[json.dumps({'id':'99001'})]))
        item,=load_materials(p)
        self.assertEqual((item['id'],item['mapping_status']),('99001','declared'))
    def test_freeform_notes_do_not_break_import(self):
        item,=load_materials(self.write('rot.json',self.profile(filament_notes=['Druckt bei 245 Grad.'])))
        self.assertEqual(item['id'],'')
    def test_invalid_notes_code_has_actionable_error(self):
        p=self.write('rot.json',self.profile(filament_notes=json.dumps({'id':'GFSA04'})))
        with self.assertRaisesRegex(ValueError,'5'):load_materials(p)
    def test_list_keeps_distinct_profiles_without_codes(self):
        p=self.write('profiles.json',[self.profile(),self.profile(name='Sunlu Blau',default_filament_colour=['#123456'])])
        result=load_materials(p)
        self.assertEqual(len(result),2)
        self.assertEqual({x['name'] for x in result},{'HISPD PETG Sunlu Rot 0.4','Sunlu Blau'})
    def test_inherited_values_do_not_inherit_registration(self):
        self.write('parent.json',self.profile(name='parent',filament_notes=[json.dumps({'id':'99007'})]))
        p=self.write('child.json',{'name':'child','inherits':'parent','from':'User','base_id':'GFSA04'})
        item,=load_materials(p)
        self.assertEqual(item['type'],'PETG')
        self.assertEqual(item['profile_metadata']['nozzle_temperature'],'245')
        self.assertEqual(item['id'],'')
    def test_cycle_is_rejected(self):
        self.write('a.json',{'from':'User','name':'a','inherits':'b'})
        self.write('b.json',{'from':'User','name':'b','inherits':'a'})
        with self.assertRaisesRegex(ValueError,'Vererbung'):load_materials(self.root/'a.json')


if __name__=='__main__':unittest.main(verbosity=2)
