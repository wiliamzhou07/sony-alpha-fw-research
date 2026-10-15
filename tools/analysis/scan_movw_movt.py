#!/usr/bin/env python3
"""scan_movw_movt.py — cpapp-b.bin (ARM32) 中 movw/movt 立即数对地址引用扫描器
用法: scan_movw_movt.py <addr1,addr2,...>  → 输出每个目标 VA 被哪些函数以 movw+movt 构造引用
同时支持 ARM 与 Thumb-2 编码；函数区间从 cpapp_fun_index.tsv 读取。
"""
import sys, struct, bisect, re

BIN = 'copro/cpapp-b.bin'
BASE = 0x108000
IDX = 'cpapp_fun_index.tsv'

def load_funcs():
    fs = []
    for i, ln in enumerate(open(IDX)):
        if i == 0 and ln.startswith('#'): continue
        p = ln.rstrip('\n').split('\t')
        if len(p) >= 3:
            try: fs.append((int(p[0], 16), p[1]))
            except ValueError: pass
    fs.sort()
    return [a for a, _ in fs], [n for _, n in fs]

def find_refs(data, targets):
    n = len(data)
    hits = {t: [] for t in targets}
    # Thumb-2: movw hw1=0xF2xx(0100 pattern) hw2; movt hw1=0xF2C0.. 扫 2 字节步进
    lo_map = {}
    for t in targets:
        lo_map.setdefault(t & 0xFFFF, []).append(t)
    hi_set = {t >> 16 for t in targets}
    for off in range(0, n - 8, 2):
        hw1, hw2 = struct.unpack_from('<HH', data, off)
        # Thumb movw: 11110 i 10 0100 imm4
        if (hw1 & 0xFBF0) == 0xF240:
            imm16 = ((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11) | ((hw2 >> 12) & 7) << 8 | (hw2 & 0xFF)
            cand = lo_map.get(imm16)
            if not cand: continue
            # 在后续 16B 内找同 Rd 的 movt
            Rd = (hw2 >> 8) & 0xF
            for k in range(1, 5):
                o2 = off + 2 * k
                if o2 + 4 > n: break
                m1, m2 = struct.unpack_from('<HH', data, o2)
                if (m1 & 0xFBF0) == 0xF2C0:
                    immt = ((m1 & 0xF) << 12) | (((m1 >> 10) & 1) << 11) | ((m2 >> 12) & 7) << 8 | (m2 & 0xFF)
                    if ((m2 >> 8) & 0xF) == Rd and immt in hi_set:
                        va = BASE + off
                        for t in cand:
                            if t >> 16 == immt:
                                hits[t].append((va, 'T'))
        # ARM movw: cond 0011 0000 Rd imm4 imm12 (word 对齐检查)
        if off % 4 == 0 and off + 4 <= n:
            w, = struct.unpack_from('<I', data, off)
            if (w & 0x0FF00000) == 0x03000000:
                imm16 = ((w >> 4) & 0xF000) | (w & 0xFFF)
                Rd = (w >> 12) & 0xF
                cand = lo_map.get(imm16)
                if not cand: continue
                for k in range(1, 5):
                    o2 = off + 4 * k
                    if o2 + 4 > n: break
                    w2, = struct.unpack_from('<I', data, o2)
                    if (w2 & 0x0FF00000) == 0x03400000 and ((w2 >> 12) & 0xF) == Rd:
                        immt = ((w2 >> 4) & 0xF000) | (w2 & 0xFFF)
                        if immt in hi_set:
                            va = BASE + off
                            for t in cand:
                                if t >> 16 == immt:
                                    hits[t].append((va, 'A'))
    return hits

def main():
    targets = [int(x, 16) for x in sys.argv[1].split(',')]
    data = open(BIN, 'rb').read()
    starts, names = load_funcs()
    hits = find_refs(data, targets)
    for t in targets:
        refs = hits.get(t, [])
        if not refs:
            print(f"0x{t:x}: (no movw/movt refs)")
            continue
        out = []
        for va, mode in refs:
            i = bisect.bisect_right(starts, va) - 1
            fn = names[i] if i >= 0 else '?'
            out.append(f"FUN@{fn}(0x{starts[i]:x},{mode})" if i >= 0 else f"@0x{va:x}({mode})")
        print(f"0x{t:x}: {', '.join(out)}")

if __name__ == '__main__':
    main()
