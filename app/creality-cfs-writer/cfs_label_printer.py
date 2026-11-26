# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""PC-only T50M Pro printing. Never accesses Creality printers or profiles."""
import asyncio
import queue
import socket
import sys
import threading
import time
from cfs_label_protocol import (FrameParser,command_frame,status,media,validate_media,encode_page,data_frames,
    CMD_STATUS,CMD_CHECK,CMD_START,CMD_STOP,CMD_NAME,CMD_MEDIA,CMD_CHUNK,CMD_BUFFER)


class ClassicTransport:
    acks=True
    def __init__(self,address):
        self.socket=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM)
        try:self.socket.settimeout(8);self.socket.connect((address,1));self.socket.settimeout(.3)
        except Exception:self.socket.close();raise
    def write(self,data):self.socket.sendall(data)
    def read(self):
        try:
            data=self.socket.recv(2048)
            if not data:raise ConnectionError('Bluetooth-Verbindung wurde getrennt.')
            return data
        except socket.timeout:return b''
    def close(self):self.socket.close()


class BleTransport:
    acks=False
    def __init__(self,address):
        self.loop=asyncio.new_event_loop();self.incoming=queue.Queue()
        self.thread=threading.Thread(target=self.loop.run_forever,daemon=True,name='cfs-label-ble');self.thread.start()
        try:self.call(self.open(address),25)
        except Exception:self.close();raise
    def call(self,coro,timeout=10):
        future=asyncio.run_coroutine_threadsafe(coro,self.loop)
        try:return future.result(timeout)
        except Exception:future.cancel();raise
    async def open(self,address):
        from bleak import BleakClient
        self.client=BleakClient(address,timeout=15)
        await self.client.connect()
        pairs=(('0000ffe9-0000-1000-8000-00805f9b34fb','0000ffe1-0000-1000-8000-00805f9b34fb'),
            ('0000c302-0000-1000-8000-00805f9b34fb','0000c305-0000-1000-8000-00805f9b34fb'),
            ('0000ff02-0000-1000-8000-00805f9b34fb','0000ff01-0000-1000-8000-00805f9b34fb'),
            ('00002af1-0000-1000-8000-00805f9b34fb','00002af0-0000-1000-8000-00805f9b34fb'))
        for w,n in pairs:
            char=self.client.services.get_characteristic(w)
            if char and self.client.services.get_characteristic(n):
                self.char=char;self.response='write' in char.properties
                self.piece=128 if self.response else min(128,char.max_write_without_response_size)
                await self.client.start_notify(n,lambda _,data:self.incoming.put(bytes(data)));return
        raise ValueError('Kein unterstützter T50-Bluetooth-Dienst gefunden.')
    async def send(self,data):
        for offset in range(0,len(data),self.piece):
            await self.client.write_gatt_char(self.char,data[offset:offset+self.piece],response=self.response)
            if not self.response:await asyncio.sleep(.01)
    def write(self,data):self.call(self.send(data))
    def read(self):
        if not self.client.is_connected:raise ConnectionError('Bluetooth-Verbindung wurde getrennt.')
        try:return self.incoming.get(timeout=.3)
        except queue.Empty:return b''
    def close(self):
        try:
            if getattr(self,'client',None):self.call(self.client.disconnect(),5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop);self.thread.join(2)


def scan():
    if sys.platform.startswith('linux'):
        import shutil,subprocess
        if shutil.which('bluetoothctl'):
            subprocess.run(['bluetoothctl','--timeout','7','scan','on'],capture_output=True,timeout=12)
            result=subprocess.run(['bluetoothctl','devices'],capture_output=True,text=True,timeout=5)
            if result.returncode:raise ValueError('Bluetooth nicht verfügbar. Stick und Betriebssystemeinstellungen prüfen.')
            devices=[]
            for line in result.stdout.splitlines():
                parts=line.split(' ',2)
                if len(parts)==3 and parts[0]=='Device' and parts[2].startswith('T0170'):devices.append({'name':parts[2],'address':parts[1]})
            return devices
    try:from bleak import BleakScanner
    except ImportError:raise ValueError('Bluetooth-Suche benötigt das optionale Paket bleak. Über „Bluetooth einrichten“ installieren; unter Linux kann die Geräteadresse auch direkt eingegeben werden.')
    async def discover():
        found=await BleakScanner.discover(timeout=7,return_adv=True)
        return [{'name':adv.local_name or device.name or '', 'address':device.address}
            for device,adv in found.values() if (adv.local_name or device.name or '').startswith('T0170')]
    return asyncio.run(discover())


