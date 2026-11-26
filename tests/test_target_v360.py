# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Printer isolation, truthful access help and complete ACE pair identities."""
from pathlib import Path
import tempfile
import unittest
from cfs_service_history import ServiceHistory
from cfs_ssh_help import help_text
from cfs_compatibility import rows, material_printer
from cfs_anycubic import AceSpec
from cfs_pairing import payload_identity


class ServiceVersions(unittest.TestCase):
    def test_versions_are_separate_for_printers_even_with_same_model(self):
        with tempfile.TemporaryDirectory() as directory:
            history=ServiceHistory(directory)
            for ip,version,running in [('192.0.2.10','2.0.0',True),('192.0.2.11','2.1.0',False)]:
                history.observe(ip,dict(installed=True,running=running,state='running' if running else 'stopped',version=version,model='F012'))
            self.assertEqual(history.get('192.0.2.10')['version'],'2.0.0')
            self.assertTrue(history.get('192.0.2.10')['running'])
            self.assertFalse(history.get('192.0.2.11')['running'])
            self.assertIsNone(history.get('192.0.2.12'))
            self.assertIn('zuletzt bestätigt',history.label('192.0.2.11'))
            self.assertIn('noch nicht geprüft',history.label('192.0.2.12'))

    def test_uninstall_updates_only_target_and_excludes_access_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            history=ServiceHistory(directory)
            report=dict(installed=True,running=True,state='running',version='2.1.0',model='F012',password='excluded-test-value')
            history.observe('192.0.2.10',report)
            history.observe('192.0.2.11',report)
            history.observe('192.0.2.10',dict(installed=False,running=False,state='missing',version=None))
            self.assertTrue(history.get('192.0.2.11')['installed'])
            self.assertFalse(history.get('192.0.2.10')['installed'])
            self.assertNotIn('excluded-test-value',history.path.read_text())

    def test_corrupt_history_does_not_get_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            history=ServiceHistory(directory);history.path.parent.mkdir(parents=True)
            history.path.write_text('{"schema_version":2}')
            with self.assertRaises(ValueError):history.observe('192.0.2.10',{})
            self.assertEqual(history.path.read_text(),'{"schema_version":2}')


class PrinterHelp(unittest.TestCase):
    def test_every_catalog_model_has_appropriate_help(self):
        for info in rows():
            with self.subTest(info=info):
                text=help_text('192.0.2.10',info['manufacturer']+' '+info['model'])
                self.assertIn(info['model'].upper(),text)
                if info['manufacturer']=='Anycubic':
                    self.assertIn('keinen SSH-Installer',text)
                    self.assertNotIn('ssh root@',text)
                else:
                    self.assertIn('ssh root@192.0.2.10',text)
                    self.assertIn('angezeigten Zugangsdaten',text)

    def test_unknown_model_does_not_receive_invented_access(self):
        for model in ('Unknown printer','F099'):
            text=help_text('192.0.2.10',model)
            self.assertIn('keine bestätigte SSH',text)
            self.assertNotIn('ssh root@',text)

    def test_imported_profile_printer_takes_precedence_over_active_other_brand(self):
        info=material_printer({'printer_manufacturer':'Anycubic','printer_model':'Kobra S1'},{'printer_int_name':'F012'})
        self.assertEqual((info['manufacturer'],info['model']),('Anycubic','Kobra S1'))
