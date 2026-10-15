#!/usr/bin/env python3
"""nab_blocks.py — 用正确 blob 基址提取每 section 的权重块序列（第七轮接力包第 1 步）.

基址规则: base = body_len − final_cum − tail (tail 每 section 单独确认:
S1=2048→0x2F8C, S11=2048→0x4400, S0=1024).
"""
import struct, math, collections, json
import numpy as np

PATH = 'default.nab'
_DATA = open(PATH, 'rb').read()
import re
SECS = [m.start() for m in re.finditer(b'VPMN', _DATA)]

# body 相对块表偏移 + 块数 (weight_tables.json / 笔记第四轮)
TABLES = {
    0:  (0x2687c, 572, 1024),
    1:  (0x2dd0,   38, 2048),
    3:  (0xd57c,  140, None),
    4:  (0x12300, 177, None),
    6:  (0xc598,   96, None),
    7:  (0x16d98, 230, None),
    11: (0x4138,   38, 2048),
    12: (0xec30,  156, None),
    15: (0x9e04,  142, None),
    16: (0x9e04,  142, None),
}

def body(i):
    s = SECS[i]
    nxt = SECS[i+1] if i+1 < len(SECS) else len(_DATA)
    e = nxt - 32 if i+1 < len(SECS) else len(_DATA)
    hdrlen = struct.unpack('<4sHHI', _DATA[s:s+12])[3]
    return _DATA[s+hdrlen:e]

def parse_table(bd, off, n):
    """u32 对 (size, cum) 顺序流."""
    vals = struct.unpack(f'<{2*n}I', bd[off:off+8*n])
    return [(vals[2*i], vals[2*i+1]) for i in range(n)]

def ceil64(x): return (x + 63) & ~63

def extract(i, tail=None, verbose=True):
    bd = body(i)
    toff, n, tail_def = TABLES[i]
    tab = parse_table(bd, toff, n)
    final = tab[-1][1]
    if tail is None: tail = tail_def
    base = len(bd) - final - tail
    blocks = []
    for size, cum in tab:
        start = base + (cum - ceil64(size))
        blocks.append(bd[start:start+size])
    if verbose:
        print(f"S{i}: body={len(bd):,} table@{toff:#x} n={n} final_cum={final:,} tail={tail} base={base:#x}")
    return dict(body=bd, table=tab, base=base, tail=tail, blocks=blocks, final=final)

def entropy(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def classify(blk):
    """W=高熵权重, desc=结构化描述符, small=小块(bias/scale), zero=全零."""
    n = len(blk)
    h = entropy(blk)
    if h < 1.0: return 'zero'
    if n <= 160: return 'small'
    # desc 检测: 64B 记录结构 → 每 8B 窗口低熵 / 大量重复 magic
    arr = np.frombuffer(blk[:n//8*8], dtype='<u4')
    u32 = arr.reshape(-1, 2 if False else arr.size//2, 2) if False else None
    q = np.frombuffer(blk[:n//64*64], dtype='<u4').reshape(-1, 16)
    # 64B 记录间相似度: 相邻记录逐 u32 相等比例
    eq = (q[:-1] == q[1:]).mean() if len(q) > 1 else 0
    if h < 6.0 and eq > 0.25: return 'desc'
    if h > 6.5: return 'W'
    return 'mid'

if __name__ == '__main__':
    for i in (11, 1, 0):
        d = extract(i)
        tags = [classify(b) for b in d['blocks']]
        sizes = [t[0] for t in d['table']]
        cums = [t[1] for t in d['table']]
        print('  blk: ' + ' '.join(f"{s}{'·'+t if t!='W' else ''}" for s, t in zip(sizes, tags)))
        # 校验: cum 链自洽
        bad = [k for k in range(1, len(cums)) if cums[k] != cums[k-1] + ceil64(sizes[k])]
        print(f"  cum 链不自洽处: {bad if bad else '无'}")
        print()
