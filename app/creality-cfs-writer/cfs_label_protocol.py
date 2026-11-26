# SPDX-License-Identifier: MIT AND PolyForm-Noncommercial-1.0.0
"""T50M Pro monochrome print codec. No device or network access.

Framing/raster adapted from Katasymbol Web (MIT), commit b3799ffb.
See label-assets/KATASYMBOL-PROTOCOL-LICENSE.txt and QUELLEN.md.
Compression uses the public liblzma LZMA1EXT ABI, with no end marker.
"""
import ctypes as C
import ctypes.util
import io
import os
from functools import lru_cache
from pathlib import Path
import sys

CMD_STATUS=0x11;CMD_CHECK=0x12;CMD_START=0x13;CMD_STOP=0x14
CMD_NAME=0x16;CMD_MEDIA=0x30;CMD_CHUNK=0x5c;CMD_BUFFER=0x10


def command_frame(command,parameter=0,extra=0):
    if command not in (CMD_STATUS,CMD_CHECK,CMD_START,CMD_STOP,CMD_NAME,CMD_MEDIA,CMD_CHUNK,CMD_BUFFER):
        raise ValueError('Nicht freigegebener Etikettendrucker-Befehl.')
    if not 0<=parameter<=65535 or not 0<=extra<=65535:raise ValueError('Ungültiger Druckparameter.')
    result=bytearray.fromhex('7e5a0c001001aa000000000100000000')
    result[7]=command;result[12:14]=parameter.to_bytes(2,'little');result[14:16]=extra.to_bytes(2,'little')
    result[8:10]=(sum(result[10:])&65535).to_bytes(2,'little');return bytes(result)


class FrameParser:
    def __init__(self):self.pending=bytearray()
    def feed(self,data):
        self.pending.extend(data);frames=[]
        while len(self.pending)>=4:
            pos=self.pending.find(b'\x7e\x5a')
            if pos<0:self.pending=self.pending[-1:] if self.pending[-1:]==b'\x7e' else bytearray();break
            if pos:del self.pending[:pos]
            if len(self.pending)<4:break
            size=int.from_bytes(self.pending[2:4],'little')+4
            if not 8<=size<=2048:del self.pending[0];continue
            if len(self.pending)<size:break
            frame=bytes(self.pending[:size]);del self.pending[:size]
            if frame[4]!=0x10 or frame[6]!=0x55:continue
            if size>=10 and int.from_bytes(frame[8:10],'little')!=(sum(frame[10:])&65535):continue
            frames.append(frame)
        if len(self.pending)>4096:self.pending.clear()
        return frames


def status(frame):
    if len(frame)<22:raise ValueError('Unvollständige Druckerstatusantwort.')
    b=frame[14:22];errors=[];warnings=[]
    for on,message in ((b[1]&8,'Druckkopf ist zu heiß.'),(b[2]&8,'Deckel des Etikettendruckers ist offen.'),
        (b[3]&1,'Keine Etikettenrolle eingesetzt.'),(b[0]&2,'Etikettenrolle kann nicht gelesen werden.'),
        (b[0]&4,'Etikettenrolle ist leer.'),(b[0]&8,'Etikettenformat wird nicht erkannt.'),(b[0]&0x10,'Etikettenrolle sitzt nicht richtig. Rolle neu einlegen und am Gerät ausrichten.'),(b[0]&0x20,'Restliche Etiketten und Rollenlage prüfen.')):
        if on:errors.append(message)
    if b[0]&0x40:warnings.append('Akku schwach; Drucker laden.')
    return {'printing':bool(b[2]&0x40),'busy':bool(b[1]&4),'buffer_full':bool(b[0]&1),
        'pages':int.from_bytes(b[4:6],'little'),'charging':bool(b[3]&0x80),'usb_attached':bool(b[2]&0x10),
        'errors':errors,'warnings':warnings,'registers':b[:4].hex()}


def media(frame):
    if len(frame)<43:raise ValueError('Unvollständige Etikettenrollen-Antwort.')
    def at(offset):return frame[offset+21]
    return {'label_id':at(16)|(at(17)<<8),'paper_type':at(18),'length_mm':at(19),'width_mm':at(20),
        'gap_mm':min(at(21),3) if at(21)>8 else at(21)}


def validate_media(info):
    if (info.get('length_mm'),info.get('width_mm'))!=(40,30) or info.get('paper_type')!=1:
        raise ValueError('Direktdruck benötigt erkannte 40 × 30 mm Einzeletiketten. Eingelegt: '+str(info.get('length_mm','?'))+' × '+str(info.get('width_mm','?'))+' mm.')


class _OptionsPrefix(C.Structure):
    _fields_=[('dict_size',C.c_uint32),('preset_dict',C.c_void_p),('preset_dict_size',C.c_uint32),
        ('lc',C.c_uint32),('lp',C.c_uint32),('pb',C.c_uint32),('mode',C.c_int),('nice_len',C.c_uint32),
        ('mf',C.c_int),('depth',C.c_uint32),('ext_flags',C.c_uint32)]
class _Filter(C.Structure):_fields_=[('id',C.c_uint64),('options',C.c_void_p)]


