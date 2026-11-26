# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from dataclasses import replace
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app/creality-cfs-writer'))
from cfs_codec import TagSpec,build_plaintext,encrypt_payload,decode_payload,weight_to_length,length_to_weight,MAX_WEIGHT_G
from cfs_pairing import TwoTagSession
from cfs_writer import parse_weight,parse_metres

BASE=TagSpec('00003','#112233',825,'123456','Testrolle')

class Amounts(unittest.TestCase):
    def test_free_grams_use_the_existing_length_field(self):
        for grams,code in ((800,'0264'),(825,'0272'),(850,'0280')):
            plain=build_plaintext(replace(BASE,weight_g=grams))
            self.assertEqual(plain[24:28].decode(),code)
            self.assertEqual(plain[34:],b'0'*14)
            decoded=decode_payload(encrypt_payload(plain))
            self.assertLessEqual(abs(decoded['weight_g']-grams),3)
    def test_all_supported_values_remain_stable_after_read_and_rewrite(self):
        for grams in range(MAX_WEIGHT_G+1):
            code=weight_to_length(grams);stored=length_to_weight(code)
            self.assertEqual(weight_to_length(stored),code)
            self.assertLessEqual(abs(stored-grams),3)
    def test_original_sizes_and_cipher_vector_stay_compatible(self):
        for grams in (250,500,600,750,1000):
            self.assertEqual(decode_payload(encrypt_payload(build_plaintext(replace(BASE,weight_g=grams))))['weight_g'],grams)
    def test_decimal_or_invalid_input_is_rejected_before_writing(self):
        for text in ('','-1','850,5','850.5','3e2','30301','NaN','１２３'):
            with self.assertRaises(ValueError):parse_weight(text)
        self.assertEqual(parse_weight(' 850 '),850)
    def test_metres_accept_only_whole_length_field_values(self):
        for text in ('','-1','280,5','280.5','10000','NaN','２８０'):
            with self.assertRaises(ValueError):parse_metres(text)
        for metres in (0,1,82,264,280,330,9999):
            self.assertEqual(parse_metres(str(metres)),metres)
    def test_every_meter_input_survives_encoding_exactly(self):
        for metres in range(10000):
            code=f'{metres:04d}'
            self.assertEqual(weight_to_length(length_to_weight(code)),code)
    def test_unknown_non_decimal_length_is_not_guessed(self):
        self.assertIsNone(length_to_weight('01AF'))

class Pairing(unittest.TestCase):
    def test_disabled_by_default(self):
        session=TwoTagSession();session.read();session.confirmed('01020304',BASE)
        self.assertFalse(session.preserve_values);self.assertEqual(session.written,[])
    def test_second_read_preserves_wishes_even_before_first_write(self):
        session=TwoTagSession();session.enable(True)
        self.assertFalse(session.preserve_values);session.read();self.assertTrue(session.preserve_values)
    def test_two_distinct_uids_share_one_payload(self):
        session=TwoTagSession();session.enable(True);session.confirmed('01020304',BASE)
        self.assertTrue(session.locked)
        session.check_write('AABBCCDD',BASE);session.confirmed('AABBCCDD',BASE)
        self.assertEqual(len(session.written),2);self.assertIn('2/2',session.hint())
    def test_same_uid_or_third_tag_cannot_count_as_a_pair(self):
        session=TwoTagSession();session.enable(True);session.confirmed('AABBCCDD',BASE)
        with self.assertRaises(ValueError):session.check_write('aabbccdd',BASE)
        session.confirmed('01020304',BASE)
        with self.assertRaises(ValueError):session.check_write('11223344',BASE)
    def test_changed_payload_requires_reset(self):
        session=TwoTagSession();session.enable(True);session.confirmed('01020304',BASE)
        for spec in (replace(BASE,weight_g=850),replace(BASE,serial='654321'),replace(BASE,color='#FFFFFF'),replace(BASE,material_id='00001')):
            with self.assertRaises(ValueError):session.check_write('AABBCCDD',spec)
        session.reset();self.assertFalse(session.locked);session.check_write('01020304',replace(BASE,weight_g=850))
    def test_local_profile_name_can_change_without_changing_tag_data(self):
        session=TwoTagSession();session.enable(True);session.confirmed('01020304',BASE)
        session.check_write('AABBCCDD',replace(BASE,name='Neuer Profilname'))
    def test_second_tag_read_and_verified_write_have_separate_timestamps(self):
        times=iter(('12:00:01','12:00:02','12:00:03','12:00:04'))
        session=TwoTagSession(clock=lambda:next(times));session.enable(True)
        session.read('01020304');self.assertIn('Tag 1 gelesen um 12:00:01',session.hint())
        session.confirmed('01020304',BASE);session.read('AABBCCDD')
        self.assertIn('Tag 2 gelesen um 12:00:03',session.hint())
        self.assertIn('Tag 2 ist bereit',session.hint())
        self.assertNotIn('Tag 2 geschrieben',session.hint())
        self.assertNotIn('AABBCCDD',session.written_at)
        session.confirmed('AABBCCDD',BASE)
        self.assertIn('Tag 2 geschrieben und zurückgelesen um 12:00:04',session.hint())
        self.assertIn('2/2',session.hint())
    def test_reading_written_tag_keeps_its_number_and_does_not_advance(self):
        session=TwoTagSession(clock=lambda:'12:00:00');session.enable(True)
        session.read('01020304');session.confirmed('01020304',BASE)
        session.read('01020304')
        self.assertIn('Tag 1 erneut gelesen',session.hint())
        self.assertIn('Bereits geschrieben und geprüft',session.hint())
        self.assertNotIn('Tag 2 ist bereit',session.hint())
        self.assertEqual(len(session.written),1)
    def test_reset_clears_read_write_feedback(self):
        session=TwoTagSession();session.enable(True);session.read('01020304');session.confirmed('01020304',BASE)
        session.reset()
        self.assertFalse(session.last_event);self.assertEqual(session.written_at,{})
        self.assertIsNone(session.last_read_uid)
    def test_turning_off_restores_normal_read_behavior(self):
        session=TwoTagSession();session.enable(True,seen=True);session.confirmed('01020304',BASE)
        session.enable(False);self.assertFalse(session.preserve_values);self.assertFalse(session.locked)

class TwoCardDevicePath(unittest.TestCase):
    def test_two_different_cards_get_equal_payload_and_individual_keys(self):
        import tempfile
        from cfs_device import Bridge
        from cfs_codec import derive_key
        from test_cfs import MifareTag,FakeSerial
        payloads=[];keys=[]
        with tempfile.TemporaryDirectory() as folder:
            for uid in ('01020304','AABBCCDD'):
                tag=MifareTag(uid);serial=FakeSerial(tag)
                bridge=Bridge('/dev/test-only',serial_factory=lambda **kwargs:serial,reset_wait=0)
                try:
                    result=bridge.write_tag(uid,replace(BASE,weight_g=850),Path(folder))
                    self.assertTrue(result['verified'])
                    payload=b''.join(tag.blocks[n] for n in (4,5,6));payloads.append(payload);keys.append(tag.key_a)
                    self.assertEqual(tag.key_a,derive_key(uid))
                    self.assertLessEqual(abs(decode_payload(payload)['weight_g']-850),3)
                finally:bridge.close()
        self.assertEqual(payloads[0],payloads[1]);self.assertNotEqual(keys[0],keys[1])
