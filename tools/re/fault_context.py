#!/usr/bin/env python3
"""Show the code around the addresses of a `Guest fault` report.

Uses only the Python standard library. The Windows package's python\\python.exe is enough;
do not install pip or capstone on the game PC.

Usage (on the Ant cloud PC, PowerShell, folder that contains UFC4.exe):

    .\\python\\python.exe -E -s tools\\re\\fault_context.py $env:LOCALAPPDATA\\UFC4Native\\out\\eboot.elf $env:LOCALAPPDATA\\UFC4Native\\logs\\20261019_122639.log

If this file is not in the extracted zip (the first Actions build did not include it), paste the
PowerShell block from the chat: it uses this same python.exe and out\\eboot.elf, and needs no pip.
The output contains game code: send it in chat, not in a public issue.
"""
import bisect
import re
import struct
import sys
from pathlib import Path

try:
    import capstone
except ImportError:
    capstone = None

_R64 = 'rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15'.split()
_R32 = 'eax ecx edx ebx esp ebp esi edi r8d r9d r10d r11d r12d r13d r14d r15d'.split()
_R16 = 'ax cx dx bx sp bp si di r8w r9w r10w r11w r12w r13w r14w r15w'.split()
_R8 = 'al cl dl bl spl bpl sil dil r8b r9b r10b r11b r12b r13b r14b r15b'.split()
_ALU = ('add', 'or', 'adc', 'sbb', 'and', 'sub', 'xor', 'cmp')
_JCC = 'o no b ae e ne be a s ns p np l ge le g'.split()


def _i8(b, i):
    return struct.unpack_from('<b', b, i)[0]


def _i32(b, i):
    return struct.unpack_from('<i', b, i)[0]


def _reg(ext_bit, r, width):
    n = (r & 7) | (8 if ext_bit else 0)
    if width == 8:
        return _R8[n]
    if width == 16:
        return _R16[n]
    if width == 32:
        return _R32[n]
    return _R64[n]


def _parse_modrm(data, i, rex, width):
    """(next, mem_or_reg, reg) starting at a ModRM byte. None if the bytes are truncated."""
    if i >= len(data):
        return None
    modrm = data[i]
    i += 1
    mod, reg, rm = modrm >> 6, (modrm >> 3) & 7, modrm & 7
    rname = _reg(rex & 4, reg, width)
    if mod == 3:
        return i, _reg(rex & 1, rm, width), rname
    parts, disp = [], None
    if rm == 4:
        if i >= len(data):
            return None
        sib = data[i]
        i += 1
        scale, index, base = 1 << (sib >> 6), (sib >> 3) & 7, sib & 7
        if not (index == 4 and (rex & 2) == 0):
            iname = _reg(rex & 2, index, 64)
            parts.append(iname if scale == 1 else f'{iname}*{scale}')
        rip_disp32 = mod == 0 and base == 5 and (rex & 1) == 0
        if not rip_disp32:
            parts.append(_reg(rex & 1, base, 64))
        elif i + 4 <= len(data):
            disp = _i32(data, i)
            i += 4
        else:
            return None
    elif mod == 0 and rm == 5:
        if i + 4 > len(data):
            return None
        disp = _i32(data, i)
        i += 4
        parts.append('rip')
    else:
        parts.append(_reg(rex & 1, rm, 64))
    if mod == 1:
        if i >= len(data):
            return None
        disp = _i8(data, i)
        i += 1
    elif mod == 2:
        if i + 4 > len(data):
            return None
        disp = _i32(data, i)
        i += 4
    if disp:
        parts.append(f'{disp:#x}' if disp > 0 else f'-{-disp:#x}')
    size = {8: 'byte', 16: 'word', 32: 'dword'}.get(width, 'qword')
    inner = '+'.join(parts) if parts else '0'
    mem = f'{size} ptr [{inner}]'.replace('+-', '-')
    return i, mem, rname