@lru_cache(maxsize=1)
def compression_library():
    configured=os.environ.get('CFS_LIBLZMA','').strip()
    if configured and (not Path(configured).is_absolute() or not Path(configured).is_file()):
        raise ValueError('CFS_LIBLZMA muss der absolute Pfad einer vorhandenen liblzma-Bibliothek sein.')
    names=[configured,ctypes.util.find_library('lzma')]
    if sys.platform=='win32':
        directories=[Path(sys.prefix)/'DLLs',Path(sys.prefix)/'Library/bin',Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'Library/bin']
        names.extend(str(folder/name) for folder in directories for name in ('liblzma.dll','lzma.dll','liblzma-5.dll') if (folder/name).is_file())
    elif sys.platform=='darwin':
        names.extend(['/opt/homebrew/opt/xz/lib/liblzma.dylib','/usr/local/opt/xz/lib/liblzma.dylib','/usr/lib/liblzma.dylib'])
    else:
        names.append('liblzma.so.5')
    for name in names:
        if not name:continue
        try:
            lib=C.CDLL(name)
            lib.lzma_lzma_preset.argtypes=[C.c_void_p,C.c_uint32];lib.lzma_lzma_preset.restype=C.c_uint32
            lib.lzma_raw_buffer_encode.argtypes=[C.POINTER(_Filter),C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.POINTER(C.c_size_t),C.c_size_t]
            lib.lzma_raw_buffer_encode.restype=C.c_int
            return lib
        except (OSError,AttributeError):
            if name==configured:
                raise ValueError('Die über CFS_LIBLZMA gewählte Bibliothek ist nicht kompatibel. Architektur und XZ/liblzma-Version prüfen.') from None
    raise ValueError('Die liblzma-Bibliothek für den Direktdruck fehlt. Unter Mint liblzma5 installieren, unter macOS XZ/liblzma. Unter Windows den absoluten DLL-Pfad über CFS_LIBLZMA angeben. Siehe docs/INSTALLATION.md.')


def compress(raw):
    if not raw or len(raw)>8*4096 or len(raw)%4096:raise ValueError('Ungültiger Druckpuffer.')
    lib=compression_library();options=C.create_string_buffer(512)
    if lib.lzma_lzma_preset(options,6):raise ValueError('Druckkompression konnte nicht eingerichtet werden.')
    prefix=_OptionsPrefix.from_buffer(options);prefix.dict_size=8192;prefix.lc=3;prefix.lp=0;prefix.pb=2;prefix.nice_len=128;prefix.ext_flags=0
    filters=(_Filter*2)(_Filter(0x4000000000000002,C.cast(options,C.c_void_p)),_Filter(0xffffffffffffffff,None))
    output=C.create_string_buffer(len(raw)*2+100);position=C.c_size_t()
    result=lib.lzma_raw_buffer_encode(filters,None,raw,len(raw),output,C.byref(position),len(output))
    if result:raise ValueError('liblzma unterstützt den benötigten Druckmodus nicht (LZMA1EXT, Fehler '+str(result)+'). PNG-Export bleibt verfügbar.')
    return b'\x5d'+(8192).to_bytes(4,'little')+len(raw).to_bytes(8,'little')+output.raw[:position.value]


def raster_buffers(png,*,density=4,paper_type=1,print_end=True):
    from PIL import Image
    if not 1<=density<=9 or paper_type!=1:raise ValueError('Ungültige Etikettendruck-Einstellung.')
    image=Image.open(io.BytesIO(png));image.load()
    if image.size!=(320,240):raise ValueError('Direktdruck benötigt ein 40 × 30 mm Bild mit 320 × 240 Pixeln (203 dpi).')
    image=image.convert('L').transpose(Image.Transpose.ROTATE_90)
    cols,rows=image.size;bpc=(rows+7)//8;pixels=image.load();packed=bytearray(cols*bpc)
    for x in range(cols):
        for y in range(rows):
            if pixels[x,y]<180:packed[x*bpc+y//8]|=1<<(y%8)
    max_cols=(4096-22)//bpc;count=(cols+max_cols-1)//max_cols;buffers=[]
    for index in range(count):
        n=min(max_cols,cols-index*max_cols);last=index==count-1;buffer=bytearray(4096)
        buffer[2]=(2 if index==0 else 0)|(4 if last else 0)|(8 if last and print_end else 0)
        buffer[3]=(paper_type<<6)|(density<<2);buffer[4:6]=n.to_bytes(2,'little');buffer[6]=bpc;buffer[8]=1;buffer[10]=1
        buffer[14:14+n*bpc]=packed[index*max_cols*bpc:(index*max_cols+n)*bpc]
        check=sum(buffer[2:14])+sum(buffer[(k+1)*256-1] for k in range((14+n*bpc)//256))
        buffer[0:2]=(check&65535).to_bytes(2,'little');buffers.append(bytes(buffer))
    return buffers


def encode_page(png,*,density=4,print_end=True):
    buffers=raster_buffers(png,density=density,print_end=print_end);chunks=[];index=0;first_n=0
    while index<len(buffers):
        n=min(8,len(buffers)-index);chunk=compress(b''.join(buffers[index:index+n]))
        while len(chunk)>4096 and n>1:n-=1;chunk=compress(b''.join(buffers[index:index+n]))
        if len(chunk)>4096:raise ValueError('Etikett ist für einen sicheren Druckpuffer zu komplex.')
        if not chunks:first_n=n
        chunks.append(chunk);index+=n
    return {'chunks':chunks,'speed':51 if first_n==len(buffers) else first_n*6+3,'buffers':len(buffers)}


def data_frames(chunk):
    if not 1<=len(chunk)<=4096:raise ValueError('Ungültige komprimierte Etikettendaten.')
    count=(len(chunk)+499)//500;frames=[]
    for index in range(count):
        frame=bytearray(512);frame[:8]=b'\x7e\x5a\xfc\x01\x10\x02\xaa\xbb';frame[10]=index;frame[11]=count
        data=chunk[index*500:(index+1)*500];frame[12:12+len(data)]=data
        frame[8:10]=(sum(frame[10:])&65535).to_bytes(2,'little');frames.append(bytes(frame))
    return frames
