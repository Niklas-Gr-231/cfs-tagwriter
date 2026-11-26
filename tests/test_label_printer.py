# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import io,lzma,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/creality-cfs-writer'))
import cfs_label_protocol as p
from cfs_label_printer import LabelPrinter
from PIL import Image


def reply(cmd,registers=b'\0'*8,tail=b''):
    result=bytearray.fromhex('7e5a160010035511000000000000')+registers+tail
    result[2:4]=(len(result)-4).to_bytes(2,'little');result[7]=cmd
    result[8:10]=sum(result[10:]).to_bytes(2,'little');return bytes(result)

def png():
    im=Image.new('L',(320,240),255);im.putpixel((0,0),0);b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()

class Fake:
    acks=True
    def __init__(self,address):self.queue=[];self.commands=[];self.printing=False;self.closed=False;self.fail_buffer=False;self.cover=False
    def close(self):self.closed=True
    def write(self,data):
        if len(data)!=16:return
        cmd=data[7];self.commands.append(cmd)
        if cmd==p.CMD_START:self.printing=True
        if cmd in (p.CMD_BUFFER,p.CMD_STOP):self.printing=False
        regs=bytearray(8);regs[2]=(64 if self.printing else 0)|(8 if self.cover else 0)
        r=reply(cmd,bytes(regs))
        if cmd==p.CMD_NAME:r=reply(cmd,tail=b'T50ProJ\0')
        if cmd==p.CMD_MEDIA:
            tail=bytearray(39);tail[15:22]=bytes([0x79,0x15,1,40,30,3,0]);r=reply(cmd,tail=tail)
        if cmd==p.CMD_BUFFER and self.fail_buffer:raise ConnectionError('lost')
        self.queue.append(r)
    def read(self):
        if self.queue:return self.queue.pop(0)
        return b''

def native_compression_available():
    try:
        p.compression_library()
        return True
    except ValueError:
        return False

NATIVE_COMPRESSION = native_compression_available()

class Codec(unittest.TestCase):
    def test_live_status_before_after_reseat(self):
        red=bytes.fromhex('7e5a16001003551137010000000010001080000000004e013810')
        green=bytes.fromhex('7e5a160010035511af000000000000001000000000004d014110')
        self.assertTrue(p.status(red)['errors']);self.assertFalse(p.status(green)['errors'])
    def test_fragmented_checked_frames(self):
        raw=reply(p.CMD_STATUS);parser=p.FrameParser();self.assertEqual(parser.feed(b'junk'+raw[:7]),[]);self.assertEqual(parser.feed(raw[7:]+raw),[raw,raw])
        bad=bytearray(raw);bad[-1]^=1;self.assertEqual(parser.feed(bad),[])
    def test_media(self):
        raw=bytes.fromhex('7e5a390010035530200a0000000010001080000000001dab5ea0131080548ff49024d3888f791501281e0304010000a406b00419081209181000000300')
        info=p.media(raw);self.assertEqual((info['label_id'],info['length_mm'],info['width_mm']),(5497,40,30));p.validate_media(info)
        with self.assertRaises(ValueError):p.validate_media(dict(info,width_mm=25))
    def test_safe_opcodes_and_exact_command(self):
        self.assertEqual(p.command_frame(p.CMD_STATUS).hex(),'7e5a0c001001aa110100000100000000')
        for unsafe in (0x5d,0xc6,0xc5):
            with self.assertRaises(ValueError):p.command_frame(unsafe)
    def test_rotated_raster_and_flags(self):
        buffers=p.raster_buffers(png());self.assertEqual(len(buffers),3)
        self.assertEqual(buffers[0][2],2);self.assertEqual(buffers[-1][2],12)
        self.assertEqual(buffers[0][6],40)
        # Source top-left becomes first column, final row after CCW rotation.
        self.assertEqual(buffers[0][14+39],128)
        self.assertEqual(sum(b[2]&8!=0 for b in buffers),1)
        self.assertFalse(p.raster_buffers(png(),print_end=False)[-1][2]&8)
        for b in buffers:
            used=14+int.from_bytes(b[4:6],'little')*b[6]
            self.assertEqual(int.from_bytes(b[:2],'little'),sum(b[2:14])+sum(b[(k+1)*256-1] for k in range(used//256)))
    @unittest.skipUnless(NATIVE_COMPRESSION, "Optional liblzma not installed")
    def test_no_end_marker_compression_and_data_frames(self):
        raw=b''.join(p.raster_buffers(png()));encoded=p.compress(raw)
        self.assertEqual(lzma.decompress(encoded,format=lzma.FORMAT_ALONE),raw)
        # Known-size ALONE stream has no trailing end marker: raw decoder returns bytes, not eof.
        decoder=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=[{'id':lzma.FILTER_LZMA1,'dict_size':8192,'lc':3,'lp':0,'pb':2}])
        self.assertEqual(decoder.decompress(encoded[13:]),raw);self.assertFalse(decoder.eof)
        frames=p.data_frames(encoded);self.assertEqual(len(frames),(len(encoded)+499)//500)
        for index,frame in enumerate(frames):self.assertEqual(frame[10:12],bytes((index,len(frames))));self.assertEqual(int.from_bytes(frame[8:10],'little'),sum(frame[10:]))

@unittest.skipUnless(NATIVE_COMPRESSION, "Optional liblzma not installed")
class Jobs(unittest.TestCase):
    def setUp(self):self.printer=LabelPrinter(Fake);self.printer.connect('test');self.transport=self.printer.transport
    def tearDown(self):self.printer.disconnect()
    def test_one_controlled_start_and_success(self):
        with patch('cfs_label_printer.time.sleep'):result=self.printer.print_images([png()])
        self.assertEqual(result['count'],1);self.assertEqual(self.transport.commands.count(p.CMD_START),1)
    def test_source_errors_block_before_start(self):
        self.transport.cover=True
        with self.assertRaisesRegex(ValueError,'Deckel'):self.printer.print_images([png()])
        self.assertNotIn(p.CMD_START,self.transport.commands)
    def test_uncertain_transfer_never_replays_print(self):
        self.transport.fail_buffer=True
        with patch('cfs_label_printer.time.sleep'),self.assertRaisesRegex(ValueError,'nicht als abgeschlossen'):self.printer.print_images([png()])
        self.assertEqual(self.transport.commands.count(p.CMD_START),1);self.assertIn(p.CMD_STOP,self.transport.commands)
    def test_completion_timeout_is_not_success(self):
        actual=self.printer.wait_status
        def wait(predicate,timeout):
            if timeout==120:raise TimeoutError('timeout')
            return actual(predicate,timeout)
        with patch.object(self.printer,'wait_status',side_effect=wait),patch('cfs_label_printer.time.sleep'),self.assertRaisesRegex(ValueError,'nicht als abgeschlossen'):self.printer.print_images([png()])
        self.assertIn(p.CMD_STOP,self.transport.commands)
    def test_cancel_before_start_is_preserved(self):
        self.printer.cancel.set()
        with self.assertRaisesRegex(ValueError,'abgebrochen'):self.printer.print_images([png()])
        self.assertNotIn(p.CMD_START,self.transport.commands)
    def test_limit_no_start(self):
        with self.assertRaises(ValueError):self.printer.print_images([png()],copies=21)
        self.assertNotIn(p.CMD_START,self.transport.commands)

if __name__=='__main__':unittest.main()