def decode_one(data, ip):
    """(size, text) for the instruction at data[0], or None."""
    if not data:
        return None
    i, rex, width, orig = 0, 0, 64, 64
    while i < len(data) and data[i] in (0x66, 0x67, 0xF2, 0xF3):
        if data[i] == 0x66:
            width = 16
        i += 1
    if i < len(data) and 0x40 <= data[i] <= 0x4F:
        rex = data[i] & 0xF
        if rex & 8:
            width = 64
        elif width != 16:
            width = 32
        i += 1
    if i >= len(data):
        return None
    op = data[i]
    i += 1

    def take_modrm(w=None):
        return _parse_modrm(data, i, rex, width if w is None else w)

    if op == 0x90:
        return i, 'nop'
    if 0x50 <= op <= 0x57:
        return i, 'push ' + _reg(rex & 1, op, 64)
    if 0x58 <= op <= 0x5F:
        return i, 'pop ' + _reg(rex & 1, op, 64)
    if 0xB8 <= op <= 0xBF:
        n = 8 if width == 64 else (2 if width == 16 else 4)
        if i + n > len(data):
            return None
        imm = int.from_bytes(data[i:i + n], 'little')
        return i + n, f'mov {_reg(rex & 1, op, width)}, {imm:#x}'
    if op == 0xC3:
        return i, 'ret'
    if op == 0xC9:
        return i, 'leave'
    if op == 0xE8 and i + 4 <= len(data):
        return i + 4, f'call {ip + i + 4 + _i32(data, i):#x}'
    if op == 0xE9 and i + 4 <= len(data):
        return i + 4, f'jmp {ip + i + 4 + _i32(data, i):#x}'
    if op == 0xEB and i < len(data):
        return i + 1, f'jmp {ip + i + 1 + _i8(data, i):#x}'
    if 0x70 <= op <= 0x7F and i < len(data):
        return i + 1, f'j{_JCC[op - 0x70]} {ip + i + 1 + _i8(data, i):#x}'
    if op in (0x88, 0x89):
        parsed = take_modrm(8 if op == 0x88 else None)
        if parsed:
            return parsed[0], f'mov {parsed[1]}, {parsed[2]}'
        return None
    if op in (0x8A, 0x8B):
        parsed = take_modrm(8 if op == 0x8A else None)
        if parsed:
            return parsed[0], f'mov {parsed[2]}, {parsed[1]}'
        return None
    if op == 0x8D:
        parsed = take_modrm()
        if parsed:
            addr = parsed[1]
            for prefix in ('qword ptr ', 'dword ptr ', 'word ptr ', 'byte ptr '):
                addr = addr.replace(prefix, '')
            return parsed[0], f'lea {parsed[2]}, {addr}'
        return None
    if op == 0x63:
        parsed = take_modrm(32)
        if parsed:
            return parsed[0], f'movsxd {parsed[2]}, {parsed[1]}'
        return None
    if op == 0x85:
        parsed = take_modrm()
        if parsed:
            return parsed[0], f'test {parsed[1]}, {parsed[2]}'
        return None
    if op in (0x01, 0x09, 0x21, 0x29, 0x31, 0x39):
        parsed = take_modrm()
        if parsed:
            return parsed[0], f'{_ALU[(op >> 3) & 7]} {parsed[1]}, {parsed[2]}'
        return None
    if op in (0x03, 0x0B, 0x23, 0x2B, 0x33, 0x3B):
        parsed = take_modrm()
        if parsed:
            return parsed[0], f'{_ALU[(op >> 3) & 7]} {parsed[2]}, {parsed[1]}'
        return None
    if op in (0x81, 0x83):
        parsed = take_modrm()
        if not parsed:
            return None
        j, dest, _regn = parsed
        name = _ALU[(data[i] >> 3) & 7]
        if op == 0x83 and j < len(data):
            return j + 1, f'{name} {dest}, {_i8(data, j):#x}'
        n = 2 if width == 16 else 4
        if j + n <= len(data):
            return j + n, f'{name} {dest}, {_i32(data, j):#x}'
        return None
    if op == 0xC7:
        parsed = take_modrm()
        if not parsed:
            return None
        j, dest, _regn = parsed
        n = 2 if width == 16 else 4
        if j + n > len(data):
            return None
        return j + n, f'mov {dest}, {int.from_bytes(data[j:j + n], "little", signed=True):#x}'
    if op == 0xFF:
        parsed = take_modrm(64)
        if not parsed:
            return None
        kind = (data[i] >> 3) & 7
        name = {0: 'inc', 1: 'dec', 2: 'call', 4: 'jmp', 6: 'push'}.get(kind)
        if name:
            return parsed[0], f'{name} {parsed[1]}'
        return None
    if op == 0x0F and i < len(data):
        op2 = data[i]
        i += 1
        if 0x80 <= op2 <= 0x8F and i + 4 <= len(data):
            return i + 4, f'j{_JCC[op2 - 0x80]} {ip + i + 4 + _i32(data, i):#x}'
        if op2 in (0xB6, 0xB7, 0xBE, 0xBF):
            src_w = 8 if op2 in (0xB6, 0xBE) else 16
            parsed = _parse_modrm(data, i, rex, src_w)
            if parsed:
                name = 'movzx' if op2 in (0xB6, 0xB7) else 'movsx'
                dst = _reg(rex & 4, (data[i] >> 3) & 7, 64 if (rex & 8) else 32)
                return parsed[0], f'{name} {dst}, {parsed[1]}'
            return None
        if op2 == 0x1F:
            parsed = _parse_modrm(data, i, rex, 64)
            return (parsed[0], 'nop') if parsed else None
        if op2 == 0x05:
            return i, 'syscall'
        if op2 == 0x31:
            return i, 'rdtsc'
    _ = orig
    return None


