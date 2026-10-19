#!/usr/bin/env python3
"""Dump hex around guest offsets in out/eboot.elf. Standard library only; no pip.

    python\\python.exe -E -s tools\\re\\dump_guest.py %LOCALAPPDATA%\\UFC4Native\\out\\eboot.elf 0x137cde4 0x1322a57
"""
import struct
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    f = Path(sys.argv[1]).read_bytes()
    if f[:4] != b'\x7fELF':
        raise SystemExit(f'{sys.argv[1]}: not an ELF')
    phoff, = struct.unpack_from('<Q', f, 0x20)
    phnum, = struct.unpack_from('<H', f, 0x38)
    segs = []
    for i in range(phnum):
        p = struct.unpack_from('<IIQQQQQQ', f, phoff + 56 * i)
        if p[0] == 1:
            segs.append((p[3], p[2], p[5]))
    for arg in sys.argv[2:]:
        addr = int(arg, 0)
        blob = None
        for va, off, size in segs:
            start = addr - 24
            if va <= start and start + 48 <= va + size:
                blob = f[off + start - va: off + start - va + 48]
                break
        print(f'{addr:#x}  {blob.hex(" ") if blob else "not in a load segment"}')


if __name__ == '__main__':
    main()
