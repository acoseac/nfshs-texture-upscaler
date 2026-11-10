"""AI-upscales the textures of one unpacked FSH/QFS folder and writes them back in their own format."""
import os
import shutil
import subprocess

import numpy as np
from PIL import Image

from . import bmp
from .imaging import bleed, quantize, resize

DIRECT = {'7D', '7E', '78'}  # direct colour: FSHTool unpacks these as 24-bit colour + optional 8-bit alpha BMP


def load_rgba(index, e):
    """Colour and alpha of one entry as (RGB HxWx3, alpha HxW) uint8 arrays."""
    path = os.path.join(index.folder, e.file)
    if e.fmt == '7B':
        idx, pal = bmp.read8(path)
        pa = np.array(index.palette_alpha(e.file), np.uint8)
        return pal[idx][:, :, 2::-1].copy(), pa[idx]
    rgb = bmp.read24(path)
    alpha = np.full(rgb.shape[:2], 255, np.uint8)
    if e.alpha_file:
        aidx, apal = bmp.read8(os.path.join(index.folder, e.alpha_file))
        alpha = apal[aidx][:, :, 0]
    return rgb, alpha


def upscale_folder(index, esrgan, model='realesrgan-x4plus', formats=('7B',), min_size=32, max_size=256,
                   exclude=(), bleed_below=1, log=print):
    """Upscales every entry of the given formats whose longer side is in [min_size, max_size).

    Returns the files that were changed. index.fsh, alpha8.dat and the buffer size are updated and saved."""
    if '7B' in formats and len(formats) > 1:
        raise ValueError('7B cannot be combined with other formats')
    palettised = '7B' in formats
    # next to the unpacked folder, named after it, so two folders with the same parent don't share it
    work = os.path.join(os.path.dirname(index.folder), os.path.basename(index.folder) + '-upscale')
    in_dir, out_dir = os.path.join(work, 'in'), os.path.join(work, 'out')
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(in_dir); os.makedirs(out_dir)

    jobs = []
    for e in index.entries:
        if e.fmt not in formats or e.name in exclude:
            continue
        mx = max(e.w, e.h)
        if mx < min_size or mx >= max_size:
            continue
        rgb, alpha = load_rgba(index, e)
        threshold = 128 if palettised else bleed_below
        transparent = alpha < threshold
        if transparent.any() and not transparent.all():
            rgb = bleed(rgb, ~transparent)
        Image.fromarray(rgb).save(os.path.join(in_dir, os.path.splitext(e.file)[0] + '.png'))
        scale = min(4, max_size // mx)
        jobs.append((e, alpha, scale, bool(transparent.any())))
    log(f'Selected {len(jobs)} textures ({sum(j[3] for j in jobs)} with transparency)')
    if not jobs:
        return []

    p = subprocess.run([esrgan, '-i', in_dir, '-o', out_dir, '-n', model, '-s', '4', '-f', 'png'],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, errors='replace')
    if p.returncode != 0:
        raise RuntimeError(f'Real-ESRGAN failed ({p.returncode}): {p.stderr.strip()[-300:]}')

    extra = 0
    for e, alpha, scale, has_alpha in jobs:
        nw, nh = e.w * scale, e.h * scale
        up = np.asarray(Image.open(os.path.join(out_dir, os.path.splitext(e.file)[0] + '.png')).convert('RGB'))
        rgb = up if up.shape[:2] == (nh, nw) else resize(up, nw, nh)
        path = os.path.join(index.folder, e.file)
        if not palettised:
            # FSHTool converts the 24-bit colour back to the entry's own format when repacking
            bmp.write24(path, rgb)
            if e.alpha_file:
                bmp.write8gray(os.path.join(index.folder, e.alpha_file), resize(alpha, nw, nh))
            extra += 4 * (nw * nh - e.w * e.h)
        else:
            # transparency is 1-bit in these palettes: bicubic up, then threshold back to crisp edges
            opaque = resize(alpha, nw, nh) >= 128 if has_alpha else np.ones((nh, nw), bool)
            idx, pal = quantize(rgb, opaque, has_alpha)
            pa = np.full(256, 255, np.uint8)
            if has_alpha:
                pa[255] = 0
            bmp.write8pal(path, idx, pal, pa)
            if e.file not in index.alpha8:
                index._alpha_order.append(e.file)
            index.alpha8[e.file] = ''.join(f'{v:02X}' for v in pa)
            extra += nw * nh - e.w * e.h
        index.set_size(e, nw, nh)
    index.grow_buffer(extra)
    index.save()
    shutil.rmtree(work, ignore_errors=True)
    return [j[0].file for j in jobs]