def disasm_builtin(data, start):
    out, i = [], 0
    while i < len(data):
        got = decode_one(data[i:], start + i)
        if not got or got[0] <= 0:
            out.append((start + i, f'db {data[i]:#04x}'))
            i += 1
            continue
        size, text = got
        out.append((start + i, text))
        i += size
    return out


def load(path):
    """(bytes, segments, funcs): load segments (vaddr, file offset, size, flags) and unwind functions."""
    f = Path(path).read_bytes()
    if f[:4] != b'\x7fELF':
        raise SystemExit(f'{path}: not an ELF (use out/eboot.elf from scripts/prepare.py)')
    phoff, = struct.unpack_from('<Q', f, 0x20)
    phnum, = struct.unpack_from('<H', f, 0x38)
    phdrs = [struct.unpack_from('<IIQQQQQQ', f, phoff + 56 * i) for i in range(phnum)]
    segs = [(p[3], p[2], p[5], p[1]) for p in phdrs if p[0] == 1]
    funcs = []
    hdr = next((p for p in phdrs if p[0] == 0x6474e550), None)
    if hdr:
        h, hva = hdr[2], hdr[3]
        count, = struct.unpack_from('<i', f, h + 8)
        text = next((s for s in segs if s[3] & 1), None)
        for i in range(count):
            loc, fde = struct.unpack_from('<ii', f, h + 12 + 8 * i)
            fde_off = hva + fde
            seg = next((s for s in segs if s[0] <= fde_off < s[0] + s[2]), text)
            if seg is None:
                continue
            size, = struct.unpack_from('<i', f, fde_off - seg[0] + seg[1] + 12)
            funcs.append((hva + loc, size))
    funcs.sort()
    return f, segs, funcs


def read(f, segs, vaddr, size):
    for va, off, filesz, _flags in segs:
        if va <= vaddr and vaddr + size <= va + filesz:
            return f[off + vaddr - va: off + vaddr - va + size]
    return None


