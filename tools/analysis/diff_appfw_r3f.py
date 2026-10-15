#!/usr/bin/env python3
"""diff_appfw_r3e.py — 收官: 区间内贪心最优对(非单调, 边际约束) + 数据插值特征 → v7 + 最终分类
"""
import re, sys, collections, hashlib, bisect as bs

A1   = "<workspace>/firmware_reverse/decompiled/a1_appfw.c"
A1M2 = "<workspace>/firmware_reverse/decompiled/a1m2_appfw.c"
TSV_IN  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v7.tsv"
OUT  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v8.tsv"

HDR  = re.compile(r"^// ==== (FUN_[0-9a-f]+) @ ([0-9a-fA-F]+) ====")
TOKC = re.compile(r'\b(?:thunk_)?FUN_[0-9a-f]{6,}')
TOKD = re.compile(r'\b(?:_?DAT|s|u)_[0-9a-f]{6,}')
MASK = re.compile(r'\b(FUN|DAT|_DAT|s|u|UNK|thunk_FUN)_[0-9a-fA-F]{6,}\b')
ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')
CST  = re.compile(r'\b0x[0-9a-fA-F]{1,4}\b')

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
    tails, tidx, prev = [], [], []
    for k, (_, kb) in enumerate(pts):
        pos = bs.bisect_left(tails, kb)
        if pos == len(tails): tails.append(kb); tidx.append(k)
        else: tails[pos] = kb; tidx[pos] = k
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

    # 数据插值器 (复用 r3b 逻辑)
    pts = []
    step = max(1, len(match) // 60000)
    for a, b in list(match.items())[::step]:
        da_ = FA[a][2]; db_ = FB[b][2]
        if da_ and db_ and len(da_) == len(db_):
            for xa, yb in zip(da_, db_): pts.append((xa, yb))
    pts.sort()
    pts = [pts[k] for k in lis_chain(pts)]
    ded = []
    for xa, yb in pts:
        if ded and ded[-1][0] == xa: continue
        ded.append((xa, yb))
    ixs = [p[0] for p in ded]
    def interp(x):
        i = bs.bisect_right(ixs, x) - 1
        if i < 0 or i >= len(ded) - 1: return None
        x0, y0 = ded[i]; x1, y1 = ded[i + 1]
        if x1 == x0: return y0
        return int(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    print(f"  interp anchors: {len(ded)}", flush=True)

    unmatched_a = [a for a in la if a not in match]
    unmatched_b = [b for b in lb if b not in used_b]
    print(f"  unmatched: a1 {len(unmatched_a)} / a1m2 {len(unmatched_b)}", flush=True)

    # LIS 链 + 区间
    pts2 = sorted(((a, b) for a, b in match.items()))
    chain = [(ia[pts2[k][0]], ib[pts2[k][1]]) for k in lis_chain(pts2)]
    print(f"  chain: {len(chain)}", flush=True)

    def feats_score(x, y, eo):
        clx, dtx, lhx, sx = FA[x][1], FA[x][2], FA[x][3], FA[x][4]
        cly, dty, lhy, sy = FB[y][1], FB[y][2], FB[y][3], FB[y][4]
        s = 0.0
        sety = set(cly)
        common = sum(1 for c in clx if match.get(c) in sety)
        s += min(common, 6) * 2.0
        s += lh_jac(lhx, lhy) * 4.0
        # 数据引用: 翻译后重合
        if dtx and dty:
            ea = [interp(v) for v in dtx]
            ea = [e for e in ea if e is not None]
            if ea:
                setb = set(dty)
                hit = sum(1 for e in ea if any(abs(e - w) <= 0x20 for w in setb))
                s += 2.0 * hit / len(ea)
        if sx and sy:
            r = sx / sy
            if 0.75 <= r <= 1.33: s += 1.0
            elif not (0.4 <= r <= 2.5): s -= 2.0
        if eo is not None:
            dev = abs((y - x) - eo)
            if dev < 0x8000: s += 2.0
            elif dev > 0x400000: s -= 3.0
        return s

    print("greedy best-pair within intervals ...", flush=True)
    added = 0
    ua_set = set(unmatched_a); ub_set = set(unmatched_b)
    for k in range(len(chain) - 1):
        alo, ahi = chain[k][0], chain[k + 1][0]
        blo, bhi = chain[k][1], chain[k + 1][1]
        a_seg = sorted([a for a in unmatched_a if alo < ia[a] < ahi])
        b_seg = sorted([b for b in unmatched_b if blo < ib[b] < bhi])
        if not a_seg or not b_seg: continue
        o0 = lb[blo] - la[alo]; o1 = lb[bhi] - la[ahi]
        pairs = []
        for x in a_seg:
            if len(pairs) > 60000: break
            fr = (ia[x] - alo) / max(1, ahi - alo)
            eo = int(o0 + (o1 - o0) * fr)
            # 只在期望偏移 ±256KB 窗内找候选
            ylo = x + eo - 0x40000; yhi = x + eo + 0x40000
            jlo = bs.bisect_left(b_seg, ylo); jhi = bs.bisect_right(b_seg, yhi)
            best = None
            for y in b_seg[max(0, jlo - 8):min(len(b_seg), jhi + 8)]:
                s = feats_score(x, y, eo)
                if best is None or s > best[0]: best = (s, y)
            if best and best[0] >= 3.0:
                pairs.append((best[0], x, best[1]))
        pairs.sort(reverse=True)
        for s, x, y in pairs:
            if x in ua_set and y in ub_set:
                # 边际检查略(分高者优先自然满足唯一性)
                match[x] = y; used_b.add(y)
                ua_set.discard(x); ub_set.discard(y); added += 1
    print(f"  greedy added {added} (total {len(match)})", flush=True)

    nA, nB = len(FA), len(FB)
    a1_only = [a for a in la if a not in match]
    m2_only = [b for b in lb if b not in used_b]
    print(f"\n===== R3e 结果 =====")
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
