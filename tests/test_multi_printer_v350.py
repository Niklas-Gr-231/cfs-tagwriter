# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cfs_anycubic import AceSpec, AceDevice, encode, decode
from cfs_compatibility import model_info
from cfs_device import BridgeError
from cfs_fleet import FleetStore, require_matching_models, sync_profiles
from cfs_tag_feedback import TagFeedback
from test_profile_roundtrip import generic_record


class ExperimentalAce(unittest.TestCase):
    def setUp(self):
        self.spec = AceSpec('TEST-PETG-01', 'PETG', '#123456', 817, 270, 230, 250, 65, 75, '123456')

    def test_repeated_clock_tick_keeps_both_ace_backups(self):
        from datetime import datetime
        bridge=self.fake_bridge()
        with tempfile.TemporaryDirectory() as directory,patch('cfs_anycubic.datetime') as clock:
            clock.now.return_value=datetime(2026,1,1,12)
            first=AceDevice(bridge).write_tag(bridge.uid,self.spec,directory)
            saved=Path(first['backup']).read_bytes()
            second=AceDevice(bridge).write_tag(bridge.uid,replace(self.spec,color='#AABBCC'),directory)
            self.assertNotEqual(first['backup'],second['backup'])
            self.assertEqual(Path(first['backup']).read_bytes(),saved)
            self.assertEqual(len(list(Path(directory).glob('*.json'))),2)
            self.assertTrue(second['verified'])

    def test_native_fields_roundtrip_but_roll_number_is_not_falsely_claimed_as_native(self):
        raw = encode(self.spec)
        self.assertEqual(len(raw), 144)
        self.assertEqual(raw[24:26], b'AC')
        self.assertEqual(raw[64:68], b'\xff\x56\x34\x12')
        self.assertEqual(decode(raw), replace(self.spec, serial=''))

    def test_bad_values_are_rejected_before_device_io(self):
        for changes in ({'sku': ''}, {'sku': 'X'*21}, {'color': '#GG0000'}, {'weight_g': -1},
                        {'nozzle_low': 260}, {'length_m': 100000}, {'bed_low': 200}, {'type': 'PÉTG'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                encode(replace(self.spec, **changes))

    def test_old_bridge_gets_actionable_update_message_without_tag_commands(self):
        class Old:
            _lock = threading.RLock()
            def hello(self): return {'protocol': 1, 'firmware_version': '1.0.0'}
            def _command(self, *_): raise AssertionError('No NTAG command on old firmware')
        with self.assertRaisesRegex(BridgeError, '1.1.0'):
            AceDevice(Old()).read_tag()

    def fake_bridge(self):
        class Fake:
            _lock = threading.RLock()
            def __init__(self):
                self.uid = '04112233445566'
                self.memory = bytearray(180)
                self.memory[12:16] = bytes.fromhex('E1101200')
                self.memory[167] = 0xff
                self.writes = []
                self.corrupt = False
            def hello(self): return {'capabilities': ['cfs_sector1', 'ntag213']}
            def _command(self, command, *args):
                if command == 'NTSCAN': return {'uid': self.uid, 'type': 'NTAG213'}
                uid, page = args[:2]
                assert uid == self.uid
                if command == 'NTWRITE':
                    assert 4 <= page <= 39
                    self.writes.append(page)
                    self.memory[page*4:page*4+4] = bytes.fromhex(args[2])
                    return {'uid': uid, 'page': page, 'verified': True}
                raw = bytes(self.memory[page*4:page*4+16])
                if self.corrupt and self.writes and page == 4:
                    raw = bytes([raw[0]^1])+raw[1:]
                return {'uid': uid, 'page': page, 'data': raw.hex()}
        return Fake()

    def test_backup_precedes_any_write_and_only_user_pages_change(self):
        bridge = self.fake_bridge()
        before = bytes(bridge.memory)
        with tempfile.TemporaryDirectory() as directory:
            report = AceDevice(bridge).write_tag(bridge.uid, self.spec, directory)
            self.assertTrue(report['verified'])
            backup = json.loads(Path(report['backup']).read_text())
            self.assertEqual(backup['user_pages_4_39'], before[16:160].hex().upper())
        self.assertEqual(bridge.memory[:16], before[:16])
        self.assertEqual(bridge.memory[160:], before[160:])
        self.assertEqual(bytes(bridge.memory[16:160]), encode(self.spec))

    def test_locked_or_password_protected_tag_never_receives_write(self):
        for index in (10, 11, 160, 161, 162, 167):
            bridge = self.fake_bridge()
            bridge.memory[index] = 1
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(BridgeError):
                AceDevice(bridge).write_tag(bridge.uid, self.spec, directory)
            self.assertEqual(bridge.writes, [])

    def test_wrong_uid_or_failed_backup_never_writes(self):
        bridge = self.fake_bridge()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BridgeError):
                AceDevice(bridge).write_tag('04999999999999', self.spec, directory)
            with patch.object(Path, 'open', side_effect=PermissionError), self.assertRaises(PermissionError):
                AceDevice(bridge).write_tag(bridge.uid, self.spec, directory)
        self.assertFalse(bridge.writes)

    def test_full_readback_failure_is_not_success(self):
        bridge = self.fake_bridge()
        bridge.corrupt = True
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(BridgeError) as error:
            AceDevice(bridge).write_tag(bridge.uid, self.spec, directory)
        self.assertEqual(error.exception.code, 'VERIFY_FAILED')


class MultiplePrinters(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = FleetStore(self.directory.name)

    def test_sharing_is_off_by_default_and_opt_in_is_per_printer(self):
        self.assertFalse(self.store.remember('10.0.0.1', 'cfs', '11223344', '123456'))
        self.assertFalse(self.store.path.exists())
        self.store.set_policy('10.0.0.2', 'rolls')
        self.assertFalse(self.store.remember('10.0.0.1', 'cfs', '11223344', '123456'))
        self.assertTrue(self.store.remember('10.0.0.2', 'cfs', '11223344', '123456', '99021', 817))
        self.assertEqual(self.store.lookup('cfs', '11223344'), '123456')

    def test_both_sides_can_share_one_roll_without_combining_different_rolls_by_name(self):
        self.store.set_policy('10.0.0.1', 'rolls')
        for uid in ('11223344', 'AABBCCDD'):
            self.store.remember('10.0.0.1', 'cfs', uid, '123456', '99021', 817)
        self.store.remember('10.0.0.1', 'cfs', '22334455', '654321', '99021', 800)
        self.assertEqual(len(self.store.load()['rolls']), 2)
        self.assertEqual(len(self.store.load()['rolls']['123456']['tags']), 2)

    def test_confirmed_code_mapping_does_not_replace_target_calibration_or_amount(self):
        self.store.set_policy('10.0.0.1', 'rolls')
        self.store.set_policy('10.0.0.2', 'profiles')
        self.store.remember('10.0.0.1', 'cfs', '11223344', '123456', '99021', 817)
        rows = [{'source_code': '99021', 'material_id': '99022'}]
        self.assertEqual(self.store.link_profile_codes('10.0.0.1', '10.0.0.2', rows), 1)
        self.assertEqual(self.store.material_for_roll('10.0.0.2', '123456'), '99022')
        self.assertIsNone(self.store.load()['rolls']['123456']['printers']['10.0.0.2']['observed_weight_g'])
        self.store.remember('10.0.0.2', 'cfs', 'AABBCCDD', '123456', '99023', 800)
        self.assertEqual(self.store.link_profile_codes('10.0.0.1', '10.0.0.2', rows), 0)
        self.assertEqual(self.store.material_for_roll('10.0.0.2', '123456'), '99023')
        self.assertEqual(self.store.load()['rolls']['123456']['printers']['10.0.0.1']['observed_weight_g'], 817)

    def test_conflicting_inventory_import_is_atomic_and_does_not_enable_sync(self):
        self.store.set_policy('10.0.0.1', 'rolls')
        self.store.remember('10.0.0.1', 'cfs', '11223344', '123456')
        before = self.store.path.read_bytes()
        incoming = self.store.load()
        incoming['rolls']['654321'] = incoming['rolls'].pop('123456')
        incoming['policies']['10.0.0.3'] = 'profiles'
        with self.assertRaises(ValueError): self.store.import_inventory(incoming)
        self.assertEqual(self.store.path.read_bytes(), before)
        incoming['rolls']['654321']['tags'] = ['cfs:22334455']
        self.store.import_inventory(incoming)
        self.assertEqual(self.store.policy('10.0.0.3'), 'off')

    def test_profile_sync_cannot_cross_models_brands_or_nozzle_diameters(self):
        source = {'printer_int_name': 'F012', 'nozzle_diameter': '0.4'}
        require_matching_models(source, deepcopy(source))
        for model, nozzle in (('F018', '0.4'), ('Anycubic Kobra S1', '0.4'), ('F012', '0.6'), ('', '0.4')):
            with self.assertRaises(ValueError):
                require_matching_models(source, {'printer_int_name': model, 'nozzle_diameter': nozzle})

    def test_only_k2_pro_is_marked_as_device_tested(self):
        self.assertFalse(model_info('F012')['experimental'])
        for model in ('F008', 'F018', 'F001', 'K1 Max 2025', 'Kobra S1', 'F099'):
            self.assertTrue(model_info(model)['experimental'])
        self.assertFalse(model_info('Anycubic Kobra S1')['service_available'])

    def test_preflight_chooses_the_native_model_and_rejects_other_manufacturers(self):
        from cfs_printer_setup import preflight
        class Remote:
            def read_status(self):
                return {'webhooks': {'state': 'ready'}, 'print_stats': {'state': 'standby'},
                        'configfile': {'settings': {'extruder': {'nozzle_diameter': 0.4}}}}
            def read_database(self): return b'', {'result': {'count': 1, 'list': [self.record]}}
            def run(self, command): return b'procd'
        remote = Remote()
        for model in ('F012', 'F008', 'F018', 'F001'):
            remote.record = dict(generic_record(), printerIntName=model)
            result = preflight(remote)
            self.assertEqual(result['manifest']['printer_int_name'], model)
            self.assertEqual(result['compatibility']['experimental'], model != 'F012')
        remote.record = dict(generic_record(), printerIntName='Anycubic Kobra S1')
        with self.assertRaises(ValueError): preflight(remote)

    def test_target_view_never_changes_active_printer_and_preserves_source_values(self):
        record = generic_record()
        record['base'].update(id='99021', name='Example Hi', brand='Example Hi')
        record['kvParam']['filament_flow_ratio'] = '0.94321'
        profile = {'material_id': '99021', 'profile_setting_id': 'a'*24, 'name': 'Example Hi', 'brand': 'Example Hi',
                   'color': '#FFFFFF', 'source_file': 'test://profile', 'record': record}
        snapshot = {'schema_version': 1, 'account_id': '123', 'printer_int_name': 'F012', 'nozzle_diameter': '0.4', 'profiles': {'99021': profile}}
        class Registry:
            path = Path(self.directory.name)/'registry.json'
            printer = {'ip': '10.0.0.1', 'name': 'Source', 'printer_int_name': 'F012'}
            def _load(self): return {'profiles': [], 'printer': deepcopy(self.printer)}
            def cloud_catalog(self, **kwargs): return deepcopy(snapshot)
            def _cloud_snapshot(self, data, **kwargs): return deepcopy(snapshot)
        registry = Registry()
        before = deepcopy(registry.printer)
        self.store.set_policy('10.0.0.2', 'profiles')
        def transfer(target, bundle, password, preview):
            self.assertEqual(target.printer['ip'], '10.0.0.2')
            self.assertEqual(bundle['profiles'][0]['record']['kvParam']['filament_flow_ratio'], '0.94321')
            target.set_profile_activity([], True)
            return {'plan': [{'retag_required': False}]}
        result = sync_profiles(registry, self.store, {'ip': '10.0.0.2', 'name': 'Target'}, ['99021'], '', transfer_function=transfer)
        self.assertEqual(registry.printer, before)
        self.assertEqual(result['code_changes'], [])


class Feedback(unittest.TestCase):
    def test_retry_buttons_and_verified_success_are_distinct(self):
        feedback = TagFeedback()
        for operation, caption in (('read', 'Erneut lesen'), ('write', 'Erneut schreiben')):
            feedback.begin(operation)
            feedback.fail('Testfehler')
            self.assertEqual(feedback.caption(operation), caption)
        feedback.begin('write')
        with self.assertRaises(ValueError): feedback.success('11223344')
        feedback.success('11223344', verified=True)
        self.assertEqual(feedback.phase, 'success')
        self.assertIn('Rücklesen', feedback.message)
        feedback.edited()
        self.assertEqual(feedback.phase, 'idle')
        self.assertIn('noch nicht', feedback.message)