def function_of(funcs, addr):
    i = bisect.bisect_right([s for s, _ in funcs], addr) - 1
    if i >= 0 and funcs[i][0] <= addr < funcs[i][0] + max(funcs[i][1], 1):
        return funcs[i]
    return None


def show(f, segs, funcs, label, addr, lines):
    print(f'\n=== {label}: guest offset {addr:#x}')
    func = function_of(funcs, addr)
    if func is None:
        print('  not inside a function listed by the executable (no unwind entry); showing raw bytes')
        start, end = max(addr - 48, 0), addr + 16
    else:
        start, end = func[0], min(func[0] + func[1], addr + 16)
        print(f'  function {func[0]:#x}, size {func[1]:#x} bytes, +{addr - func[0]:#x} into it')
    data = read(f, segs, start, end - start)
    if data is None:
        print('  address is outside the loaded segments')
        return
    if capstone is not None:
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        ins = [(i.address, f'{i.mnemonic} {i.op_str}'.rstrip()) for i in md.disasm(data, start) if i.address <= addr + 16]
    else:
        ins = [(a, t) for a, t in disasm_builtin(data, start) if a <= addr + 16]
    before = [x for x in ins if x[0] <= addr]
    mark = next((a for a, _t in ins if a >= addr), None)
    shown = ins[max(len(before) - lines, 0):]
    if mark is not None:
        keep = [a for a, _t in ins if a >= mark][:4]
        shown = [x for x in shown if x[0] < mark or x[0] in keep]
    for a, text in shown:
        arrow = '>>' if a == mark else '  '
        print(f'  {arrow} {a:#09x}  {text}')
    window = read(f, segs, max(addr - 16, start), 40) or b''
    print('  bytes: ' + window.hex(' '))


def parse_log(text):
    regs, frames = None, []
    m = re.search(r'Guest fault:.*?at guest offset (0x[0-9a-fA-F]+)', text)
    if not m:
        return None, [], None
    top = int(m.group(1), 16)
    tail = text[m.end():]
    r = re.search(r'^\s+rax=.*(?:\n\s+r\w\w=.*)*', tail, re.M)
    regs = r.group(0) if r else None
    for fm in re.finditer(r'^\s+#(\d+) guest offset (0x[0-9a-fA-F]+)', tail, re.M):
        frames.append((int(fm.group(1)), int(fm.group(2), 16)))
    return top, frames, regs


def main():
    args = sys.argv[1:]
    lines = 14
    if '--lines' in args:
        i = args.index('--lines')
        lines = int(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        raise SystemExit(__doc__)
    f, segs, funcs = load(args[0])
    decoder = 'capstone' if capstone else 'built-in'
    print(f'{args[0]}: {len(segs)} load segments, {len(funcs)} functions with unwind entries, {decoder} decoder')
    for arg in args[1:]:
        path = Path(arg)
        if path.is_file():
            top, frames, regs = parse_log(path.read_text(encoding='utf-8', errors='replace'))
            if top is None:
                print(f'{arg}: no "Guest fault" block found')
                continue
            if regs:
                print('\nregisters at the fault:\n' + regs)
                for m in re.finditer(r'(r\w\w)=([0-9a-f]{16})', regs):
                    v = int(m.group(2), 16)
                    text = v.to_bytes(8, 'little').rstrip(b'\0')
                    if 3 <= len(text) <= 8 and all(32 <= c < 127 for c in text):
                        print(f'  {m.group(1)} reads as ASCII "{text.decode()}" when stored little-endian')
            show(f, segs, funcs, 'the faulting instruction', top, lines)
            for n, addr in frames[:8]:
                show(f, segs, funcs, f'backtrace #{n} (a return address found on the stack)', addr, lines)
        else:
            show(f, segs, funcs, 'offset', int(arg, 0), lines)


if __name__ == '__main__':
    main()
