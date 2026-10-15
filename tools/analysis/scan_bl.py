#!/usr/bin/env python3
"""BL/B 跳转目标扫描 (ARM32+Thumb2): 找调用指定地址的全部函数"""
import struct, sys, bisect

BIN = "<workspace>/a1m2_ai_pipeline/copro/cpapp-b.bin"
BASE = 0x108000
IDX  = "<workspace>/a1m2_ai_pipeline/cpapp_fun_index.tsv"

def load_funcs():
    fs = []
    for i, ln in enumerate(open(IDX)):
        if i == 0 and ln.startswith('#'): continue
        p = ln.rstrip('\n').split('\t')
        if len(p) >= 2:
            try: fs.append(int(p[0], 16))
            except ValueError: pass
    fs.sort()
    return fs

data = open(BIN, 'rb').read()
starts = load_funcs()

def func_of(addr):
    i = bisect.bisect_right(starts, addr) - 1
    return starts[i] if i >= 0 else 0

def scan_target(target):
    hits = []
    n = len(data)
    # Thumb-2 BL: 0xF000-0xF7FF hw1 with (11110 S imm10), hw2 11xx J1 J2 imm11
    # 2026-10-12 修正: 原版在 S=0 时用 bit23(=I1) 判符号, 污染正向目标 → 大量漏报。
    # 正确: 25 位立即数 S:I1:I2:imm10:imm11:1<<1? — BL 偏移 = SignExtend(S:I1:I2:imm10:imm11) << 1,
    # 符号位只有 S。imm11 本身占 [11:1](含尾 0), 不再额外 <<1。
    for off in range(0, n - 4, 2):
        hw1, hw2 = struct.unpack_from('<HH', data, off)
        if (hw1 & 0xF800) == 0xF000 and (hw2 & 0xD000) == 0xD000:
            S  = (hw1 >> 10) & 1
            imm10 = hw1 & 0x3FF
            J1 = (hw2 >> 13) & 1; J2 = (hw2 >> 11) & 1
            imm11 = hw2 & 0x7FF
            I1 = 1 - (J1 ^ S); I2 = 1 - (J2 ^ S)
            comp = (S << 23) | (I1 << 22) | (I2 << 21) | (imm10 << 11) | imm11
            if comp & 0x800000: comp -= 0x1000000   # 24 位符号扩展, 唯一符号位 = S
            off_pc = off + 4  # Align(PC,4): PC = (off+4)+BASE (off even so aligned)
            tgt = BASE + off_pc + (comp << 1)
            if tgt == target:
                hits.append(('BL', BASE + off))
        # ARM BL (if file contains ARM code): cond=1110, 1011...
        if (hw1 & 0x0F00) == 0x0B00 and (hw1 >> 24) == 0xEA:
            pass  # ARM words misaligned with Thumb scan; skip (cpapp is Thumb)
    return hits

for arg in sys.argv[1:]:
    t = int(arg, 16)
    hs = scan_target(t)
    fset = sorted({func_of(a) for _, a in hs})
    print(f"target 0x{t:x}: {len(hs)} BL sites, {len(fset)} functions:")
    for f in fset:
        print(f"  caller func 0x{f:x}")
