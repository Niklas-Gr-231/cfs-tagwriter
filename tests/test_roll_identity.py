# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cfs_roll_identity import RollIdentities,valid_serial
from cfs_pairing import TwoTagSession
from cfs_codec import TagSpec,new_serial
from cfs_tag_feedback import TagFeedback,filament_details


class LocalRollIdentity(unittest.TestCase):
    def test_empty_tags_keep_reserved_numbers_across_restarts_without_sharing(self):
        with tempfile.TemporaryDirectory() as directory:
            first=RollIdentities(directory,factory=lambda:'123456')
            self.assertEqual(first.resolve('cfs','01020304'),('123456',True))
            second=RollIdentities(directory,factory=lambda:(_ for _ in ()).throw(AssertionError('must reuse')))
            self.assertEqual(second.resolve('cfs','01020304',incoming='000000'),('123456',False))
            self.assertFalse((Path(directory)/'fleet.json').exists())

    def test_demo_identity_never_creates_or_reads_real_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            store=RollIdentities(directory,factory=lambda:'123456',memory=True)
            self.assertEqual(store.resolve('cfs','01020304'),('123456',True))
            self.assertEqual(store.resolve('cfs','01020304'),('123456',False))
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_real_tag_serial_wins_over_old_local_record_and_manual_retag_updates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store=RollIdentities(directory,factory=lambda:'123456')
            store.resolve('cfs','01020304')
            self.assertEqual(store.resolve('cfs','01020304',incoming='003456'),('003456',False))
            store.remember('cfs','01020304','654321')
            self.assertEqual(store.resolve('cfs','01020304'),('654321',False))

    def test_new_numbers_avoid_zero_and_existing_rolls_but_two_tags_can_share(self):
        with tempfile.TemporaryDirectory() as directory:
            numbers=iter(('000000','123456','123456','654321'))
            store=RollIdentities(directory,factory=lambda:next(numbers))
            self.assertEqual(store.resolve('cfs','01020304')[0],'123456')
            self.assertEqual(store.resolve('cfs','AABBCCDD')[0],'654321')
            store.remember('cfs','AABBCCDD','123456')
            self.assertEqual(store.resolve('cfs','AABBCCDD')[0],'123456')
        with patch('cfs_codec.secrets.randbelow',return_value=0):self.assertEqual(new_serial(),'000001')

    def test_ace_uses_local_or_legacy_identity_and_never_claims_native_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            store=RollIdentities(directory)
            self.assertEqual(store.resolve('ace','04112233445566',legacy='654321'),('654321',False))
            self.assertEqual(RollIdentities(directory).resolve('ace','04112233445566'),('654321',False))

    def test_new_id_also_avoids_previously_shared_rolls(self):
        from cfs_fleet import FleetStore
        with tempfile.TemporaryDirectory() as directory:
            fleet=FleetStore(directory);fleet.set_policy('10.0.0.1','rolls')
            fleet.remember('10.0.0.1','cfs','01020304','123456')
            numbers=iter(('123456','654321'))
            store=RollIdentities(directory,factory=lambda:next(numbers))
            self.assertEqual(store.resolve('cfs','AABBCCDD')[0],'654321')

    def test_invalid_state_and_uid_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            store=RollIdentities(directory);store.path.parent.mkdir()
            store.path.write_text('{broken');original=store.path.read_bytes()
            with self.assertRaises(ValueError):store.resolve('cfs','01020304')
            self.assertEqual(store.path.read_bytes(),original)
            with self.assertRaises(ValueError):store.resolve('cfs','not-a-uid')
        for value in ('',None,'000000','123','abc123'):self.assertIsNone(valid_serial(value))


