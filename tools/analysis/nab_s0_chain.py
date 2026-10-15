#!/usr/bin/env python3
"""S0 通道链求解器.

假设: 大块 = 纯 int8 权重(可带少量 pad) 或 元数据(模式表/desc/bias).
对每个权重块枚举 (out,in): size = out*in*9 + pad (3x3) 或 out*in + pad (1x1), pad∈[0,700].
然后按 blob 顺序做链: in == 当前通道数 C (起点 3), 更新 C=out.
"""
import numpy as np, struct, re, collections
from nab_blocks import body, parse_table, TABLES

si = 0
bd = body(si)
toff, n, _ = TABLES[si]
tab = parse_table(bd, toff, n)
BASE = len(bd) - tab[-1][1] - 1024
sizes = [t[0] for t in tab]
cums = [t[1] for t in tab]
starts = [0] + cums[:-1]
blocks = [np.frombuffer(bd[BASE+starts[i]:BASE+cums[i]], dtype=np.uint8) for i in range(n)]
print(f'S0 base={BASE:#x} n={n}')
big = [(i, sizes[i]) for i in range(n) if sizes[i] > 64]
print(f'大块 {len(big)}: {big[:10]}...')

# ---- 分类 ----
def harmonic(b, lags=(4, 8)):
    x = b.astype(np.float64); x -= x.mean()
    den = (x*x).sum()
    if den == 0: return 0
    return max(float((x[:-L]*x[L:]).sum()/den) for L in lags)

def feat(b):
    a = b.astype(np.int32)
    return dict(std=float(a.std()), f0=float((a == 0).mean()),
                harm=harmonic(b), nz=float((a != 0).mean()))

def classify(b):
    f = feat(b)
    if f['harm'] > 0.35: return 'pat'      # 7B 模式表
    if f['f0'] > 0.55: return 'meta'       # 大量零: desc/bias 类
    if f['std'] > 55: return 'W'           # 稠密 int8
    return 'mid'

tags = {}
for i, s in big:
    tags[i] = classify(blocks[i])

seq = [(i, sizes[i], tags[i]) for i, _ in big]
print('\n大块序列 (idx size tag):')
for i, s, t in seq:
    print(f'  {i:3d} {s:>6} {t}')
