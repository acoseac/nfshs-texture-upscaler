"""Palette quantisation, transparent-pixel bleeding, resizing and the quality measure."""
import numpy as np
from PIL import Image


def quantize(rgb, opaque, reserve_transparent):
    """Median cut on a 15-bit histogram (the FSH palette is 1:5:5:5), refined with a few k-means passes.

    Returns (indices HxW, palette 256x3). Transparent pixels get index 255 when reserve_transparent is set."""
    h, w, _ = rgb.shape
    px = rgb.reshape(-1, 3).astype(np.int64)
    op = opaque.reshape(-1)
    keys = ((px[:, 0] >> 3) << 10) | ((px[:, 1] >> 3) << 5) | (px[:, 2] >> 3)
    cnt = np.bincount(keys[op], minlength=32768)
    sums = np.stack([np.bincount(keys[op], px[op, c], 32768) for c in range(3)], 1)
    bins = np.nonzero(cnt)[0]
    comp = np.stack([bins >> 10, (bins >> 5) & 31, bins & 31], 1)
    max_colors = 255 if reserve_transparent else 256

    boxes = [np.arange(bins.size)]
    def score(box):
        if box.size < 2:
            return -1, 0
        rng = comp[box].max(0) - comp[box].min(0)
        axis = int(rng.argmax())
        return (rng[axis] * np.sqrt(cnt[bins[box]].sum()) if rng[axis] > 0 else -1), axis
    scores = [score(b) for b in boxes]
    while len(boxes) < max_colors:
        best = max(range(len(boxes)), key=lambda i: scores[i][0])
        if scores[best][0] < 0:
            break
        box, axis = boxes[best], scores[best][1]
        box = box[np.argsort(comp[box, axis], kind='stable')]
        acc = np.cumsum(cnt[bins[box]])
        cut = min(max(int(np.searchsorted(acc * 2, acc[-1])) + 1, 1), box.size - 1)
        boxes[best], scores[best] = box[:cut], score(box[:cut])
        boxes.append(box[cut:]); scores.append(score(box[cut:]))

    pal = np.array([sums[bins[b]].sum(0) / max(cnt[bins[b]].sum(), 1) for b in boxes], float)
    mean = sums[bins] / cnt[bins, None]
    for _ in range(4):
        d = ((mean[:, None, :] - pal[None, :, :]) ** 2).sum(2)
        lut = d.argmin(1)
        for p in range(len(pal)):
            m = lut == p
            if m.any():
                pal[p] = sums[bins[m]].sum(0) / cnt[bins[m]].sum()
    full_lut = np.zeros(32768, np.int64)
    full_lut[bins] = lut
    idx = full_lut[keys].astype(np.uint8)
    if reserve_transparent:
        idx[~op] = 255
    palette = np.zeros((256, 3), np.uint8)
    palette[:len(pal)] = np.clip(np.round(pal), 0, 255)
    return idx.reshape(h, w), palette


def bleed(rgb, known):
    """Fill unknown pixels with the average of known neighbours, repeatedly, so upscaling has no dark halo."""
    rgb = rgb.astype(np.float64).copy()
    known = known.copy()
    for _ in range(max(rgb.shape[:2])):
        if known.all():
            break
        k = known.astype(np.float64)
        acc = np.zeros_like(rgb); n = np.zeros(known.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ks = np.zeros_like(k); rs = np.zeros_like(rgb)
            ys = slice(max(dy, 0), k.shape[0] + min(dy, 0)); yd = slice(max(-dy, 0), k.shape[0] + min(-dy, 0))
            xs = slice(max(dx, 0), k.shape[1] + min(dx, 0)); xd = slice(max(-dx, 0), k.shape[1] + min(-dx, 0))
            ks[yd, xd] = k[ys, xs]; rs[yd, xd] = rgb[ys, xs] * k[ys, xs, None]
            acc += rs; n += ks
        new = (~known) & (n > 0)
        if not new.any():
            break
        rgb[new] = np.floor(acc[new] / n[new, None])
        known |= new
    return rgb.astype(np.uint8)


def resize(arr, w, h):
    """Bicubic resize of an RGB or single-channel uint8 array."""
    return np.asarray(Image.fromarray(arr).resize((w, h), Image.BICUBIC))


def edge_strength(rgb):
    """Average brightness change between horizontally neighbouring pixels, on 16 rows, as a percentage.

    A smooth texture scores about 1, grain 3 to 6, and the woven pattern Real-ESRGAN sometimes invents 10 or more."""
    c = rgb.astype(np.float64)
    v = (c.max(2) + c.min(2)) / 510  # HSL lightness, which the thresholds below were tuned on
    rows = v[::max(1, v.shape[0] // 16)]
    return float(np.abs(np.diff(rows, axis=1)).mean() * 100) if rows.shape[1] > 1 else 0.0


def judge(before_rgb, after_rgb):
    """'woven' when upscaling added a strong fine pattern, 'flat' when it wiped out the grain, else ''.

    Signs and painted graphics also lose their dithering, so 'flat' needs the result to be low in contrast
    overall (like grass or dirt), not only smooth. Tuned by eye on 93 textures; expect a few wrong calls."""
    e0, e1 = edge_strength(before_rgb), edge_strength(after_rgb)
    if e1 > 5 and e1 / max(e0, 0.1) > 3:
        return 'woven', e0, e1
    c = after_rgb.astype(np.float64)
    contrast = float(((c.max(2) + c.min(2)) / 510).std())
    if e0 > 2.5 and e1 < 1 and contrast < 0.09:
        return 'flat', e0, e1
    return '', e0, e1
