# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Execute the real firmware command parser against a simulated RC522."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++'), 'Native C++ compiler not available; real AVR builds are also required for a firmware release.')
class BridgeParser(unittest.TestCase):
    def test_classic_and_ntag_guardrails_on_both_board_variants(self):
        for sketch, flags in (('CFS_Mega_Bridge', []), ('CFS_Nano_Bridge', ['-D__AVR_ATmega328P__'])):
            with self.subTest(board=sketch), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                for path in (ROOT/'tests/firmware').iterdir():
                    shutil.copyfile(path, work/path.name)
                shutil.copyfile(ROOT/'app/creality-cfs-writer'/sketch/(sketch+'.ino'), work/'bridge.ino')
                target = work/('check.exe' if __import__('sys').platform == 'win32' else 'check')
                compiled = subprocess.run(['g++', '-std=c++17', '-O1', '-I', str(work), *flags,
                                           str(work/'test.cpp'), '-o', str(target)], capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                checked = subprocess.run([str(target)], capture_output=True, text=True, timeout=10)
                self.assertEqual(checked.returncode, 0, checked.stdout+checked.stderr)
