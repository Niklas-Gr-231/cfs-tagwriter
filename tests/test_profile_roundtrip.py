# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Entirely synthetic profiles exercise transfer and native database safety."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from cfs_local_profiles import local_bundle
from cfs_transfer_core import plan_import, validate_bundle


def generic_record():
    return {
        'printerIntName': 'F012', 'nozzleDiameter': ['0.4'],
        'base': {'id': '00003', 'name': 'Generic PETG', 'brand': 'Generic',
                 'meterialType': 'PETG', 'diameter': '1.75', 'density': '1.26',
                 'colors': ['#FFFFFF']},
        'kvParam': {'filament_type': 'PETG', 'nozzle_temperature_range_low': '220',
                    'nozzle_temperature_range_high': '260', 'nozzle_temperature': '240',
                    'nozzle_temperature_initial_layer': '240', 'filament_flow_ratio': '1',
                    'pressure_advance': '0.03', 'filament_max_volumetric_speed': '12'},
    }


class ProfileRoundtrip(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'Synthetic PETG Hi.json'
        self.database = {'result': {'count': 1, 'list': [generic_record()]}}
        raw = dict(generic_record()['kvParam'], name='Synthetic PETG Hi',
                   filament_settings_id=['Synthetic PETG Hi'],
                   compatible_printers=['Creality K2 Pro 0.4 nozzle'],
                   default_filament_colour=['#123456'], filament_vendor=['Example Hi'],
                   filament_density=['1.26'], filament_diameter=['1.75'],
                   filament_soluble=['0'], filament_is_support=['0'],
                   filament_flow_ratio=['0.94321'], pressure_advance=['0.052'])
        raw['from'] = 'User'
        self.path.write_text(json.dumps(raw))
        self.bundle = local_bundle([self.path], self.database, 'F012', '0.4', {})
        self.manifest = {'schema_version': 2, 'account_id': None, 'printer_int_name': 'F012',
                         'nozzle_diameter': '0.4', 'profiles': [], 'imported_profiles': []}

    def test_exact_calibrations_survive_bundle_creation(self):
        validated = validate_bundle(self.bundle)
        params = validated['profiles'][0]['record']['kvParam']
        self.assertEqual(params['filament_flow_ratio'], '0.94321')
        self.assertEqual(params['pressure_advance'], '0.052')
        self.assertEqual(params['filament_max_volumetric_speed'], '12')

    def test_foreign_code_collision_allocates_new_code_without_changing_source(self):
        foreign = generic_record()
        foreign['base']['id'] = self.bundle['profiles'][0]['material_id']
        self.database['result']['list'].append(foreign)
        self.database['result']['count'] = 2
        before = deepcopy(self.database)
        original = self.path.read_bytes()
        target, plan = plan_import(self.bundle, self.database, self.manifest, {}, {'profiles': []})
        self.assertNotEqual(plan[0]['material_id'], foreign['base']['id'])
        self.assertEqual(self.database, before)
        self.assertEqual(self.path.read_bytes(), original)
        repeated, again = plan_import(self.bundle, self.database, target, {}, {'profiles': []})
        self.assertEqual(again[0]['material_id'], plan[0]['material_id'])
        self.assertEqual(len(repeated['imported_profiles']), 1)

    def test_different_printer_model_is_rejected(self):
        self.manifest['printer_int_name'] = 'F018'
        with self.assertRaises(ValueError):
            plan_import(self.bundle, self.database, self.manifest, {}, {'profiles': []})


if __name__ == '__main__':
    unittest.main()
