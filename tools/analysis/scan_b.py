#!/usr/bin/env python3
"""scan_b.py — Thumb-2 B.W (条件/无条件) 与 BLX.imm 分支目标扫描
B.T3 (cond): hw1=11110 S cond imm6,  hw2=10 J1 0 J2 imm11 → (hw2&0xD000)==0x8000, cond!=111x
B.T4 (uncond): hw1=11110 S imm10,    hw2=10 J1 1 J2 imm11 → (hw2&0xD000)==0x9000
BLX.imm (to ARM): hw2=11 J1 0 J2 imm11 → (hw2&0xD000)==0xC000
用法: python3 scan_b.py <hex_target>..."""
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

def main():
    targets = set(int(x, 16) for x in sys.argv[1:])
    data = open(BIN, 'rb').read()
    n = len(data)
    hits = {t: [] for t in targets}
    for off in range(0, n - 4, 2):
        hw1, hw2 = struct.unpack_from('<HH', data, off)
        pc = (BASE + off + 4) & ~3
        kind = None; imm32 = None
        if (hw1 & 0xF800) == 0xF000:
            S = (hw1 >> 10) & 1
            J1 = (hw2 >> 13) & 1; J2 = (hw2 >> 11) & 1
            I1 = 1 - (J1 ^ S); I2 = 1 - (J2 ^ S)
            m = hw2 & 0xD000
            if m == 0x9000:  # B.T4 uncond
                imm10 = hw1 & 0x3FF; imm11 = hw2 & 0x7FF
                comp = (S << 23) | (I1 << 22) | (I2 << 21) | (imm10 << 11) | imm11
                if comp & 0x800000: comp -= 0x1000000
                kind = 'B.W'; imm32 = comp << 1
            elif m == 0x8000 and (hw1 & 0x3C0) != 0x3C0:  # B.T3 cond
                imm6 = hw1 & 0x3F; imm11 = hw2 & 0x7FF
                comp = (S << 17) | (I1 << 16) | (I2 << 15) | (imm6 << 11) | imm11
                if comp & 0x20000: comp -= 0x40000
                kind = 'Bcc'; imm32 = comp << 1
            elif m == 0xC000:  # BLX imm (ARM)
                imm10 = hw1 & 0x3FF; imm11 = hw2 & 0x7FF
                comp = (S << 23) | (I1 << 22) | (I2 << 21) | (imm10 << 11) | imm11
                if comp & 0x800000: comp -= 0x1000000
                kind = 'BLX'; imm32 = (comp << 2) & ~3
            if kind and imm32 is not None:
                t = pc + imm32
                if t in targets:
                    hits[t].append((BASE + off, kind))
    for t in targets:
        refs = hits[t]
        if not refs:
            print(f"0x{t:x}: (no B.W/Bcc/BLX refs)")
            continue
        out = []
        for va, k in refs[:15]:
            fa, fn = func_of(va)
            out.append(f"{fn}@0x{fa:x}({k},at 0x{va:x})")
        print(f"0x{t:x}: {len(refs)} refs: {', '.join(out)}{' ...' if len(refs) > 15 else ''}")

if __name__ == '__main__':
    main()
