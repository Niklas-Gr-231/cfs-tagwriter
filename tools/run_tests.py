#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Run only self-contained tests with generated fixtures and mock transports."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app/creality-cfs-writer'), str(ROOT/'app/creality-cfs-cloud'), str(ROOT/'tests')]

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
