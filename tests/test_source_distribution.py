# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'app/creality-cfs-writer')]
import start
import cfs_label_protocol as protocol
from cfs_arduino import upload_bridge, export_ide_sketch


class SourceUpload(unittest.TestCase):
    def test_builds_selected_board_from_source_before_verified_upload(self):
        class Port:
            device = 'TEST-PORT'
        for board, sketch in (('mega2560', 'CFS_Mega_Bridge'), ('nano328p', 'CFS_Nano_Bridge'), ('nano328p_old', 'CFS_Nano_Bridge')):
            with self.subTest(board=board), tempfile.TemporaryDirectory() as directory:
                (Path(directory)/'arduino-tools').mkdir()
                with patch('serial.tools.list_ports.comports', return_value=[Port()]), patch('cfs_arduino.prepare_tools', return_value=['fake-cli']), patch('cfs_arduino.run') as run:
                    report = upload_bridge(Port.device, directory, board=board)
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual(commands[0][1:], ['lib', 'install', 'MFRC522@1.4.12'])
                self.assertIn('compile', commands[1])
                self.assertTrue(commands[1][-1].endswith(sketch))
                self.assertIn('--verify', commands[2])
                self.assertIn(Port.device, commands[2])
                self.assertEqual(report['board'], board)
                self.assertEqual(report['version'], '1.1.0')

    def test_disconnect_during_compile_prevents_upload(self):
        class Port:
            device = 'TEST-PORT'
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'arduino-tools').mkdir()
            with patch('serial.tools.list_ports.comports', side_effect=[[Port()], []]), patch('cfs_arduino.prepare_tools', return_value=['fake-cli']), patch('cfs_arduino.run') as run:
                with self.assertRaisesRegex(ValueError, 'nicht mehr vorhanden'):
                    upload_bridge(Port.device, directory)
            self.assertEqual(len(run.call_args_list), 2)

    def test_compile_failure_never_starts_upload(self):
        class Port:
            device = 'TEST-PORT'
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'arduino-tools').mkdir()
            with patch('serial.tools.list_ports.comports', return_value=[Port()]), patch('cfs_arduino.prepare_tools', return_value=['fake-cli']), patch('cfs_arduino.run', side_effect=[None, ValueError('compile failed')]) as run:
                with self.assertRaisesRegex(ValueError, 'compile failed'):
                    upload_bridge(Port.device, directory)
            self.assertEqual(len(run.call_args_list), 2)

    def test_exported_sketch_keeps_license_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            for board in ('mega2560', 'nano328p', 'nano328p_old'):
                result = export_ide_sketch(directory, board)
                text = Path(result['path']).read_text()
                self.assertIn('PolyForm-Noncommercial-1.0.0', text)
                self.assertIn('https://polyformproject.org/licenses/noncommercial/1.0.0', text)


class PortableStartup(unittest.TestCase):
    def test_default_paths_follow_each_operating_system(self):
        with patch.dict(os.environ, {}, clear=True):
            for platform, suffix in (('linux', '.local/share/cfs-tagwriter/data'), ('darwin', 'Library/Application Support/CFS-Tagwriter/data'), ('win32', 'AppData/Local/CFS-Tagwriter/data')):
                with self.subTest(platform=platform), patch.object(sys, 'platform', platform):
                    self.assertEqual(start.user_data_directory(), Path.home()/suffix)

    def test_existing_profile_registry_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            registry = Path(directory)/'profil-zuordnung.json'
            original = b'{"test":"existing user data"}'
            registry.write_bytes(original)
            with patch('cfs_writer.main', return_value=0) as run:
                self.assertEqual(start.main(['--demo', '--data-dir', directory]), 0)
            self.assertEqual(registry.read_bytes(), original)
            self.assertEqual(run.call_args.args[0], ['--registry', str(registry), '--demo'])

    def test_fresh_profile_registry_has_no_printer_or_personal_profiles(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ), patch('cfs_writer.main', return_value=0):
            start.main(['--demo', '--data-dir', directory])
            data = json.loads((Path(directory)/'profil-zuordnung.json').read_text())
            self.assertEqual(data['profiles'], [])
            self.assertEqual(data['printer']['ip'], '')

    def test_mac_homebrew_library_paths_and_explicit_dll_are_supported(self):
        protocol.compression_library.cache_clear()
        self.addCleanup(protocol.compression_library.cache_clear)
        with patch.dict(os.environ, {'CFS_LIBLZMA': ''}), patch.object(sys, 'platform', 'darwin'), patch('ctypes.util.find_library', return_value=None), patch.object(protocol.C, 'CDLL') as load:
            library = MagicMock()
            load.side_effect = lambda path: library if path.startswith('/opt/homebrew/') else (_ for _ in ()).throw(OSError())
            self.assertIs(protocol.compression_library(), library)
        protocol.compression_library.cache_clear()
        with tempfile.TemporaryDirectory() as directory:
            dll = Path(directory)/'liblzma.dll'
            dll.touch()
            with patch.dict(os.environ, {'CFS_LIBLZMA': str(dll)}), patch.object(protocol.C, 'CDLL', return_value=library) as load:
                self.assertIs(protocol.compression_library(), library)
                load.assert_called_once_with(str(dll))


if __name__ == '__main__':
    unittest.main()
