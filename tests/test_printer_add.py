# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from cfs_connections import ConnectionStore
from cfs_printer_add import configured_printers,save_printer


class PrinterAdd(unittest.TestCase):
    def test_offline_add_preserves_active_printer_and_requires_valid_target(self):
        with tempfile.TemporaryDirectory() as directory:
            app=SimpleNamespace(data_dir=Path(directory),registry=None)
            for brand,model in [('Creality','Hi'),('Anycubic','Kobra S1')]:
                ip='10.0.0.7' if brand=='Creality' else '10.0.0.8'
                with patch('cfs_connections.ConnectionStore._keyring',side_effect=AssertionError('Must not access passwords')):
                    if brand=='Creality':saved=save_printer(app,'Test printer',ip,brand,model)
                    else:
                        from cfs_anycubic_feeders import FEEDERS
                        feeder=FEEDERS['ace_pro'];variant=next(key for key,item in feeder['variants'].items() if model in item[1])
                        saved=save_printer(app,'Test printer',ip,brand,model,feeder_id='ace_pro',feeder_variant=variant)
                self.assertEqual(saved['model'],brand+' '+model)
            self.assertEqual(len(configured_printers(app)),2)
            with self.assertRaises(ValueError):save_printer(app,'Invalid','10.0.0.9','Unknown','Anything')

    def test_existing_bookmark_is_not_overwritten_or_password_forgotten(self):
        with tempfile.TemporaryDirectory() as directory:
            app=SimpleNamespace(data_dir=Path(directory),registry=None)
            store=ConnectionStore(directory);store.remember('Original','10.0.0.7',model='Creality K2 Pro')
            before=store.path.read_bytes()
            with patch('cfs_connections.ConnectionStore._keyring',side_effect=AssertionError('Must not access passwords')):
                with self.assertRaisesRegex(ValueError,'bereits eingerichtet'):save_printer(app,'Replacement','10.0.0.7','Creality','Hi')
            self.assertEqual(store.path.read_bytes(),before)

    def test_add_keeps_the_active_printer_and_detects_its_address(self):
        with tempfile.TemporaryDirectory() as directory:
            active={'name':'Source','ip':'10.0.0.1','printer_int_name':'F012'}
            registry=SimpleNamespace(printer=dict(active),printer_choices=lambda:[dict(active)])
            app=SimpleNamespace(data_dir=Path(directory),registry=registry)
            save_printer(app,'New printer','10.0.0.2','Creality','Hi')
            self.assertEqual(registry.printer,active)
            self.assertEqual(len(configured_printers(app)),2)
            with self.assertRaisesRegex(ValueError,'bereits eingerichtet'):
                save_printer(app,'Wrong replacement','10.0.0.1','Creality','Hi')
