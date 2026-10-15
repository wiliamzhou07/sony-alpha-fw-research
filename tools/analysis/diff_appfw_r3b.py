#!/usr/bin/env python3
"""diff_appfw_r3b.py — 最终推动: 数据地址分区线性插值 → 访问器配对 + 二次对齐 + 大间隔处理
输入: appfw_diff_summary_v3.tsv (117469 matched)
新增: ① 数据地址单调 LIS + 分段线性插值器
      ② 访问器 pass: 数据引用地址翻译(±0x20) + 唯一候选 → 配对 (3 轮迭代)
      ③ 二次区域对齐 (降阈值 3.5 + 唯一性 + 全间隔不跳过)
输出: appfw_diff_summary_v4.tsv
"""
import re, sys, collections, hashlib, bisect as bs

A1   = "<workspace>/firmware_reverse/decompiled/a1_appfw.c"
A1M2 = "<workspace>/firmware_reverse/decompiled/a1m2_appfw.c"
TSV_IN  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v3.tsv"
OUT  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v4.tsv"

HDR  = re.compile(r"^// ==== (FUN_[0-9a-f]+) @ ([0-9a-fA-F]+) ====")
TOKC = re.compile(r'\b(?:thunk_)?FUN_[0-9a-f]{6,}')
TOKD = re.compile(r'\b(?:_?DAT|s|u)_[0-9a-f]{6,}')
MASK = re.compile(r'\b(FUN|DAT|_DAT|s|u|UNK|thunk_FUN)_[0-9a-fA-F]{6,}\b')
ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')

def parse(path):
    cur_name, cur_addr, calls, datas, body = None, None, [], [], []
    with open(path, "r", errors="replace") as f:
        for ln in f:
            m = HDR.match(ln.rstrip("\n"))
            if m:
                if cur_name is not None:
                    yield cur_addr, cur_name, calls, datas, body
                cur_name, cur_addr, calls, datas, body = m.group(1), int(m.group(2), 16), [], [], []
            elif cur_name is not None:
                calls += [int(x.split('_')[-1], 16) for x in TOKC.findall(ln)]
                datas += [int(t.rsplit('_', 1)[1], 16) for t in TOKD.findall(ln)]
                body.append(ln)
    if cur_name is not None:
        yield cur_addr, cur_name, calls, datas, body

def line_hashes(lines, minlen=16):
    out = set()
    for ln in lines:
        t = re.sub(r'\s+', ' ', MASK.sub('X', ADDR.sub('0xA', ln))).strip()
        if len(t) >= minlen:
            out.add(int.from_bytes(hashlib.blake2b(t.encode(), digest_size=8).digest(), 'big'))
    return out

def load(path):
    F = {}
    n = 0
    for addr, name, calls, datas, body in parse(path):
        F[addr] = [name, calls, datas, line_hashes(body) if len(body) >= 6 else set(), len(body)]
        n += 1
        if n % 50000 == 0: print(f"  {n} ...", flush=True)
    return F

def lh_jac(ha, hb):
    if not ha or not hb: return 0.0
    return len(ha & hb) / len(ha | hb)

def lis_chain(pts):
    """pts: [(ka, kb)] 按 ka 升序; 返回 kb 单调递增的最大子序列 (索引列表)"""
    tails, tidx, prev = [], [], []
    for k, (_, kb) in enumerate(pts):
        pos = bs.bisect_left(tails, kb)
        if pos == len(tails):
            tails.append(kb); tidx.append(k)
        else:
            tails[pos] = kb; tidx[pos] = k
        prev.append(tidx[pos - 1] if pos > 0 else -1)
    out = []
    k = tidx[-1] if tidx else -1
    while k >= 0:
        out.append(k); k = prev[k]
    return out[::-1]