class PairStatus(unittest.TestCase):
    def test_read_write_stages_stay_separate_and_first_success_survives_second_failure(self):
        session=TwoTagSession(clock=lambda:'12:34:56');session.enable(True)
        spec=TagSpec('00003','#112233',825,'123456','PETG blue')
        details=filament_details(spec,{'type':'PETG'})
        session.read('01020304');session.confirmed('01020304',spec,details)
        first=session.status_rows()[0].copy()
        session.read('AABBCCDD');session.failed('AABBCCDD','test failure')
        self.assertEqual(session.status_rows()[0],first)
        second=session.status_rows()[1]
        self.assertTrue(second['read']);self.assertFalse(second['written']);self.assertTrue(second['error'])
        session.confirmed('AABBCCDD',spec,details)
        self.assertTrue(all(row['read'] and row['written'] and not row['error'] for row in session.status_rows()))
        self.assertIn('PETG',session.status_rows()[0]['text']);self.assertIn('825 g',session.status_rows()[1]['text'])
        session.reset();self.assertFalse(any(row['read'] or row['written'] for row in session.status_rows()))

    def test_two_reads_keep_distinct_slots_and_third_tag_is_rejected_before_write(self):
        session=TwoTagSession();session.enable(True)
        session.read('01020304');session.read('AABBCCDD');session.read('11223344')
        self.assertEqual([row['uid'] for row in session.status_rows()],['01020304','AABBCCDD'])
        with self.assertRaises(ValueError):session.check_write('11223344',TagSpec('00003','#112233',825,'123456'))
        session.read('01020304');session.confirmed('AABBCCDD',TagSpec('00003','#112233',825,'123456'))
        self.assertIn('Tag 1 ist bereit',session.hint())

    def test_green_result_keeps_a_snapshot_of_verified_filament_values(self):
        spec=TagSpec('00003','#AABBCC',825,'123456','Sunlu Himmel Blau')
        feedback=TagFeedback();feedback.begin('write')
        with self.assertRaises(ValueError):feedback.success('01020304',details=filament_details(spec,{'type':'PETG'}))
        feedback.success('01020304',verified=True,details=filament_details(spec,{'type':['PETG']}))
        for text in ('PETG','Sunlu Himmel Blau','#AABBCC','825 g','123456'):self.assertIn(text,feedback.message)


class WriterRollFlow(unittest.TestCase):
    def harness(self):
        from test_writer_registry import WriterRegistryTests
        harness=WriterRegistryTests('runTest');harness.setUp();self.addCleanup(harness.tearDown)
        return harness

    def test_read_and_rewrite_keep_a_real_roll_serial(self):
        harness=self.harness();app=harness.app
        app.bridge.tag={'uid':'11223344','formatted':True,'profile':{'material_id':'99006','serial':'246810','color':'#112233','weight_g':825}}
        app.read_tag();self.assertEqual(app.serial_var.get(),'246810')
        app.show_material(harness.material);app.write_tag()
        self.assertFalse(harness.errors)
        self.assertEqual(app.bridge.writes[-1][1].serial,'246810')

    def test_blank_tag_auto_number_repeats_and_two_tags_share_it(self):
        harness=self.harness();app=harness.app;app.update_controls=lambda:None;app.pair_session=TwoTagSession()
        with patch('cfs_roll_identity.new_serial',side_effect=['001111','001112']):
            app.read_tag();first=app.serial_var.get();self.assertEqual(first,'001111')
            app.read_tag();self.assertEqual(app.serial_var.get(),first)
            app.pair_session.enable(True);app.read_tag();app.write_tag()
            app.bridge.tag={'uid':'AABBCCDD','formatted':False};app.read_tag()
            self.assertEqual(app.serial_var.get(),first);app.write_tag()
        self.assertFalse(harness.errors)
        self.assertEqual([spec.serial for uid,spec in app.bridge.writes],['001111','001111'])
        self.assertEqual(app.roll_identities().resolve('cfs','AABBCCDD')[0],first)

    def test_existing_native_serial_is_read_even_if_optional_local_index_is_broken(self):
        harness=self.harness();app=harness.app
        path=app.roll_identities().path;path.parent.mkdir();path.write_text('{broken')
        app.bridge.tag={'uid':'11223344','formatted':True,'profile':{'material_id':'99006','serial':'246810','color':'#112233','weight_g':825}}
        app.read_tag()
        self.assertFalse(harness.errors);self.assertEqual(app.serial_var.get(),'246810')
        self.assertEqual(path.read_text(),'{broken')

    def test_cache_failure_after_verification_is_not_reported_as_a_failed_write(self):
        from unittest.mock import Mock
        from cfs_tag_feedback import TagFeedback
        harness=self.harness();app=harness.app;app.tag_feedback=TagFeedback()
        store=Mock();store.remember.side_effect=OSError('test read-only state')
        with patch.object(app,'roll_identities',return_value=store):app.write_tag()
        self.assertFalse(harness.errors)
        self.assertEqual(app.tag_feedback.phase,'success')
        self.assertIn('Rücklesen',app.tag_feedback.message)
