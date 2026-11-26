# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/creality-cfs-writer'))
from cfs_firmware_check import FirmwareHistory, read_firmware, repair_message, check_printer
from cfs_service_manager import service_status

RUNNING = {'installed': True, 'running': True, 'state': 'running'}


class FirmwareChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.history = FirmwareHistory(self.temp.name)

    def observe(self, version, **kwargs):
        return self.history.observe('10.0.0.1', 'K2-Pro-one', version, RUNNING, **kwargs)

    def test_first_successful_check_establishes_baseline_without_warning(self):
        self.assertFalse(self.observe('1.1.8.3')['needs_repair'])

    def test_change_requires_manual_reinstall_even_if_service_still_runs(self):
        self.observe('1.1.8.3')
        report = self.observe('1.1.9.0')
        self.assertTrue(report['needs_repair'])
        self.assertIn('1.1.8.3 → 1.1.9.0', repair_message(report))
        self.assertEqual(self.history.pending('10.0.0.1'), report)
        self.assertTrue(self.observe('1.1.9.0')['needs_repair'])

    def test_downgrade_and_version_suffix_changes_are_detected(self):
        self.observe('1.1.8.3')
        self.assertTrue(self.observe('1.1.8.2')['needs_repair'])
        self.assertTrue(self.observe('1.1.8.2-beta')['needs_repair'])

    def test_only_successful_manual_repair_clears_persistent_warning(self):
        self.observe('1.1.8.3')
        self.observe('1.1.9.0')
        self.assertFalse(self.observe('1.1.9.0', repaired=True)['needs_repair'])
        self.assertIsNone(self.history.pending('10.0.0.1'))
        self.assertFalse(self.observe('1.1.9.0')['needs_repair'])

    def test_missing_or_broken_service_warns_on_first_start(self):
        for state in ('missing', 'broken'):
            report = self.history.observe('10.0.0.2', 'printer-'+state, '1.1.8.3', {'state': state})
            self.assertTrue(report['needs_repair'])

    def test_stopped_service_does_not_invent_firmware_change(self):
        report = self.history.observe('10.0.0.1', 'K2-Pro-one', '1.1.8.3', {'state': 'stopped'})
        self.assertFalse(report['needs_repair'])
        with self.assertRaises(ValueError):
            self.history.observe('10.0.0.1', 'K2-Pro-one', '1.1.8.3', {'state': 'stopped'}, repaired=True)

    def test_printers_are_independent_and_ip_change_preserves_history(self):
        self.observe('1.1.8.3')
        other = self.history.observe('10.0.0.2', 'Hi-two', '1.0.0', RUNNING)
        self.assertFalse(other['needs_repair'])
        moved = self.history.observe('10.0.0.3', 'K2-Pro-one', '1.1.9.0', RUNNING)
        self.assertTrue(moved['needs_repair'])
        self.assertIsNone(self.history.pending('10.0.0.2'))

    def test_identical_checks_do_not_rewrite_state(self):
        self.observe('1.1.8.3')
        before = self.history.path.stat().st_mtime_ns
        self.observe('1.1.8.3')
        self.assertEqual(self.history.path.stat().st_mtime_ns, before)

    def test_unrecognized_firmware_is_not_replaced_by_klipper_version(self):
        class Remote:
            def run(self, command, **kwargs): return b'{"software_version":"klipper-hash"}'
        with self.assertRaises(ValueError): read_firmware(Remote())

    def test_both_supported_version_sources(self):
        class Remote:
            def run(self, command, **kwargs): return self.raw
        remote = Remote()
        for raw in (b'{"sys_version":"1.1.8.3"}', b'version=1.1.8.3\n'):
            remote.raw = raw
            self.assertEqual(read_firmware(remote), '1.1.8.3')

    def test_offline_check_preserves_history(self):
        self.observe('1.1.8.3')
        before = self.history.path.read_bytes()
        with patch('cfs_printer_identity.probe_printer', side_effect=TimeoutError), patch('cfs_service_manager.remote_for') as remote:
            with self.assertRaises(TimeoutError):
                check_printer(None, self.temp.name, '', address='10.0.0.1')
        remote.assert_not_called()
        self.assertEqual(self.history.path.read_bytes(), before)


class ServiceFileRegression(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Printer process check requires Linux /proc')
    def test_orphaned_autostart_cannot_report_running(self):
        # Execute the real remote diagnostic script against a miniature local
        # filesystem. Its init status lies exactly as the affected printer did.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            init = base/'init'
            init.write_text('#!/bin/sh\n# '+str(base/'cloud_service.py')+'\nexit 0\n')
            init.chmod(0o755)
            class Remote:
                def run(self, command):
                    script = command.split("\n", 1)[1].rsplit('\nCFS_STATUS', 1)[0]
                    return subprocess.check_output([sys.executable, '-c', script])
            with patch('cfs_service_manager.INIT', str(init)), patch('cfs_service_manager.REMOTE_CONFIG', str(base)), patch('cfs_service_manager.REMOTE_SERVICE', str(base/'cloud_service.py')):
                report = service_status(None, None, _remote=Remote())
            self.assertEqual(report['state'], 'broken')
            self.assertFalse(report['running'])
            self.assertIsNone(report['version'])


if __name__ == '__main__':
    unittest.main()
