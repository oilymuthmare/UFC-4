#!/usr/bin/env python3
"""One-shot DirtyHttpCM / scnm dump from out/eboot.elf. Standard library only.

On the Ant cloud PC (PowerShell, folder that contains UFC4.exe):

    .\\python\\python.exe -E -s -c "exec(open(r'%TEMP%\\ufc4_scnm_report.py',encoding='utf-8').read())"

Or paste the file next to python.exe and run it. Prints guest-code hex and C strings.
Send the text in chat, not in a public issue.
"""
import struct
import sys
from pathlib import Path

ELF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / 'AppData/Local/UFC4Native/out/eboot.elf'


def load(path):
    f = Path(path).read_bytes()
    if f[:4] != b'\x7fELF':
        raise SystemExit(f'{path}: not eboot.elf')
    phoff, = struct.unpack_from('<Q', f, 0x20)
    phnum, = struct.unpack_from('<H', f, 0x38)
    segs = []
    for i in range(phnum):
        t, fl, off, va, _p, filesz, _m, _a = struct.unpack_from('<IIQQQQQQ', f, phoff + 56 * i)
        if t == 1:
            segs.append((va, off, filesz, fl))
    return f, segs


def read(f, segs, va, n):
    for v, o, s, _fl in segs:
        if v <= va and va + n <= v + s:
            return f[o + va - v: o + va - v + n]
    return None


def cstr(f, segs, va, n=80):
    b = read(f, segs, va, n)
    if not b:
        return 'MISSING'
    return repr(b.split(b'\x00', 1)[0])


def calls_to(f, segs, target):
    hits = []
    for v, o, s, fl in segs:
        if not (fl & 1):
            continue
        data = f[o:o + s]
        for i in range(len(data) - 5):
            if data[i] != 0xE8:
                continue
            rel = struct.unpack_from('<i', data, i + 1)[0]
            if v + i + 5 + rel == target:
                hits.append(v + i)
    return hits


def fn_start(f, segs, addr, limit=0x800):
    for back in range(0, limit):
        if read(f, segs, addr - back, 4) == b'\x55\x48\x89\xe5':
            return addr - back
    return None


def main():
    f, segs = load(ELF)
    print('elf', ELF, 'bytes', len(f))
    print('=== strings ===')
    for va, name in (
        (0x1EF8C87, 'default_name'),
        (0x20182E8, 'needle1'),
        (0x20182F3, 'needle2'),
        (0x20182FE, 's3'),
        (0x2018309, 's4'),
        (0x201830D, 's5'),
        (0x2018318, 's6'),
        (0x1F5F520, 's7'),
        (0x201D1D1, 'DirtyHttpCM'),
        (0x201B574, 'protohttpps4'),
        (0x1325A20, 'fnptr_a_bytes'),
        (0x1325AA0, 'fnptr_b_bytes'),
    ):
        if name.endswith('_bytes'):
            b = read(f, segs, va, 32)
            print(name, hex(va), b.hex(' ') if b else 'MISSING')
        else:
            print(name, hex(va), cstr(f, segs, va))

    print('=== windows ===')
    for va, n, name in (
        (0xC136C0, 192, 'use_site_0xc136c0'),
        (0x137BA00, 192, 'factory_0x137ba00'),
        (0x137BE30, 96, 'setup_0x137be30'),
        (0x137CF30, 96, 'maybe_0x137cf30'),
        (0x2B3EE0, 64, 'caller_0x2b3efb'),
        (0x10B3AB0, 64, 'caller_0x10b3ad3'),
        (0x10BAD20, 64, 'caller_0x10bad43'),
        (0x1E6B880, 64, 'caller_0x1e6b898'),
    ):
        b = read(f, segs, va, n)
        print(name, hex(va), b.hex(' ') if b else 'MISSING')

    print('=== calls to DirtyHttpCM init 0x13256b0 ===')
    for site in calls_to(f, segs, 0x13256B0):
        around = read(f, segs, site, 16)
        print(hex(site), around.hex(' ') if around else '')

    print('=== calls to factory 0x137ba00 ===')
    for site in calls_to(f, segs, 0x137BA00)[:16]:
        print(hex(site), (read(f, segs, site, 12) or b'').hex(' '))

    start = fn_start(f, segs, 0x137BA00)
    print('factory_fn_start', hex(start) if start else 'UNKNOWN')
    if start:
        print('factory_fn', (read(f, segs, start, 0x200) or b'').hex(' '))


if __name__ == '__main__':
    main()
