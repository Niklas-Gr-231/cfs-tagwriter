# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/creality-cfs-writer'))
from cfs_connections import ConnectionStore,SERVICE
from cfs_printer_identity import printer_identity,icon_name

class MemoryKeyring:
    def __init__(self):self.secrets={}
    def get_password(self,service,user):return self.secrets.get((service,user))
    def set_password(self,service,user,value):self.secrets[(service,user)]=value
    def delete_password(self,service,user):self.secrets.pop((service,user),None)

class Connections(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.backend=MemoryKeyring();self.store=ConnectionStore(self.temp.name,self.backend)
    def test_default_does_not_store_password(self):
        self.store.remember('Test','10.0.0.1','private-value')
        self.assertFalse(self.store.choices()[0]['password_saved']);self.assertEqual(self.backend.secrets,{})
        self.assertNotIn('private-value',self.store.path.read_text())
    def test_password_is_only_in_keyring_and_reloaded_by_endpoint(self):
        self.store.remember('A','10.0.0.1','secret-A',True)
        self.store.remember('B','10.0.0.2','secret-B',True)
        self.assertEqual(self.store.password('10.0.0.1'),'secret-A');self.assertEqual(self.store.password('10.0.0.2'),'secret-B')
        self.assertEqual(self.store.password('10.0.0.3'),'')
        for path in Path(self.temp.name).iterdir():self.assertNotIn('secret-',path.read_text())
    def test_forget_keeps_ip_and_model_and_removes_keyring_password(self):
        self.store.remember('A','10.0.0.1','secret-A',True,model='F012')
        self.store.remember('A','10.0.0.1','',False)
        self.assertEqual(self.store.password('10.0.0.1'),'');self.assertFalse(self.backend.secrets)
        self.assertEqual(self.store.choices()[0]['model'],'F012')
    def test_secret_from_other_data_folder_is_not_silently_loaded(self):
        self.backend.set_password(SERVICE,'root@10.0.0.1','private')
        self.assertEqual(self.store.password('10.0.0.1'),'')
    def test_keyring_failure_does_not_save_secret_to_file(self):
        with patch.object(self.backend,'set_password',side_effect=RuntimeError('must-not-leak-secret')):
            with self.assertRaises(ValueError) as caught:self.store.remember('A','10.0.0.1','must-not-leak-secret',True)
        self.assertNotIn('must-not-leak-secret',str(caught.exception));self.assertFalse(self.store.path.exists())
    def test_invalid_address_name_password_rejected_before_storage(self):
        for args in [('A','127.0.0.1','pw',True),('','10.0.0.1','pw',True),('A','10.0.0.1','bad\npassword',True)]:
            with self.assertRaises(ValueError):self.store.remember(*args)
        self.assertFalse(self.backend.secrets)
    def test_renaming_same_endpoint_updates_one_entry(self):
        self.store.remember('A','10.0.0.1');self.store.remember('B','10.0.0.1')
        self.assertEqual(len(self.store.choices()),1);self.assertEqual(self.store.choices()[0]['name'],'B')

class Reply:
    def __init__(self,value):self.value=json.dumps(value).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,_limit):return self.value
class Identity(unittest.TestCase):
    def fetch(self,url,timeout):
        return Reply({'result':{'hostname':'K2Pro-Test','state':'ready'}} if url.endswith('/printer/info') else {'printer_int_name':'F012'})
    def test_configured_network_alias_preferred_over_default_hostname(self):
        with patch('urllib.request.urlopen',side_effect=self.fetch),patch('socket.gethostbyaddr',return_value=('Werkstatt.fritz.box',[],[])):
            result=printer_identity('10.0.0.1')
        self.assertEqual(result['name'],'Werkstatt.fritz.box');self.assertEqual(result['model'],'F012')
    def test_hostname_fallback_without_dns(self):
        with patch('urllib.request.urlopen',side_effect=self.fetch),patch('socket.gethostbyaddr',side_effect=OSError()):
            result=printer_identity('10.0.0.1')
        self.assertEqual(result['name'],'K2Pro-Test')
    def test_custom_printer_name_preferred(self):
        with patch('urllib.request.urlopen',return_value=Reply({'result':{'device_name':'Mein Drucker','hostname':'default','state':'ready'}})),patch('socket.gethostbyaddr',return_value=('dns',[],[])):
            result=printer_identity('10.0.0.1')
        self.assertEqual(result['name'],'Mein Drucker')
    def test_unreachable_printer_keeps_manual_name_workflow(self):
        with patch('urllib.request.urlopen',side_effect=OSError()),patch('socket.gethostbyaddr',side_effect=OSError()):
            with self.assertRaises(ValueError):printer_identity('10.0.0.1')
    def test_model_artwork_mapping(self):
        self.assertEqual(icon_name('F018'),'printer-hi.png');self.assertEqual(icon_name('F012'),'printer-closed.png');self.assertEqual(icon_name('unknown'),'printer-generic.png')
