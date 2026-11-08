"""Whole-file operations: upscale with backup and checks, quality report, restoring single textures, undo."""
import csv
import os
import shutil
import time

from PIL import Image, ImageDraw

from .fsh import QFS_LIMIT, Index
from .imaging import judge
from .upscale import load_rgba, upscale_folder

ORIGINAL = ' original'  # the HD Mod Pack's convention: the untouched file sits next to the new one


def _fresh(folder):
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    return folder


def _label(path, game):
    rel = os.path.relpath(path, game) if game else os.path.basename(path)
    return rel.replace('\\', '/')


def compare(orig_index, new_index):
    """Judges every entry whose size changed. Returns rows of (file, name, verdict, edge before, edge after)."""
    rows = []
    by_file = {e.file: e for e in orig_index.entries}
    for e in new_index.entries:
        o = by_file.get(e.file)
        if not o or (o.w, o.h) == (e.w, e.h):
            continue
        try:
            verdict, e0, e1 = judge(load_rgba(orig_index, o)[0], load_rgba(new_index, e)[0])
        except ValueError:
            continue
        rows.append((e.file, e.name, verdict, round(e0, 2), round(e1, 2)))
    return rows


def sheet(pairs, out, title=''):
    """Before/after contact sheet. pairs: (orig index, new index, file, label)."""
    if not pairs:
        return None
    cols, cell, pad = 4, 160, 18
    rows = (len(pairs) + cols - 1) // cols
    img = Image.new('RGB', (cols * (cell * 2 + 8), rows * (cell + pad) + 24), (40, 40, 40))
    d = ImageDraw.Draw(img)
    d.text((4, 4), title, fill=(255, 255, 255))
    for i, (oi, ni, file, label) in enumerate(pairs):
        x, y = (i % cols) * (cell * 2 + 8), 24 + (i // cols) * (cell + pad)
        for k, idx in enumerate((oi, ni)):
            e = next(en for en in idx.entries if en.file == file)
            rgb = load_rgba(idx, e)[0]
            img.paste(Image.fromarray(rgb).resize((cell - 2, cell - 2), Image.NEAREST if k == 0 else Image.BILINEAR), (x + k * cell, y + pad))
        d.text((x + 2, y + 3), label, fill=(255, 220, 0))
    img.save(out)
    return out


def original_status(fsh, path, work):
    """'none', 'matches' (same file, earlier version) or 'stale' (an 'original' from a different file, e.g. a replaced track)."""
    orig = path + ORIGINAL
    if not os.path.exists(orig):
        return 'none', None, None
    a = fsh.unpack(orig, _fresh(os.path.join(work, 'orig')))
    b = fsh.unpack(path, _fresh(os.path.join(work, 'now')))
    return ('matches' if a.signature() == b.signature() else 'stale'), a, b


def restore_in_folder(index, orig_index, files):
    for f in files:
        shutil.copyfile(os.path.join(orig_index.folder, f), os.path.join(index.folder, f))
        index.copy_entry_from(orig_index, f)
    index.save()


def _pack_and_verify(fsh, folder_index, out_qfs, work):
    if os.path.exists(out_qfs):
        os.remove(out_qfs)
    size = fsh.pack(folder_index.folder, out_qfs)
    check = fsh.unpack(out_qfs, _fresh(os.path.join(work, 'verify')))
    want = [(e.name, e.fmt, e.w, e.h) for e in folder_index.entries]
    got = [(e.name, e.fmt, e.w, e.h) for e in check.entries]
    if want != got:
        raise RuntimeError(f'verify failed: {len(got)} entries read back, {len(want)} expected')
    return size, check


def upscale_file(fsh, path, esrgan, work, backups, sheets, game=None, formats=('7B',), max_size=256, exclude=(),
                 bleed_below=1, restore_flagged=False, log=print):
    label = _label(path, game)
    row = {'file': label, 'status': '', 'textures': 0, 'max_size': '', 'unpacked_mb': '', 'woven': '', 'flat': '', 'restored': ''}
    w = _fresh(os.path.join(work, label.replace('/', '_')))
    status, _, _ = original_status(fsh, path, w)
    if status == 'matches':
        row['status'] = 'skipped: already done (an "original" is next to it)'
        return row
    if status == 'stale':
        row['status'] = 'skipped: its "original" belongs to a different file, so undo would restore the wrong textures. Move it away first'
        return row

    orig = fsh.unpack(path, _fresh(os.path.join(w, 'orig')))
    size = None
    for mx in (max_size, 128) if max_size > 128 else (max_size,):
        shutil.rmtree(os.path.join(w, 'fsh'), ignore_errors=True)
        shutil.copytree(orig.folder, os.path.join(w, 'fsh'))
        idx = Index(os.path.join(w, 'fsh'))
        changed = upscale_folder(idx, esrgan, formats=formats, max_size=mx, exclude=exclude, bleed_below=bleed_below, log=log)
        if not changed:
            row['status'] = 'nothing to upscale'
            return row
        out = os.path.join(w, 'new.QFS')
        if os.path.exists(out):
            os.remove(out)
        size = fsh.pack(idx.folder, out)
        if size < QFS_LIMIT:
            row['max_size'] = mx
            break
        log(f'{label}: {size / 2**20:.1f} MB unpacked is over the 16 MB limit at {mx} px')
        size = None
    if size is None:
        row['status'] = 'skipped: over the 16 MB limit even at 128 px'
        return row

    size, check = _pack_and_verify(fsh, idx, os.path.join(w, 'new.QFS'), w)
    rows = compare(orig, check)
    flagged = [r for r in rows if r[2]]
    row.update(textures=len(changed), unpacked_mb=f'{size / 2**20:.1f}',
               woven=' '.join(r[0][:-4] for r in flagged if r[2] == 'woven'),
               flat=' '.join(r[0][:-4] for r in flagged if r[2] == 'flat'))
    pairs = [(orig, check, r[0], f'{r[2]} {r[0][:-4]} ({r[3]}>{r[4]})') for r in flagged]
    row['sheet'] = sheet(pairs, os.path.join(sheets, label.replace('/', '_') + '.png'), f'{label}: flagged textures, before | after') or ''
    if restore_flagged and flagged:
        restore_in_folder(idx, orig, [r[0] for r in flagged])
        size, check = _pack_and_verify(fsh, idx, os.path.join(w, 'new.QFS'), w)
        row['restored'] = len(flagged)
        row['unpacked_mb'] = f'{size / 2**20:.1f}'

    dest = os.path.join(backups, os.path.dirname(label))
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
    shutil.copy2(path, path + ORIGINAL)
    shutil.copyfile(os.path.join(w, 'new.QFS'), path)
    row['status'] = 'installed'
    return row


def check_file(fsh, path, work, sheets, game=None):
    """Compares an upscaled file with its 'original' and lists textures that look woven or flat."""
    label = _label(path, game)
    w = _fresh(os.path.join(work, 'check', label.replace('/', '_')))
    status, a, b = original_status(fsh, path, w)
    if status != 'matches':
        return {'file': label, 'status': 'no original to compare' if status == 'none' else 'original belongs to a different file'}
    rows = compare(a, b)
    flagged = [r for r in rows if r[2]]
    pairs = [(a, b, r[0], f'{r[2]} {r[0][:-4]} ({r[3]}>{r[4]})') for r in flagged]
    return {'file': label, 'status': 'checked', 'upscaled': len(rows),
            'woven': ' '.join(r[0][:-4] for r in flagged if r[2] == 'woven'),
            'flat': ' '.join(r[0][:-4] for r in flagged if r[2] == 'flat'),
            'sheet': sheet(pairs, os.path.join(sheets, label.replace('/', '_') + '.png'), f'{label}: flagged textures, before | after') or ''}


def restore_file(fsh, path, textures, work, backups, game=None):
    """Puts single textures back to the versions in '<file> original'."""
    label = _label(path, game)
    w = _fresh(os.path.join(work, 'restore', label.replace('/', '_')))
    status, a, b = original_status(fsh, path, w)
    if status != 'matches':
        raise RuntimeError(f'{label}: needs an "original" of the same file next to it ({status})')
    files = [t if t.upper().endswith('.BMP') else f'{t}.BMP' for t in textures]
    restore_in_folder(b, a, files)
    _pack_and_verify(fsh, b, os.path.join(w, 'new.QFS'), w)
    dest = os.path.join(backups, os.path.dirname(label))
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
    shutil.copyfile(os.path.join(w, 'new.QFS'), path)
    return len(files)


def undo_file(path, backups, game=None):
    """Moves '<file> original' back in place, after backing up the current file."""
    orig = path + ORIGINAL
    if not os.path.exists(orig):
        raise RuntimeError(f'{path}: there is no "original" next to it')
    label = _label(path, game)
    dest = os.path.join(backups, os.path.dirname(label))
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
    os.replace(orig, path)


def write_report(rows, out):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(out, 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, keys)
        wr.writeheader()
        wr.writerows(rows)


def run_folder(base):
    return os.path.join(base, time.strftime('%Y%m%d-%H%M%S'))
