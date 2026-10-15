#!/usr/bin/env python3
"""指针引用扫描: 在 cpapp-b.bin 里找指向目标地址的 4 字节字（绝对指针/literal pool）
用法: python3 scan_ptr.py 19ece0 43242c ...  （十六进制, 不带 0x, Thumb bit 自动 ±1 都查）"""
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

data = open(BIN, 'rb').read()
n = len(data)

def scan_word(target):
    """找 4 字节 LE == target 或 target|1 的所有位置"""
    hits = []
    for val in (target, target | 1):
        pat = struct.pack('<I', val)
        pos = 0
        while True:
            pos = data.find(pat, pos)
            if pos < 0: break
            hits.append((pos + BASE, val))
            pos += 1
    return hits

for arg in sys.argv[1:]:
    t = int(arg, 16)
    hits = scan_word(t)
    # 分类: 代码区(literal pool, 归属某函数) vs 数据区
    by_region = {}
    for addr, val in hits:
        f = func_of(addr)
        # 函数区间判断: 若落在函数起点之后且距离下一起点 < 64KB 视为代码内
        nxt = starts[bisect.bisect_right(starts, addr)] if bisect.bisect_right(starts, addr) < len(starts) else 0
        in_code = (f != 0 and (nxt == 0 or addr - f < 0x10000) and addr - f > 8)
        reg = f"code:FUN_{f:08x}" if in_code else "data/unknown"
        by_region.setdefault(reg, []).append((addr, val))
    print(f"target 0x{t:x}: {len(hits)} pointer hits")
    for reg, lst in sorted(by_region.items()):
        addrs = ' '.join(f"0x{a:x}({'T' if v&1 else '-'})" for a, v in lst[:24])
        more = f" (+{len(lst)-24} more)" if len(lst) > 24 else ""
        print(f"  [{reg}] {addrs}{more}")