def main():
    print("loading anchors ...", flush=True)
    match = {}
    for ln in open(TSV_IN):
        p = ln.rstrip('\n').split('\t')
        if p[0] == 'matched' and p[1] and p[2]:
            match[int(p[1], 16)] = int(p[2], 16)
    print(f"  {len(match)} anchors", flush=True)

    print("parsing a1 ...", flush=True);   FA = load(A1)
    print("parsing a1m2 ...", flush=True); FB = load(A1M2)
    print(f"  a1 {len(FA)} / a1m2 {len(FB)}", flush=True)
    used_b = set(match.values())
    la = sorted(FA); lb = sorted(FB)
    ia = {a: i for i, a in enumerate(la)}
    ib = {b: i for i, b in enumerate(lb)}

    # ---- 数据地址插值器 ----
    print("data interpolator ...", flush=True)
    def build_interp():
        pts = []
        step = max(1, len(match) // 60000)
        for a, b in list(match.items())[::step]:
            da_ = FA[a][2]; db_ = FB[b][2]
            if da_ and db_ and len(da_) == len(db_):
                for xa, yb in zip(da_, db_):
                    pts.append((xa, yb))
        pts.sort()
        idx = lis_chain(pts)
        pts = [pts[k] for k in idx]
        # 去重相邻 (同一 token 多次引用)
        ded = []
        for xa, yb in pts:
            if ded and ded[-1][0] == xa:
                if abs(ded[-1][1] - yb) > 0x40:  # 同地址映射冲突, 保留多数近似: 跳过
                    continue
                continue
            ded.append((xa, yb))
        xs = [p[0] for p in ded]; ys = [p[1] for p in ded]
        return ded, xs, ys
    ded, ixs, iys = build_interp()
    print(f"  interp anchors: {len(ded)}", flush=True)
    def interp(x):
        i = bs.bisect_right(ixs, x) - 1
        if i < 0 or i >= len(ded) - 1: return None
        x0, y0 = ded[i]; x1, y1 = ded[i + 1]
        if x1 == x0: return y0
        return int(y0 + (y1 - y0) * (x - x0) / (x1 - x0))

    # ---- 访问器 pass (迭代 3 轮) ----
    print("accessor pass ...", flush=True)
    unmatched_a = set(a for a in la if a not in match)
    unmatched_b = set(b for b in lb if b not in used_b)
    # b 侧小函数数据引用索引: data addr -> [b]
    def rebuild_bidx():
        bidx = collections.defaultdict(list)
        for b in unmatched_b:
            if FB[b][4] > 64: continue
            for y in set(FB[b][2]):
                bidx[y].append(b)
        return bidx
    bidx = rebuild_bidx()
    for rnd in range(3):
        nadd = 0
        newly = []
        for a in list(unmatched_a):
            dsa = FA[a][2]
            if not dsa or FA[a][4] > 40: continue
            exp = [interp(x) for x in set(dsa)]
            exp = [e for e in exp if e is not None]
            if not exp: continue
            cands = None
            for e in exp:
                cs = set()
                for dev in (0, 4, -4, 8, -8, 0x10, -0x10):
                    cs.update(bidx.get(e + dev, ()))
                cands = cs if cands is None else (cands & cs)
                if cands is not None and not cands: break
            if not cands: continue
            if len(cands) == 1:
                b = next(iter(cands))
                if FB[b][4] <= 64:
                    match[a] = b; used_b.add(b)
                    unmatched_a.discard(a); unmatched_b.discard(b)
                    newly.append((a, b)); nadd += 1
        # 增量更新插值器 (并入新对)
        for a, b in newly:
            da_ = FA[a][2]; db_ = FB[b][2]
            if da_ and db_ and len(da_) == len(db_):
                for xa, yb in zip(da_, db_):
                    i = bs.bisect_right(ixs, xa)
                    if i > 0 and (xa, yb) not in ded:
                        ded.insert(i, (xa, yb)); ixs.insert(i, xa); iys.insert(i, yb)
        print(f"  accessor round{rnd}: +{nadd} (total {len(match)})", flush=True)
        if not nadd: break

    # ---- 二次区域对齐 (LIS 链重建, 全间隔, 双阈值) ----
    print("re-alignment ...", flush=True)
    la2 = sorted(FA); lb2 = sorted(FB)
    ia2 = {a: i for i, a in enumerate(la2)}
    ib2 = {b: i for i, b in enumerate(lb2)}
    pts = sorted(((a, b) for a, b in match.items()))
    chain = [(ia2[pts[k][0]], ib2[pts[k][1]]) for k in lis_chain(pts)]
    print(f"  chain: {len(chain)}", flush=True)
    ua_sorted = sorted(unmatched_a, key=lambda x: ia2[x])
    ub_sorted = sorted(unmatched_b, key=lambda x: ib2[x])
    def score(x, y, eo):
        clx, lhx, sx = FA[x][1], FA[x][3], FA[x][4]
        cly, lhy, sy = FB[y][1], FB[y][3], FB[y][4]
        s = 0.0
        sety = set(cly)
        common = sum(1 for c in clx if match.get(c) in sety)
        s += min(common, 6) * 2.0
        s += lh_jac(lhx, lhy) * 4.0
        if sx and sy:
            r = sx / sy
            if 0.75 <= r <= 1.33: s += 1.0
            elif not (0.4 <= r <= 2.5): s -= 2.0
        if eo is not None:
            dev = abs((y - x) - eo)
            if dev < 0x4000: s += 2.0
            elif dev > 0x300000: s -= 3.0
        return s
    added = 0
    for k in range(len(chain) - 1):
        alo, ahi = chain[k][0], chain[k + 1][0]
        blo, bhi = chain[k][1], chain[k + 1][1]
        a_seg = [a for a in ua_sorted if alo < ia2[a] < ahi]
        b_seg = [b for b in ub_sorted if blo < ib2[b] < bhi]
        if not a_seg or not b_seg: continue
        eo = lb2[blo] - la2[alo]
        if ahi - alo > 6000 or bhi - blo > 6000:
            eo = None   # 大间隔: 放弃偏移先验但保留对齐
        i = j = 0
        while i < len(a_seg) and j < len(b_seg):
            x, y = a_seg[i], b_seg[j]
            s = score(x, y, eo)
            if s >= 4.0:
                match[x] = y; used_b.add(y)
                unmatched_a.discard(x); unmatched_b.discard(y)
                added += 1; i += 1; j += 1
            else:
                if FA[x][4] <= FB[y][4]: i += 1
                else: j += 1
    print(f"  re-alignment added {added} (total {len(match)})", flush=True)

    # ---- 输出 ----
    nA, nB = len(FA), len(FB)
    a1_only = [a for a in la if a not in match]
    m2_only = [b for b in lb if b not in used_b]
    print(f"\n===== R3b 结果 =====")
    print(f"配对 {len(match)} ({len(match)/nA*100:.1f}% / {len(match)/nB*100:.1f}%)")
    print(f"a1_only {len(a1_only)}  a1m2_only {len(m2_only)}")
    with open(OUT, "w") as f:
        f.write("class\ta1_addr\ta1m2_addr\tnote\n")
        for a, b in sorted(match.items()):
            f.write(f"matched\t{a:x}\t{b:x}\t{FA[a][0]}|{FB[b][0]}\n")
        for a in a1_only:
            f.write(f"a1_only\t{a:x}\t\t{FA[a][0]}\n")
        for b in m2_only:
            f.write(f"a1m2_only\t\t{b:x}\t{FB[b][0]}\n")
    print(f"wrote {OUT}")

if __name__ == '__main__':
    main()
