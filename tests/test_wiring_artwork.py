# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Check the actual illustrated wires and breadboard connections, not a copy of the drawing code."""
from collections import Counter
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).resolve().parents[1]/'app/creality-cfs-writer/hardware-assets'


class WiringArtwork(unittest.TestCase):
    def test_both_board_drawings_have_four_isolated_voltage_dividers(self):
        for family, pins in (
            ('mega2560', {'SS': '53', 'SCK': '52', 'MOSI': '51', 'RST': '5', 'MISO': '50'}),
            ('nano328p', {'SS': 'D10', 'SCK': 'D13', 'MOSI': 'D11', 'RST': 'D9', 'MISO': 'D12'}),
        ):
            with self.subTest(board=family):
                svg = ET.parse(ASSETS/(family+'-breadboard.svg'))
                nodes = {e.get('data-node'): (float(e.get('cx')), float(e.get('cy')))
                         for e in svg.iter() if e.get('data-node')}
                parent = {key: key for key in nodes}

                def find(key):
                    while parent[key] != key:
                        key = parent[key]
                    return key

                def join(a, b):
                    parent[find(a)] = find(b)

                def same(a, b):
                    self.assertEqual(find(a), find(b), (a, b))

                # Real breadboard topology: separate groups of five holes.
                for column in range(1, 31):
                    for group in ('abcde', 'fghij'):
                        for row in group[1:]:
                            join(f'bb:{group[0]}{column}', f'bb:{row}{column}')
                for rail in ('red-top', 'blue-top', 'blue-bottom', 'red-bottom'):
                    for column in range(2, 31):
                        join(f'bb:{rail}1', f'bb:{rail}{column}')

                occupied = []
                resistors = []
                for element in svg.iter():
                    a, b = element.get('data-from'), element.get('data-to')
                    if not a:
                        continue
                    self.assertIn(a, nodes)
                    self.assertIn(b, nodes)
                    occupied.extend((a, b))
                    if element.get('data-component') == 'resistor':
                        resistors.append((a, b, int(element.get('data-ohms'))))
                    else:
                        points = [tuple(map(float, part.split(','))) for part in element.get('points').split()]
                        self.assertEqual(points[0], nodes[a])
                        self.assertEqual(points[-1], nodes[b])
                        join(a, b)
                # Each drawn terminal/hole gets one lead only.
                self.assertEqual(max(Counter(occupied).values()), 1)
                self.assertEqual(Counter(r[2] for r in resistors), {1000: 4, 2000: 4})
                self.assertNotIn('reader:IRQ', occupied)
                same('mcu:GND', 'reader:GND')
                same('mcu:'+pins['MISO'], 'reader:MISO')
                if family == 'mega2560':
                    same('mcu:3.3V', 'reader:3.3V')
                else:
                    same('mcu:5V', 'reg:IN')
                    same('reg:OUT', 'reader:3.3V')
                    same('reg:GND', 'reader:GND')
                    self.assertNotEqual(find('mcu:5V'), find('reader:3.3V'))
                for signal in ('SS', 'SCK', 'MOSI', 'RST'):
                    source = 'mcu:'+pins[signal]
                    destination = 'reader:'+('SDA' if signal == 'SS' else signal)
                    self.assertNotEqual(find(source), find(destination))
                    self.assertNotEqual(find(destination), find('reader:GND'))
                    matching = [(a, b, ohms) for a, b, ohms in resistors
                                if find(a) == find(source) and find(b) == find(destination)]
                    self.assertEqual([ohms for _, _, ohms in matching], [1000])
                    matching = [(a, b, ohms) for a, b, ohms in resistors
                                if find(a) == find(destination) and find(b) == find('reader:GND')]
                    self.assertEqual([ohms for _, _, ohms in matching], [2000])

    def test_all_sheets_include_license_and_matching_readable_png(self):
        from PIL import Image
        for name in ('mega2560-breadboard', 'nano328p-breadboard', 'spannungsteiler-detail'):
            with self.subTest(sheet=name):
                text = (ASSETS/(name+'.svg')).read_text()
                self.assertIn('PolyForm Noncommercial 1.0.0', text)
                with Image.open(ASSETS/(name+'.png')) as image:
                    self.assertEqual(image.width, 3280)
                    image.verify()
