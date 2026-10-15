#!/usr/bin/env python3
"""scan_adr.py — ADR (PC-relative) 引用扫描: 找以 adr/add-pc/sub-pc 构造目标地址的全部位置
覆盖: Thumb T1(16-bit ADD Rd,PC,imm8*4), Thumb-2 ADR.W T2/T3(ADD/SUB Rd,PC,#const),
      ARM A32 ADR(ADD/SUB pc, imm12)。
用法: python3 scan_adr.py <hex_addr>...   → 每个目标的引用点(宿主函数)
"""
import struct, sys, bisect

BIN = "<workspace>/a1m2_ai_pipeline/copro/cpapp-b.bin"
BASE = 0x108000
IDX  = "<workspace>/a1m2_ai_pipeline/cpapp_fun_index.tsv"

starts, names = [], []
for i, ln in enumerate(open(IDX)):
    if i == 0 and ln.startswith('#'): continue
    p = ln.rstrip('\n').split('\t')
    if len(p) >= 3:
        try:
            starts.append(int(p[0], 16)); names.append(p[1])
        except ValueError: pass
o = sorted(range(len(starts)), key=lambda k: starts[k])
starts = [starts[k] for k in o]; names = [names[k] for k in o]

def func_of(addr):
    i = bisect.bisect_right(starts, addr) - 1
    return (starts[i], names[i]) if i >= 0 else (0, '?')

def thumb_expand_imm(imm12):
    if (imm12 >> 10) != 0:
        return imm12
    bits98 = (imm12 >> 8) & 3
    imm8 = imm12 & 0xFF
    if bits98 == 0: return imm8
    if bits98 == 1: return (imm8 << 16) | imm8
    if bits98 == 2: return (imm8 << 24) | (imm8 << 16)
    return (imm8 << 24) | (imm8 << 8) | (imm8 << 16) | imm8

def scan(data, targets):
    n = len(data)
    tset = set(targets)
    hits = {t: [] for t in targets}
    for off in range(0, n - 4, 2):
        pc4 = (BASE + off + 4) & ~3
        hw1, = struct.unpack_from('<H', data, off)
        # T1: ADD Rd, PC, imm8*4   (0xA000-0xA7FF)
        if (hw1 & 0xF800) == 0xA000:
            t = pc4 + (hw1 & 0xFF) * 4
            if t in tset: hits[t].append((BASE + off, 'T1'))
        if off + 4 > n: break
        hw2, = struct.unpack_from('<H', data, off + 2)
        # T2/T3: ADR.W = ADD/SUB Rd, PC, #const  (Rn=0xF)
        if (hw1 & 0xFBF0) == 0xF100 and (hw1 & 0xF) == 0xF:
            i_bit = (hw1 >> 10) & 1
            imm3 = (hw2 >> 12) & 7
            imm8 = hw2 & 0xFF
            const = thumb_expand_imm((i_bit << 11) | (imm3 << 8) | imm8)
            t = pc4 + const
            if t in tset: hits[t].append((BASE + off, 'T2'))
        elif (hw1 & 0xFBF0) == 0xF1A0 and (hw1 & 0xF) == 0xF:
            i_bit = (hw1 >> 10) & 1
            imm3 = (hw2 >> 12) & 7
            imm8 = hw2 & 0xFF
            const = thumb_expand_imm((i_bit << 11) | (imm3 << 8) | imm8)
            t = pc4 - const
            if t in tset: hits[t].append((BASE + off, 'T3'))
        # ARM A32 ADR (word-aligned)
        if off % 4 == 0:
            w, = struct.unpack_from('<I', data, off)
            if (w & 0x0FF0F000) == 0x028F0000:
                t = BASE + off + 8 + (w & 0xFFF)
                if t in tset: hits[t].append((BASE + off, 'A+'))
            elif (w & 0x0FF0F000) == 0x024F0000:
                t = BASE + off + 8 - (w & 0xFFF)
                if t in tset: hits[t].append((BASE + off, 'A-'))
    return hits

def main():
    targets = [int(x, 16) for x in sys.argv[1:]]
    data = open(BIN, 'rb').read()
    hits = scan(data, targets)
    for t in targets:
        refs = hits.get(t, [])
        if not refs:
            print(f"0x{t:x}: (no ADR refs)")
            continue
        out = []
        for va, mode in refs:
            fa, fn = func_of(va)
            out.append(f"{fn}@0x{fa:x}({mode},at 0x{va:x})")
        print(f"0x{t:x}: {len(refs)} refs: {', '.join(out[:12])}{' ...' if len(out) > 12 else ''}")

if __name__ == '__main__':
    main()
