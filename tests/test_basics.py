"""Tests that need no game files, FSHTool or Real-ESRGAN. Run with: python -m unittest"""
import os
import tempfile
import unittest

import numpy as np

from nfshs_upscaler import bmp
from nfshs_upscaler.fsh import Index
from nfshs_upscaler.imaging import bleed, judge, quantize

rng = np.random.default_rng(1)


class Bmp(unittest.TestCase):
    def test_8bit_round_trip_keeps_palette_alpha(self):
        idx = rng.integers(0, 256, (17, 13), dtype=np.uint8)  # odd width tests row padding
        pal = rng.integers(0, 256, (256, 3), dtype=np.uint8)
        alpha = np.full(256, 255, np.uint8); alpha[255] = 0
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.BMP')
            bmp.write8pal(p, idx, pal, alpha)
            idx2, pal2 = bmp.read8(p)
        self.assertTrue((idx2 == idx).all())
        self.assertTrue((pal2[:, 2::-1] == pal).all())
        self.assertTrue((pal2[:, 3] == alpha).all())

    def test_24bit_round_trip(self):
        rgb = rng.integers(0, 256, (9, 7, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.BMP')
            bmp.write24(p, rgb)
            self.assertTrue((bmp.read24(p) == rgb).all())


class Quantize(unittest.TestCase):
    def test_few_colours_come_back_exactly(self):
        colours = np.array([[200, 40, 40], [40, 200, 40], [40, 40, 200], [248, 248, 248]], np.uint8)
        rgb = colours[rng.integers(0, 4, (32, 32))]
        idx, pal = quantize(rgb, np.ones((32, 32), bool), False)
        self.assertLessEqual(np.abs(pal[idx].astype(int) - rgb).max(), 0)

    def test_transparent_pixels_get_index_255(self):
        rgb = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
        opaque = np.ones((16, 16), bool); opaque[:4] = False
        idx, pal = quantize(rgb, opaque, True)
        self.assertTrue((idx[:4] == 255).all())
        self.assertTrue((idx[4:] < 255).all())

    def test_all_transparent_does_not_crash(self):
        idx, pal = quantize(np.zeros((8, 8, 3), np.uint8), np.zeros((8, 8), bool), True)
        self.assertTrue((idx == 255).all())

    def test_many_colours_stay_close(self):
        rgb = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
        idx, pal = quantize(rgb, np.ones((64, 64), bool), False)
        self.assertLess(np.abs(pal[idx].astype(int) - rgb).mean(), 30)


class Bleed(unittest.TestCase):
    def test_unknown_pixels_take_neighbour_colours(self):
        rgb = np.zeros((8, 8, 3), np.uint8); rgb[:, :4] = (100, 150, 200)
        known = np.zeros((8, 8), bool); known[:, :4] = True
        out = bleed(rgb, known)
        self.assertTrue((out[:, 4:] == (100, 150, 200)).all())


class Judge(unittest.TestCase):
    def test_smooth_to_woven_is_flagged(self):
        smooth = np.full((64, 64, 3), 120, np.uint8) + rng.integers(0, 3, (64, 64, 1), dtype=np.uint8)
        weave = np.full((256, 256, 3), 120, np.uint8); weave[:, ::2] = 160
        self.assertEqual(judge(smooth, weave)[0], 'woven')

    def test_grain_to_plain_is_flagged(self):
        grain = rng.integers(60, 120, (64, 64, 1), dtype=np.uint8).repeat(3, 2)
        plain = np.full((256, 256, 3), 90, np.uint8)
        self.assertEqual(judge(grain, plain)[0], 'flat')

    def test_sign_losing_its_dither_is_not_flagged(self):
        sign = np.zeros((64, 64, 3), np.uint8); sign[:, 32:] = 230
        sign = np.clip(sign.astype(int) + rng.integers(-25, 25, (64, 64, 1)), 0, 255).astype(np.uint8)
        clean = np.zeros((256, 256, 3), np.uint8); clean[:, 128:] = 230
        self.assertEqual(judge(sign, clean)[0], '')


class IndexFile(unittest.TestCase):
    SAMPLE = ['FSHTool generated file -- be very careful when editing', 'a.QFS', 'QFS', 'SHPI 2 objects, tag GIMX',
              'BUFSZ 1000', 'NOGLOBPAL', 'ZR01 0000.BMP', 'BMP 7B +1 64 64 {0 0 0 0}', 'PAL 2D 256 1 {256 0 0 0}',
              'sky1 0001.BMP', 'BMP 7D +0 32 16 {0 0 0 0}', 'alpha 0001-a.BMP', '#END']

    def test_parse_resize_and_save(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'index.fsh'), 'w', newline='\r\n') as f:
                f.write('\n'.join(self.SAMPLE) + '\n')
            ix = Index(d)
            self.assertEqual(ix.signature(), ['ZR01', 'sky1'])
            self.assertEqual(ix.entries[1].alpha_file, '0001-a.BMP')
            ix.set_size(ix.entries[0], 256, 256)
            self.assertEqual(ix.grow_buffer(100), 1000 + 100 + 1024 * 1024)
            ix.save()
            again = Index(d)
            self.assertEqual((again.entries[0].w, again.entries[0].h), (256, 256))
            self.assertEqual(again.lines[ix.entries[0].line], 'BMP 7B +1 256 256 {0 0 0 0}')


if __name__ == '__main__':
    unittest.main()
