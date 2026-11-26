# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from pathlib import Path
import tempfile
import unittest

from cfs_anycubic import AceDevice, AceSpec
from cfs_anycubic_feeders import FEEDERS, PRINTERS, get_feeder, validate_selection, require_write_target
from cfs_connections import ConnectionStore
from test_connections_identity import MemoryKeyring


class FeederSelection(unittest.TestCase):
    def test_all_researched_families_and_official_ace2_variants_are_separate(self):
        self.assertEqual(set(FEEDERS), {'ace_pro', 'ace2_pro', 'kobra_x_integrated', 'other'})
        self.assertIn('Kobra 4', PRINTERS)
        self.assertIn('Kobra 3 Max V2', PRINTERS)
        for model in ('Kobra 3', 'Kobra 3 V2', 'Kobra 3 Max', 'Kobra 3 Max V2', 'Kobra 4'):
            validate_selection('ace2_pro', 'k3_k4', model)
        for model in ('Kobra S1', 'Kobra S1 Max', 'Kobra X'):
            validate_selection('ace2_pro', 's1_x', model)

    def test_wrong_printer_or_variant_is_not_silently_reinterpreted(self):
        for args in (('ace_pro', 'standard', 'Kobra X'), ('ace2_pro', 'k3_k4', 'Kobra S1'),
                     ('kobra_x_integrated', 'integrated', 'Kobra S1'), ('ace_pro', 'k3_max_upgrade', 'Kobra S1'),
                     ('', '', 'Kobra S1'), ('ace2_pro', 'invented', 'Kobra S1')):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_selection(*args)

    def test_integrated_and_unknown_readers_need_explicit_format_test(self):
        for feeder, variant, model in (('kobra_x_integrated', 'integrated', 'Kobra X'), ('other', 'unknown', 'Kobra S1')):
            with self.subTest(feeder=feeder):
                with self.assertRaises(ValueError): require_write_target(feeder, variant, model)
                require_write_target(feeder, variant, model, test_unknown_format=True)
        require_write_target('ace2_pro', 's1_x', 'Kobra S1')

    def test_unapproved_target_fails_before_any_usb_or_backup_operation(self):
        class Transport:
            def __getattr__(self, name): raise AssertionError('Transport must not be accessed: '+name)
        spec = AceSpec('EXAMPLE-01', 'PLA', '#123456', 817, 270, 200, 220, 50, 60)
        with tempfile.TemporaryDirectory() as directory:
            target = {'feeder_id': 'kobra_x_integrated', 'variant': 'integrated', 'model': 'Kobra X', 'test_unknown_format': False}
            with self.assertRaises(ValueError):
                AceDevice(Transport(), target=target).write_tag('04112233445566', spec, Path(directory)/'backup')
            self.assertFalse((Path(directory)/'backup').exists())

    def test_target_catalog_cannot_be_mutated_by_a_ui_consumer(self):
        entry = get_feeder('ace2_pro')
        entry['variants'].clear()
        self.assertTrue(get_feeder('ace2_pro')['variants'])


class FeederBookmarks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backend = MemoryKeyring()
        self.store = ConnectionStore(self.directory.name, backend=self.backend)

    def test_selected_feeder_survives_rename_and_no_test_consent_is_stored(self):
        self.store.remember('ACE', '10.0.0.3', model='Anycubic Kobra S1', feeder_id='ace2_pro', feeder_variant='s1_x')
        self.store.remember('Renamed', '10.0.0.3')
        saved = self.store.choices()[0]
        self.assertEqual(saved['feeder_id'], 'ace2_pro')
        self.assertEqual(saved['feeder_variant'], 's1_x')
        self.assertNotIn('test_unknown_format', saved)

    def test_legacy_bookmark_has_no_invented_feeder(self):
        self.store.remember('Legacy', '10.0.0.3', model='Anycubic Kobra S1')
        self.assertNotIn('feeder_id', self.store.choices()[0])

    def test_bad_variant_cannot_change_bookmark_or_keyring(self):
        self.store.remember('ACE', '10.0.0.3', model='Anycubic Kobra S1')
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.remember('Wrong', '10.0.0.3', 'secret', True, model='Anycubic Kobra S1', feeder_id='ace2_pro', feeder_variant='k3_k4')
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse(self.backend.secrets)
