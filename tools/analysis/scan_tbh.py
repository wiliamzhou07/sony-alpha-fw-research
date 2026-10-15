#!/usr/bin/env python3
"""scan_tbh.py — TBB/TBH 跳转表扫描: 定位所有 tbb/tbh 指令, 解表, 报告表项命中目标的表
TBB: hw1=0xE8DF hw2=(Rn<<12)|0xF00|Rm      → target = table_base + u8[entry]
TBH: hw1=0xE8DF hw2=(Rn<<12)|0xF00|(Rm<<1) → target = table_base + u16[entry]*2
用法: python3 scan_tbh.py <hex_target>...   → 报告哪些表包含指向目标的表项
"""
import struct, sys, bisect

BIN = "<workspace>/a1m2_ai_pipeline/copro/cpapp-b.bin"
BASE = 0x108000
IDX  = "<workspace>/a1m2_ai_pipeline/cpapp_fun_index.tsv"

starts = []
for i, ln in enumerate(open(IDX)):
    if i == 0 and ln.startswith('#'): continue
    p = ln.rstrip('\n').split('\t')
    if len(p) >= 2:
        try: starts.append(int(p[0], 16))
        except ValueError: pass
starts.sort()

def func_of(addr):
    i = bisect.bisect_right(starts, addr) - 1
    return starts[i] if i >= 0 else 0

def main():
    targets = set(int(x, 16) for x in sys.argv[1:])
    data = open(BIN, 'rb').read()
    n = len(data)
    tset = targets
    found = []
    for off in range(0, n - 4, 2):
        hw1, hw2 = struct.unpack_from('<HH', data, off)
        if hw1 != 0xE8DF or (hw2 >> 8) != 0x0F: continue
        is_tbh = hw2 & 1
        table_base = BASE + off + 4
        # 解表: 最多 512 项, 表内偏移指向代码区
        hit_targets = []
        for e in range(512):
            if is_tbh:
                p = off + 4 + e * 2
                if p + 2 > n: break
                d, = struct.unpack_from('<H', data, p)
                t = table_base + d * 2
            else:
                p = off + 4 + e
                if p >= n: break
                d = data[p]
                t = table_base + d
            # 表项为 0 或超界即停(粗略)
            if t - BASE >= n: break
            if t in tset:
                hit_targets.append((e, t, BASE + off))
            if d == 0 and e > 8: break
        if hit_targets:
            found.append((BASE + off, is_tbh, hit_targets))
    for site, is_tbh, hits in found:
        kind = 'TBH' if is_tbh else 'TBB'
        f = func_of(site)
        for e, t, _ in hits:
            print(f"{kind} table @0x{site:x} (in FUN_{f:x}): entry[{e}] -> 0x{t:x}")
    if not found:
        print("(no TBB/TBH table entries hit targets)")

if __name__ == '__main__':
    main()
