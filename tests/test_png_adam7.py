"""Independent Adam7 fixtures use the spec's 8x8 pass map, not decoder strides."""
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_github_archive import ArchivePlanError, _decode_png

PASS_MAP = (
    (1,6,4,6,2,6,4,6), (7,7,7,7,7,7,7,7),
    (5,6,5,6,5,6,5,6), (7,7,7,7,7,7,7,7),
    (3,6,4,6,3,6,4,6), (7,7,7,7,7,7,7,7),
    (5,6,5,6,5,6,5,6), (7,7,7,7,7,7,7,7),
)

def chunk(kind, payload):
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)

def packed(samples, depth):
    if depth == 16:
        return b''.join(struct.pack('>H', n) for n in samples)
    if depth == 8:
        return bytes(samples)
    result=bytearray((len(samples)*depth+7)//8)
    for i,n in enumerate(samples):
        result[i*depth//8] |= n << (8-depth-(i*depth)%8)
    return bytes(result)

def fixture(width, height, depth, color, filter_type=0, mutation=None):
    channels={0:1,2:3,3:1,4:2,6:4}[color]
    max_value=(1<<depth)-1
    pixels=[[[((x*3+y*7+c*11)%(max_value+1)) for c in range(channels)] for x in range(width)] for y in range(height)]
    if color==3:
        pixels=[[[p[0]%min(1<<depth,16)] for p in row] for row in pixels]
    expected=tuple(packed([n for p in row for n in p],depth) for row in pixels)
    stream=bytearray()
    for pass_number in range(1,8):
        previous=None
        for y in range(height):
            xs=[x for x in range(width) if PASS_MAP[y%8][x%8]==pass_number]
            if not xs: continue
            raw=packed([n for x in xs for n in pixels[y][x]],depth)
            previous=previous or bytes(len(raw))
            bpp=max(1,(channels*depth+7)//8)
            filtered=bytearray()
            for i,v in enumerate(raw):
                a=raw[i-bpp] if i>=bpp else 0
                b=previous[i]
                c=previous[i-bpp] if i>=bpp else 0
                predictors=(0,a,b,(a+b)//2,min((a,b,c),key=lambda n:abs((a+b-c)-n)))
                filtered.append((v-predictors[filter_type])&255)
            stream.append(filter_type)
            stream.extend(filtered)
            previous=raw
    if mutation: stream=mutation(stream)
    ancillary=chunk(b'PLTE', bytes(range(3*min(1<<depth,16)))) if color==3 else b''
    data=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,depth,color,0,0,1))
          +ancillary+chunk(b'IDAT',zlib.compress(stream))+chunk(b'IEND',b''))
    return data,expected

class Adam7Tests(unittest.TestCase):
    def decode(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sample.png';path.write_bytes(data)
            return _decode_png(path)

    def test_all_legal_depths_and_colors_reconstruct_original_samples(self):
        for color,depths in {0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}.items():
            for depth in depths:
                with self.subTest(color=color,depth=depth):
                    data,expected=fixture(11,9,depth,color)
                    result=self.decode(data)
                    self.assertEqual(result.rows,expected)
                    self.assertEqual((result.width,result.height,result.color_type,result.bit_depth),(11,9,color,depth))

    def test_filters_restart_for_each_pass_and_empty_passes_have_no_bytes(self):
        for size in ((1,1),(1,9),(9,1),(3,5),(11,9)):
            for filter_type in range(5):
                with self.subTest(size=size,filter=filter_type):
                    data,expected=fixture(*size,16,6,filter_type)
                    self.assertEqual(self.decode(data).rows,expected)

    def test_rejects_bad_later_pass_filter_missing_extra_or_trailing_data(self):
        def bad_filter(stream):
            stream[-(11*4+1)]=5
            return stream
        for mutate in (lambda b:b[:-1],lambda b:b+b'\x00',bad_filter):
            data,_=fixture(11,9,8,6,mutation=mutate)
            with self.assertRaises(ArchivePlanError):self.decode(data)
        data,_=fixture(11,9,8,6)
        with self.assertRaises(ArchivePlanError):self.decode(data+b'trailing')
        corrupted=bytearray(data);corrupted[-8]^=1
        with self.assertRaises(ArchivePlanError):self.decode(corrupted)

    def test_rejects_palette_index_outside_declared_palette(self):
        data,_=fixture(11,9,8,3)
        data=data.replace(chunk(b'PLTE',bytes(range(48))),chunk(b'PLTE',b'\x00\x00\x00'))
        with self.assertRaises(ArchivePlanError):self.decode(data)

if __name__=='__main__':unittest.main()