class LabelPrinter:
    def __init__(self,transport_factory=None):
        self.transport=None;self.parser=FrameParser();self.frames=[];self.cancel=threading.Event()
        self.lock=threading.Lock();self.info=None;self.transport_factory=transport_factory
    def connect(self,address,mode='Automatisch'):
        with self.lock:
            self.disconnect();self.cancel.clear()
            if not address.strip():raise ValueError('Etikettendrucker auswählen oder Geräteadresse eingeben.')
            factory=self.transport_factory or (ClassicTransport if mode!='Bluetooth LE' and sys.platform.startswith('linux') else BleTransport)
            try:
                self.transport=factory(address.strip());self.parser=FrameParser();self.frames=[]
                info=self.refresh();name=self.command(CMD_NAME)[22:].split(b'\0')[0].decode('ascii','replace')
                if not name.startswith('T50'):raise ValueError('Dieses Gerät meldet keinen unterstützten T50-Drucker.')
                info.update(name=name,address=address,transport='Bluetooth Classic' if self.transport.acks else 'Bluetooth LE');self.info=info;return info
            except Exception:self.disconnect();raise
    def disconnect(self):
        if self.transport:
            try:self.transport.close()
            finally:self.transport=None;self.info=None
    def check_cancel(self):
        if self.cancel.is_set():raise ValueError('Etikettendruck abgebrochen.')
    def receive(self,cmd,timeout=3):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.check_cancel()
            while self.frames:
                frame=self.frames.pop(0)
                if cmd is None or frame[7]==cmd:return frame
            self.frames.extend(self.parser.feed(self.transport.read()))
        raise TimeoutError('Etikettendrucker antwortet nicht rechtzeitig. Verbindung und Statusleuchte prüfen.')
    def command(self,cmd,a=0,b=0):
        if self.transport is None:raise ValueError('Kein Etikettendrucker verbunden.')
        # Only harmless read queries may be retried. Never replay a print command.
        for attempt in range(2 if cmd in (CMD_STATUS,CMD_NAME,CMD_MEDIA) else 1):
            self.frames.clear();self.transport.write(command_frame(cmd,a,b))
            try:return self.receive(cmd)
            except TimeoutError:
                if attempt or cmd not in (CMD_STATUS,CMD_NAME,CMD_MEDIA):raise
    def refresh(self):
        result={'status':status(self.command(CMD_STATUS)),'media':media(self.command(CMD_MEDIA))}
        self.info={**(self.info or {}),**result};return self.info
    def printable(self,s):
        if s['errors']:raise ValueError(' '.join(s['errors']))
    def wait_status(self,predicate,timeout):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.check_cancel();s=status(self.command(CMD_STATUS));self.printable(s)
            if predicate(s):return s
            time.sleep(.1)
        raise TimeoutError('Druckerzustand wurde nicht rechtzeitig erreicht.')
    def print_images(self,images,*,copies=1,density=4,progress=lambda update:None):
        with self.lock:
            if not images or not 1<=copies<=20 or len(images)*copies>100:raise ValueError('Bitte 1 bis 100 Etiketten wählen; höchstens 20 Kopien.')
            self.check_cancel();total=len(images)*copies;sequence=[]
            for index,png in enumerate(images*copies):
                self.check_cancel();progress({'phase':'Etiketten vorbereiten','current':index,'total':total})
                sequence.append(encode_page(png,density=density,print_end=index==total-1))
            info=self.refresh();validate_media(info['media']);self.printable(info['status'])
            if info['status']['printing'] or info['status']['busy']:raise ValueError('Etikettendrucker ist noch beschäftigt.')
            self.command(CMD_CHECK);self.wait_status(lambda s:not s['busy'] and not s['printing'],8)
            attempted=False
            try:
                self.check_cancel();attempted=True;self.command(CMD_START)
                self.wait_status(lambda s:s['printing'],8)
                for index,page in enumerate(sequence):
                    progress({'phase':'Etiketten übertragen','current':index,'total':total})
                    for chunk in page['chunks']:
                        s=self.wait_status(lambda s:not s['buffer_full'],15)
                        if not s['printing'] and not s['busy']:raise ValueError('Druck wurde am Gerät gestoppt.')
                        frames=data_frames(chunk);self.command(CMD_CHUNK,512,len(frames))
                        for number,frame in enumerate(frames):
                            self.check_cancel();self.frames.clear()
                            for offset in range(0,512,128):
                                self.check_cancel();self.transport.write(frame[offset:offset+128]);time.sleep(.01)
                            if self.transport.acks and number<len(frames)-1:self.receive(None)
                        self.command(CMD_BUFFER,len(chunk),page['speed'])
                progress({'phase':'Etiketten werden gedruckt','current':total,'total':total})
                final=self.wait_status(lambda s:not s['printing'] and not s['busy'],120)
                self.info={**info,'status':final};return {'count':total,'status':final}
            except Exception as error:
                if attempted:
                    cancelled=self.cancel.is_set();self.cancel.clear()
                    try:self.command(CMD_STOP)
                    except Exception:pass
                    if cancelled:self.cancel.set()
                    raise ValueError(str(error)+' Der Auftrag wurde nicht als abgeschlossen bestätigt. Es können bereits Etiketten gedruckt sein; nicht automatisch erneut senden.') from error
                raise
