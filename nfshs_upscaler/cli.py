"""Command line: nfshs-upscale upscale | check | restore | undo"""
import argparse
import fnmatch
import os
import sys

from .fsh import FshTool
from .pipeline import check_file, restore_file, run_folder, undo_file, upscale_file, write_report

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_files(game, tracks, names):
    root = os.path.join(game, 'Data', 'TRACKS')
    if not os.path.isdir(root):
        sys.exit(f'{game} has no Data\\TRACKS folder. Point --game at the game folder.')
    out = []
    for t in sorted(os.listdir(root)):
        if tracks and t.upper() not in tracks:
            continue
        for f in sorted(os.listdir(os.path.join(root, t))):
            if any(fnmatch.fnmatch(f.upper(), n) for n in names):
                out.append(os.path.join(root, t, f))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog='nfshs-upscale', description='Safely AI-upscale Need for Speed: High Stakes textures.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--game', required=True, help='game folder (the one with nfs4.exe or nfshs.exe)')
        p.add_argument('--fshtool', help='fshtool.exe (default: <game>\\FSHTool\\fshtool.exe)')
        p.add_argument('--out', default=os.path.join(HERE, 'output'), help='work, backups, reports and sheets go here')
        p.add_argument('--tracks', help='track folders, comma separated, e.g. UK,HILLS (default: all)')
        p.add_argument('--files', help='file names inside each track, e.g. TR0.QFS,TRN0.QFS')
        p.add_argument('--path', action='append', default=[], help='a specific QFS/FSH file instead of tracks (repeatable)')

    up = sub.add_parser('upscale', help='upscale textures, with backup, size check, verification and a quality report')
    common(up)
    up.add_argument('--esrgan', default=os.path.join(HERE, 'realesrgan', 'realesrgan-ncnn-vulkan.exe'))
    up.add_argument('--skies', action='store_true', help='do SKY.QFS (32-bit, soft transparency) instead of track textures')
    up.add_argument('--format', help='entry formats: 7B (track textures) or 7D,7E,78 (skies, effects)')
    up.add_argument('--max-size', type=int, default=256, help='largest side after upscaling (default 256, the Voodoo-era limit)')
    up.add_argument('--exclude', default='', help='texture names to leave alone, e.g. mous,fntc')
    up.add_argument('--bleed-below', type=int, default=1, help='direct colour only: fill pixels with alpha below this first (64 for soft sprites)')
    up.add_argument('--restore-flagged', action='store_true', help='put textures that came out woven or flat back to their originals')

    ck = sub.add_parser('check', help='compare upscaled files with their originals and flag woven or flat textures')
    common(ck)

    rs = sub.add_parser('restore', help='put single textures back to their originals')
    common(rs)
    rs.add_argument('--textures', required=True, help='e.g. 0149,0152')

    ud = sub.add_parser('undo', help='put whole files back to their originals')
    common(ud)

    a = ap.parse_args(argv)
    game = os.path.abspath(a.game)
    fsh = FshTool(a.fshtool or os.path.join(game, 'FSHTool', 'fshtool.exe'))
    run = run_folder(a.out)
    work, backups, sheets = (os.path.join(run, n) for n in ('work', 'backups', 'sheets'))
    os.makedirs(sheets, exist_ok=True)

    if a.path:
        files = [os.path.abspath(p) for p in a.path]
    else:
        skies = getattr(a, 'skies', False)
        names = [n.strip().upper() for n in a.files.split(',')] if a.files else (['SKY.QFS'] if skies else ['TR0.QFS', 'TRN0.QFS'])
        files = find_files(game, [t.strip().upper() for t in a.tracks.split(',')] if a.tracks else None, names)
    if not files:
        sys.exit('No files matched.')

    rows = []
    for path in files:
        try:
            if a.cmd == 'upscale':
                if not os.path.isfile(a.esrgan):
                    sys.exit(f'Real-ESRGAN not found at {a.esrgan}')
                fmt = tuple(a.format.split(',')) if a.format else (('7D',) if a.skies else ('7B',))
                row = upscale_file(fsh, path, a.esrgan, work, backups, sheets, game, fmt, a.max_size,
                                   [x for x in a.exclude.split(',') if x], a.bleed_below, a.restore_flagged)
            elif a.cmd == 'check':
                row = check_file(fsh, path, work, sheets, game)
            elif a.cmd == 'restore':
                n = restore_file(fsh, path, [t.strip() for t in a.textures.split(',')], work, backups, game)
                row = {'file': os.path.relpath(path, game), 'status': f'restored {n} textures'}
            else:
                undo_file(path, backups, game)
                row = {'file': os.path.relpath(path, game), 'status': 'put back to the original'}
        except Exception as e:  # one bad file shouldn't stop the rest
            row = {'file': os.path.relpath(path, game), 'status': f'FAILED: {e}'}
        rows.append(row)
        flags = ' '.join(f'{k}: {row[k]}' for k in ('woven', 'flat') if row.get(k))
        print(f"{row['file']}: {row['status']}" + (f'  [{flags}]' if flags else ''))
    write_report(rows, os.path.join(run, 'report.csv'))
    print(f'\nReport: {os.path.join(run, "report.csv")}')
    if any(r.get('sheet') for r in rows):
        print(f'Before/after sheets of flagged textures: {sheets}')
    if a.cmd in ('upscale', 'restore', 'undo'):
        print(f'Backups of the files as they were: {backups}')


if __name__ == '__main__':
    main()
