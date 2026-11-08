"""Unpacking and repacking through FSHTool, and the index.fsh / alpha8.dat files it writes."""
import os
import re
import subprocess
from dataclasses import dataclass

QFS_LIMIT = 16 * 1024 * 1024  # a QFS stores its unpacked size in 3 bytes
ENTRY_RX = re.compile(r'^BMP (\w\w) \+(\d+) (\d+) (\d+) (\{.*\})$')


class FshTool:
    def __init__(self, exe):
        if not os.path.isfile(exe):
            raise FileNotFoundError(f'FSHTool not found at {exe}')
        self.exe = exe

    def run(self, src, dst):
        # FSHTool waits for Enter when it finishes, so it gets empty input
        p = subprocess.run([self.exe, src, dst], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors='replace')
        return p.stdout + p.stderr

    def unpack(self, qfs, folder):
        self.run(qfs, folder)
        if not os.path.isfile(os.path.join(folder, 'index.fsh')):
            raise RuntimeError(f'FSHTool could not unpack {qfs}')
        return Index(folder)

    def pack(self, folder, qfs):
        out = self.run(os.path.join(folder, 'index.fsh'), qfs)
        m = re.search(r'obtained (\d+) bytes', out)
        if not os.path.isfile(qfs) or not m:
            raise RuntimeError(f'FSHTool could not pack {folder}: {out.strip()[-300:]}')
        return int(m.group(1))


@dataclass
class Entry:
    line: int      # line number of the 'BMP ...' line
    name: str      # four-character texture name
    file: str      # e.g. 0149.BMP
    fmt: str       # 7B, 7D, 7E, 78 ...
    attach: int
    w: int
    h: int
    rest: str
    alpha_file: str | None


class Index:
    """index.fsh plus alpha8.dat, kept line for line so FSHTool reads them back unchanged."""

    def __init__(self, folder):
        self.folder = folder
        self.path = os.path.join(folder, 'index.fsh')
        self.lines = open(self.path, encoding='latin-1').read().splitlines()
        self.entries = []
        for n, line in enumerate(self.lines):
            m = ENTRY_RX.match(line)
            if not m or n == 0:
                continue
            name, file = (self.lines[n - 1].split(' ', 1) + [''])[:2]
            nxt = self.lines[n + 1] if n + 1 < len(self.lines) else ''
            alpha = nxt.split(' ', 1)[1] if nxt.startswith('alpha ') else None
            self.entries.append(Entry(n, name, file, m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5), alpha))
        self.alpha8 = {}
        a8 = os.path.join(folder, 'alpha8.dat')
        self._alpha_order = []
        if os.path.isfile(a8):
            al = open(a8, encoding='latin-1').read().splitlines()
            for k in range(0, len(al) - 1, 2):
                self.alpha8[al[k].strip()] = al[k + 1].strip()
                self._alpha_order.append(al[k].strip())

    def signature(self):
        """Entry names in order. Two versions of one file share it; a different track's file won't."""
        return [e.name for e in self.entries]

    def set_size(self, e, w, h):
        e.w, e.h = w, h
        self.lines[e.line] = f'BMP {e.fmt} +{e.attach} {w} {h} {e.rest}'

    def copy_entry_from(self, other, file):
        """Take one entry's size line from another version of this file (used when restoring)."""
        mine = next(e for e in self.entries if e.file == file)
        theirs = next(e for e in other.entries if e.file == file)
        if mine.name != theirs.name:
            raise ValueError(f'{file} is {mine.name} here but {theirs.name} in the other file')
        self.lines[mine.line] = other.lines[theirs.line]
        mine.w, mine.h = theirs.w, theirs.h
        if file in other.alpha8:
            if file not in self.alpha8:
                self._alpha_order.append(file)
            self.alpha8[file] = other.alpha8[file]

    def grow_buffer(self, extra):
        for k, line in enumerate(self.lines):
            m = re.match(r'^BUFSZ (\d+)$', line)
            if m:
                self.lines[k] = f'BUFSZ {int(m.group(1)) + extra + 1024 * 1024}'
                return int(m.group(1)) + extra + 1024 * 1024
        raise ValueError('index.fsh has no BUFSZ line')

    def palette_alpha(self, file):
        hexs = self.alpha8.get(file, '')
        return [int(hexs[i * 2:i * 2 + 2], 16) if len(hexs) >= i * 2 + 2 else 255 for i in range(256)]

    def save(self):
        with open(self.path, 'w', encoding='latin-1', newline='\r\n') as f:
            f.write('\n'.join(self.lines) + '\n')
        if self._alpha_order:
            with open(os.path.join(self.folder, 'alpha8.dat'), 'w', encoding='latin-1', newline='\r\n') as f:
                for k in self._alpha_order:
                    f.write(f'{k}\n{self.alpha8[k]}\n')
