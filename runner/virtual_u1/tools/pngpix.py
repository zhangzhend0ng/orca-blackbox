"""pngpix.py — decode a non-interlaced 8-bit PNG (what CDP screenshots are)
into RGB rows, stdlib only. Just enough for pixel assertions on page regions.

    rows = decode(png_bytes)      # list of bytearrays, 3 bytes per pixel
    r, g, b = rows[y][x * 3:x * 3 + 3]
"""
import struct
import zlib


def _unfilter(raw, w, h, bpp):
    stride = w * bpp
    rows = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        ft = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:                                    # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:                                  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:                                  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:                                  # Paeth
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return rows


def decode(png):
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat = 8, b""
    while pos < len(png):
        n, kind = struct.unpack(">I4s", png[pos:pos + 8])
        data = png[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            idat += data
        pos += 12 + n
    assert depth == 8 and interlace == 0, "unsupported PNG (depth %d interlace %d)" % (depth, interlace)
    assert ctype in (2, 6), "unsupported PNG color type %d" % ctype
    bpp = 3 if ctype == 2 else 4
    rows = _unfilter(zlib.decompress(idat), w, h, bpp)
    if bpp == 4:
        rows = [bytearray(v for i, v in enumerate(r) if i % 4 != 3) for r in rows]
    return rows
