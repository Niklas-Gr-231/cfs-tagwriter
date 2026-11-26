#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Draw original breadboard illustrations with electrically testable SVG nodes."""
import argparse
from html import escape
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT/'app/creality-cfs-writer/hardware-assets'
COLORS = {'SS': '#D36A12', 'SCK': '#A48200', 'MOSI': '#138A53', 'RST': '#8253B8',
          'MISO': '#167BA7', '3.3V': '#CD3247', 'GND': '#374151', '5V': '#C24E26'}
PINS = {
    'mega2560': {'SS': '53', 'SCK': '52', 'MOSI': '51', 'RST': '5', 'MISO': '50'},
    'nano328p': {'SS': 'D10', 'SCK': 'D13', 'MOSI': 'D11', 'RST': 'D9', 'MISO': 'D12'},
}


class Drawing:
    def __init__(self, title, width=1640, height=1250):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                      '<title>'+escape(title)+'</title>',
                      '<metadata>Original project artwork. PolyForm Noncommercial 1.0.0. https://polyformproject.org/licenses/noncommercial/1.0.0</metadata>',
                      '<rect width="100%" height="100%" fill="#FFFFFF"/>']
        self.nodes = {}

    def rect(self, x, y, w, h, fill, stroke='none', radius=0, **attributes):
        extra = ' '.join(f'{k.replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in attributes.items())
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" {extra}/>')

    def text(self, x, y, value, size=18, color='#233044', weight='normal', anchor='start', **attributes):
        extra = ' '.join(f'{k.replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in attributes.items())
        self.parts.append(f'<text x="{x}" y="{y}" font-family="DejaVu Sans,sans-serif" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(value)}</text>')

    def circle(self, x, y, radius, fill, stroke='none', **attributes):
        extra = ' '.join(f'{k.replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in attributes.items())
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{fill}" stroke="{stroke}" {extra}/>')

    def node(self, name, x, y, fill='#C8CDD3', radius=4):
        self.nodes[name] = (x, y)
        self.circle(x, y, radius, fill, data_node=name)

    def route(self, start, end, waypoints, color, width=6):
        points = [self.nodes[start], *waypoints, self.nodes[end]]
        value = ' '.join(f'{x},{y}' for x, y in points)
        # A white outline makes insulated crossings distinct from junctions.
        self.parts.append(f'<polyline points="{value}" fill="none" stroke="#FFFFFF" stroke-width="{width+3}" stroke-linejoin="round" stroke-linecap="round"/>')
        self.parts.append(f'<polyline points="{value}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" data_from="{start}" data_to="{end}"/>'.replace('data_from', 'data-from').replace('data_to', 'data-to'))
        for point in (points[0], points[-1]):
            self.circle(*point, 6, color, '#FFFFFF')

    def resistor(self, name, start, end, ohms, label_x, label_y, stacked=False):
        x1, y1 = self.nodes[start]
        x2, y2 = self.nodes[end]
        length = math.hypot(x2-x1, y2-y1)
        angle = math.degrees(math.atan2(y2-y1, x2-x1))
        body = min(42, length-16)
        self.parts.append(f'<g data-component="resistor" data-name="{name}" data-ohms="{ohms}" data-from="{start}" data-to="{end}" transform="translate({(x1+x2)/2},{(y1+y2)/2}) rotate({angle})">')
        self.parts.append(f'<line x1="{-length/2}" y1="0" x2="{length/2}" y2="0" stroke="#8E969F" stroke-width="3"/>')
        self.rect(-body/2, -8, body, 16, '#D5B588', '#AA8F6A', 5)
        bands = ['#743B1B', '#202020', '#D52E34', '#C19B32'] if ohms == 1000 else ['#D52E34', '#202020', '#D52E34', '#C19B32']
        for position, color in zip((-.31, -.12, .07, .34), bands):
            self.rect(position*body-1.6, -8, 3.2, 16, color)
        self.parts.append('</g>')
        if stacked:
            self.rect(label_x-3, label_y-14, 47, 36, '#FFFFFF', radius=3)
            self.text(label_x, label_y, name, 13, weight='bold')
            self.text(label_x, label_y+17, f'{ohms//1000} kΩ', 13, weight='bold')
            return
        label = f'{name} · {ohms//1000} kΩ'
        self.rect(label_x-4, label_y-14, max(91, len(label)*8), 20, '#FFFFFF', radius=3)
        self.text(label_x, label_y, label, 13, weight='bold')

    def save(self, destination, name, png=False):
        destination.mkdir(parents=True, exist_ok=True)
        raw = '\n'.join([*self.parts, '</svg>']).encode()
        (destination/(name+'.svg')).write_bytes(raw)
        if png:
            import cairosvg
            cairosvg.svg2png(bytestring=raw, write_to=str(destination/(name+'.png')), scale=2)


def breadboard(draw):
    draw.rect(411, 275, 745, 475, '#EFF0EC', '#BFC4BF', 17)
    draw.rect(423, 504, 721, 23, '#D9DCD5', radius=5)
    draw.text(425, 260, 'Breadboard · Spalten 1–30', 20, weight='bold')
    for y, color, label in ((315, '#CD3247', '+  3,3 V'), (340, '#B1B6B5', '−'), (690, '#2D74A3', '−  GND'), (715, '#D2A9A9', '+')):
        draw.rect(438, y-10, 675, 2, color)
        draw.text(1125, y+6, label, 13, color)
    for column in range(1, 31):
        x = 455+(column-1)*22
        for row, y in zip('abcdefghij', (390, 415, 440, 465, 490, 540, 565, 590, 615, 640)):
            draw.node(f'bb:{row}{column}', x, y, '#92988E', 3.4)
        for rail, y in (('red-top', 315), ('blue-top', 340), ('blue-bottom', 690), ('red-bottom', 715)):
            draw.node(f'bb:{rail}{column}', x, y, '#8E958B', 3.4)
        draw.text(x, 370, str(column), 10, '#727970', anchor='middle')
        draw.text(x, 667, str(column), 10, '#727970', anchor='middle')
    for row, y in zip('abcdefghij', (390, 415, 440, 465, 490, 540, 565, 590, 615, 640)):
        draw.text(426, y+4, row, 13, '#727970')


def mega(draw):
    x, y = 70, 220
    draw.rect(x, y, 270, 520, '#127183', '#0C5262', 12)
    draw.rect(x+14, y-13, 45, 66, '#282B30', radius=4)
    draw.rect(x+173, y-19, 58, 72, '#C3C8CC', '#8A9198', 3)
    for offset in range(0, 62, 9):
        draw.rect(x+176, y-11+offset, 52, 2, '#929BA1')
    draw.text(x+136, y+93, 'MEGA2560 R3', 22, '#FFFFFF', 'bold', 'middle')
    draw.text(x+137, y+119, '5-V-Logik', 15, '#CDEBF1', anchor='middle')
    draw.rect(x+97, y+211, 78, 82, '#242A2B', radius=3)
    for dx in (92, 176):
        for dy in range(218, 289, 10):
            draw.rect(x+dx, y+dy, 6, 4, '#A5ACAD')
    for cx, cy in ((x+18,y+80),(x+250,y+80),(x+18,y+491),(x+247,y+491)):
        draw.circle(cx, cy, 6, '#E8EEF0')
    power = ['NC', 'IOREF', 'RESET', '3.3V', '5V', 'GND', 'GND2', 'VIN']
    for index, pin in enumerate(power):
        py = y+130+index*13
        draw.rect(x+4, py-5, 16, 10, '#242A2B')
        draw.node('mcu:'+pin, x+12, py)
        draw.text(x+27, py+4, pin, 10, '#FFFFFF')
    for index in range(16):
        py = y+260+index*11
        draw.rect(x+4, py-5, 16, 10, '#242A2B')
        draw.circle(x+12, py, 3, '#A6ADB1')
        draw.text(x+25, py+4, 'A'+str(index), 9, '#D1E4E7')
    rows = [(pin, y+140+i*12) for i,pin in enumerate(['13','12','11','10','9','8'])]
    rows += [(pin, y+230+i*12) for i,pin in enumerate(['7','6','5','4','3','2','1','0'])]
    rows += [(str(pin), y+340+(pin-14)*12) for pin in range(14,22)]
    for pin, py in rows:
        draw.rect(x+249, py-5, 17, 10, '#242A2B')
        draw.node('mcu:'+pin, x+257, py)
        draw.text(x+241, py+4, pin, 10, '#FFFFFF', anchor='end')
    for row, values in enumerate((['5V-X', *map(str, range(22,54,2)), 'GND-X'], ['5V-Y', *map(str, range(23,54,2)), 'GND-Y'])):
        for index, pin in enumerate(values):
            px, py = x+25+index*12, y+475+row*14
            draw.rect(px-5, py-5, 10, 10, '#242A2B')
            draw.node('mcu:'+pin, px, py, '#A6ADB1', 3)
    draw.text(285, 681, '50  52', 12, '#FFFFFF', 'bold', 'middle')
    draw.text(285, 731, '51  53', 12, '#FFFFFF', 'bold', 'middle')
    draw.text(205, 199, 'Mega2560 R3 · USB oben', 18, weight='bold', anchor='middle')


def nano(draw):
    x, y = 130, 230
    draw.rect(x, y, 150, 340, '#127183', '#0C5262', 9)
    draw.rect(x+45, y-18, 60, 55, '#C3C8CC', '#8A9198', 3)
    draw.rect(x+54, y+116, 44, 48, '#252B2E', radius=3)
    draw.rect(x+61, y+206, 30, 30, '#D1D5D5', '#9CA4A6', 4)
    draw.circle(x+76, y+221, 9, '#A74A42')
    draw.text(x+76, y+90, 'NANO', 19, '#FFFFFF', 'bold', 'middle')
    draw.text(x+76, y+185, 'ATmega328P', 12, '#E0EFF1', anchor='middle')
    left = ['D13','3.3V','AREF',*[f'A{i}' for i in range(8)],'5V','RESET','GND','VIN']
    right = ['D12','D11','D10','D9','D8','D7','D6','D5','D4','D3','D2','GND2','RESET2','RX0','TX1']
    for side, pins in ((0,left),(1,right)):
        for index, pin in enumerate(pins):
            px, py = x+6+side*138, y+40+index*20
            draw.node('mcu:'+pin, px, py, '#D7B56F', 5)
            draw.text(px+(10 if not side else -10), py+4, pin.replace('GND2','GND').replace('RESET2','RST'), 10, '#FFFFFF', anchor='start' if not side else 'end')
    draw.text(x+75, 199, 'Nano Classic · USB oben', 18, weight='bold', anchor='middle')
    draw.rect(90, 610, 230, 120, '#4D896F', '#2E5F4B', 9)
    draw.rect(185, 635, 55, 42, '#252B2E', radius=3)
    draw.text(203, 596, '3,3-V-Reglermodul', 17, weight='bold', anchor='middle')
    for name, px, py, label in (('IN',110,640,'IN 5 V'),('GND',110,695,'GND'),('OUT',300,640,'OUT 3,3 V')):
        draw.node('reg:'+name, px, py, '#D7B56F', 5)
        draw.text(px+(11 if name!='OUT' else -11), py-12, label, 11, '#FFFFFF', 'bold', 'start' if name!='OUT' else 'end')
    draw.text(206, 719, 'Pinfolge am eigenen Modul prüfen', 10, '#FFFFFF', anchor='middle')


def reader(draw):
    x, y = 1290, 270
    draw.rect(x, y, 280, 400, '#224589', '#17315F', 10)
    for inset in (13,20,27,34):
        draw.rect(x+inset, y+inset, 280-2*inset, 169-inset, 'none', '#8BB2D8', 8, stroke_width=2)
    draw.text(x+140, y+86, '13,56 MHz', 23, '#FFFFFF', 'bold', 'middle')
    draw.text(x+140, y+115, 'RC522 / MFRC522', 16, '#DFEAF6', anchor='middle')
    draw.rect(x+112, y+219, 56, 56, '#21252C', radius=2)
    for row in range(5):
        draw.rect(x+104, y+222+row*10, 8, 4, '#B4BFCC')
        draw.rect(x+168, y+222+row*10, 8, 4, '#B4BFCC')
    draw.rect(x+23, y+239, 22, 64, '#B0B9C5', radius=8)
    draw.rect(x+8, 641, 256, 29, '#212733', radius=3)
    for index, pin in enumerate(('SDA','SCK','MOSI','MISO','IRQ','GND','RST','3.3V')):
        px, py = 1312+index*32, 655
        draw.node('reader:'+pin, px, py, '#D7B56F', 5)
        draw.text(px+4, 630, 'SDA/SS' if pin=='SDA' else pin, 13, '#FFFFFF', 'bold', transform=f'rotate(-90,{px+4},630)')
    draw.text(x+140, 251, 'RC522 · Stiftleiste unten', 18, weight='bold', anchor='middle')
    draw.text(x+140, 720, 'IRQ bleibt frei', 17, '#687484', anchor='middle')


def header(draw, title, subtitle):
    draw.rect(40, 35, draw.width-80, 95, '#F2F5F8', radius=16)
    draw.text(65, 74, title, 29, weight='bold')
    draw.text(65, 107, subtitle, 17, '#526276')


def overview(family):
    draw = Drawing(f'{family} mit Breadboard und RC522')
    header(draw, 'RC522 anschließen · '+('Mega2560 R3' if family=='mega2560' else 'Nano Classic ATmega328P'),
           'Vier eigene Spannungsteiler · USB zum Verdrahten abziehen · Ansicht von oben')
    breadboard(draw)
    if family=='mega2560':mega(draw)
    else:nano(draw)
    reader(draw)
    # Supply input and output use different holes of the same continuous rail.
    if family=='mega2560':
        draw.route('mcu:3.3V','bb:red-top1',[(48,389),(48,180),(455,180)],COLORS['3.3V'])
        draw.route('mcu:GND','bb:blue-bottom1',[(30,415),(30,755),(455,755)],COLORS['GND'])
        inputs = {'SS':[(287,820),(499,820)], 'SCK':[(365,695),(365,800),(631,800)],
                  'MOSI':[(275,840),(763,840)], 'RST':[(370,474),(370,760),(895,760)]}
        miso_route = [(275,780),(1408,780)]
    else:
        draw.route('mcu:5V','reg:IN',[(80,490),(80,640)],COLORS['5V'])
        draw.route('reg:OUT','bb:red-top1',[(335,640),(335,180),(455,180)],COLORS['3.3V'])
        draw.route('mcu:GND','bb:blue-bottom1',[(50,530),(50,755),(455,755)],COLORS['GND'])
        draw.route('reg:GND','bb:blue-bottom2',[(110,735),(477,735)],COLORS['GND'])
        inputs = {'SS':[(330,310),(330,820),(499,820)], 'SCK':[(94,270),(94,800),(631,800)],
                  'MOSI':[(350,290),(350,840),(763,840)], 'RST':[(370,330),(370,760),(895,760)]}
        miso_route = [(395,270),(395,780),(1408,780)]
    for index, signal in enumerate(('SS','SCK','MOSI','RST')):
        entry, junction = 3+index*6, 6+index*6
        x = draw.nodes[f'bb:d{junction}'][0]
        draw.route('mcu:'+PINS[family][signal],f'bb:a{entry}',inputs[signal],COLORS[signal])
        draw.resistor('R'+str(index*2+1),f'bb:b{entry}',f'bb:b{junction}',1000,x-64,438)
        draw.resistor('R'+str(index*2+2),f'bb:e{junction}',f'bb:h{junction}',2000,x-59,550,stacked=True)
        draw.route(f'bb:j{junction}',f'bb:blue-bottom{junction}',[],COLORS['GND'],4)
        pin = 'SDA' if signal=='SS' else signal
        rx = draw.nodes['reader:'+pin][0]
        lane = 860+index*30
        draw.route(f'bb:d{junction}','reader:'+pin,[(x+30,465),(x+30,lane),(rx,lane)],COLORS[signal])
    draw.route('mcu:'+PINS[family]['MISO'],'reader:MISO',miso_route,COLORS['MISO'])
    draw.route('bb:red-top30','reader:3.3V',[(1200,315),(1200,1010),(1536,1010)],COLORS['3.3V'])
    draw.route('bb:blue-bottom30','reader:GND',[(1230,690),(1230,1040),(1472,1040)],COLORS['GND'])
    draw.text(450, 218, 'a–e je Spalte verbunden · f–j je Spalte verbunden', 14, '#536271')
    draw.text(450, 239, 'R2 / R4 / R6 / R8 stecken über der isolierenden Mittelrinne.', 14, '#536271')
    draw.rect(60, 1080, 1520, 120, '#F2F5F8', radius=12)
    for index, signal in enumerate(('SS','SCK','MOSI','RST','MISO')):
        x = 85+index*288
        draw.circle(x, 1111, 7, COLORS[signal])
        text = ('SDA/SS' if signal=='SS' else signal)+' ← '+PINS[family][signal]
        draw.text(x+17,1117,text,20,weight='bold')
        draw.text(x+17,1144,'direkt zurück' if signal=='MISO' else '1 kΩ oben + 2 kΩ nach GND',12,'#526276')
    draw.text(85,1178,'Kreuzungen ohne Anschluss sind isolierte Kabel. Kontakt entsteht an den markierten Steckpunkten.',15)
    draw.text(64,1224,'Stromschienen auf Durchgang prüfen · Pinnamen am eigenen Board beachten · Eigene Projektgrafik',14,'#536271')
    return draw


def divider_detail():
    draw = Drawing('Spannungsteiler und Widerstandsfarben',1640,1060)
    header(draw,'Ein Spannungsteiler im Detail','Diesen Aufbau viermal verwenden · jeder Arduino-Ausgang bekommt einen eigenen Teiler')
    draw.rect(390,180,790,520,'#EFF0EC','#BFC4BF',17)
    for column in range(1,9):
        x = 470+(column-1)*85
        for row,y in zip('abcdefghij',(235,285,335,385,435,525,555,585,615,645)):
            draw.node(f'detail:{row}{column}',x,y,'#858D83',5)
        draw.text(x,207,str(column),15,'#536271',anchor='middle')
    for row,y in zip('abcdefghij',(235,285,335,385,435,525,555,585,615,645)):
        draw.text(420,y+5,row,17,'#536271')
    draw.rect(410,455,750,40,'#D8DDD4',radius=6)
    for column,color in ((2,'#D36A12'),(5,'#138A53')):
        x=470+(column-1)*85
        draw.rect(x-18,215,36,242,color,opacity='.12',radius=8)
    draw.node('detail:input',190,235)
    draw.node('detail:reader',1435,385)
    draw.node('detail:GND',1435,645)
    draw.route('detail:input','detail:a2',[],COLORS['SS'])
    draw.resistor('R oben','detail:b2','detail:b5',1000,650,325)
    draw.route('detail:d5','detail:reader',[],COLORS['MOSI'])
    draw.resistor('R unten','detail:e5','detail:h5',2000,840,510)
    draw.route('detail:j5','detail:GND',[],COLORS['GND'])
    draw.text(75,190,'Arduino-Ausgang',23,weight='bold')
    draw.text(75,282,'5 V',23,color=COLORS['SS'],weight='bold')
    draw.text(1210,335,'zum RC522-Eingang',22,weight='bold')
    draw.text(1210,423,'ca. 3,3 V am Abgriff',19,color=COLORS['MOSI'],weight='bold')
    draw.text(1230,615,'gemeinsame Masse',20,weight='bold')
    draw.text(1230,676,'GND',20,color=COLORS['GND'],weight='bold')
    draw.text(445,740,'5 V × 2 kΩ / (1 kΩ + 2 kΩ) ≈ 3,33 V',25,weight='bold')
    draw.text(75,800,'Widerstände erkennen',25,weight='bold')
    draw.text(75,840,'1 kΩ = 1000 Ω',21,weight='bold')
    draw.text(440,840,'4 Ringe: Braun · Schwarz · Rot · Gold',20)
    draw.text(440,877,'5 Ringe: Braun · Schwarz · Schwarz · Braun · Braun',20)
    draw.text(75,925,'2 kΩ = 2000 Ω',21,weight='bold')
    draw.text(440,925,'4 Ringe: Rot · Schwarz · Rot · Gold',20)
    draw.text(440,962,'5 Ringe: Rot · Schwarz · Schwarz · Braun · Braun',20)
    draw.text(75,1020,'Gold: ±5 % · letzter brauner Ring: ±1 % · Im Zweifel den Widerstand mit einem Multimeter messen.',17,'#536271')
    return draw


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DESTINATION)
    parser.add_argument('--png',action='store_true',help='Zusätzlich PNG mit CairoSVG rendern')
    args=parser.parse_args()
    for family in PINS:
        overview(family).save(args.output,family+'-breadboard',args.png)
    divider_detail().save(args.output,'spannungsteiler-detail',args.png)
    print('Drei eigene SVG-Verdrahtungsbilder erstellt'+(' und als PNG gerendert.' if args.png else '.'))


if __name__=='__main__':
    main()
