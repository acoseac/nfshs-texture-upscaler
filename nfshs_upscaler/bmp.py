"""Minimal BMP reading and writing in the exact layouts FSHTool produces and expects."""
import struct

import numpy as np


def _header(path):
    data = open(path, 'rb').read()
    if data[:2] != b'BM':
        raise ValueError(f'{path} is not a BMP')
    off, = struct.unpack_from('<I', data, 10)
    hsize, w, h_raw, _, bpp = struct.unpack_from('<IiiHH', data, 14)
    return data, off, 14 + hsize, w, abs(h_raw), h_raw > 0, bpp


def read8(path):
    """Returns (indices HxW uint8, palette 256x4 as B,G,R,reserved). FSHTool keeps palette alpha in 'reserved'."""
    data, off, pal_off, w, h, bottom_up, bpp = _header(path)
    if bpp != 8:
        raise ValueError(f'{path} is not 8-bit')
    stride = (w + 3) // 4 * 4
    rows = np.frombuffer(data, np.uint8, stride * h, off).reshape(h, stride)[:, :w]
    pal = np.zeros((256, 4), np.uint8)
    raw = np.frombuffer(data, np.uint8, min(1024, off - pal_off), pal_off)
    pal.flat[:raw.size] = raw
    return (rows[::-1] if bottom_up else rows).copy(), pal


def read24(path):
    """Returns RGB HxWx3 uint8."""
    data, off, _, w, h, bottom_up, bpp = _header(path)
    if bpp != 24:
        raise ValueError(f'{path} is not 24-bit')
    stride = (w * 3 + 3) // 4 * 4
    rows = np.frombuffer(data, np.uint8, stride * h, off).reshape(h, stride)[:, :w * 3].reshape(h, w, 3)
    rows = rows[::-1] if bottom_up else rows
    return rows[:, :, ::-1].copy()


def _write(path, w, h, bpp, palette_bytes, pixel_rows):
    stride = (w * bpp // 8 + 3) // 4 * 4
    off = 54 + len(palette_bytes)
    body = bytearray(stride * h)
    for y, row in enumerate(pixel_rows[::-1]):  # bottom-up
        b = row.tobytes()
        body[y * stride:y * stride + len(b)] = b
    head = b'BM' + struct.pack('<IHHI', off + len(body), 0, 0, off)
    info = struct.pack('<IiiHHIIiiII', 40, w, h, 1, bpp, 0, len(body), 0, 0, 256 if bpp == 8 else 0, 0)
    with open(path, 'wb') as f:
        f.write(head + info + palette_bytes + body)


def write8pal(path, idx, pal_rgb, pal_alpha):
    """8-bit BMP with a full 256-entry palette; palette alpha goes in the reserved byte, as FSHTool reads it."""
    pal = np.zeros((256, 4), np.uint8)
    pal[:, 0], pal[:, 1], pal[:, 2], pal[:, 3] = pal_rgb[:, 2], pal_rgb[:, 1], pal_rgb[:, 0], pal_alpha
    _write(path, idx.shape[1], idx.shape[0], 8, pal.tobytes(), idx.astype(np.uint8))


def write8gray(path, a):
    ramp = np.arange(256, dtype=np.uint8)
    pal = np.stack([ramp, ramp, ramp, np.zeros(256, np.uint8)], 1)
    _write(path, a.shape[1], a.shape[0], 8, pal.tobytes(), a.astype(np.uint8))


def write24(path, rgb):
    _write(path, rgb.shape[1], rgb.shape[0], 24, b'', rgb[:, :, ::-1].astype(np.uint8))
