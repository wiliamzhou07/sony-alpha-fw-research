#!/usr/bin/env python3
"""diff_appfw_r3d.py — 密集锚传播收敛 (唯一边直配 + 投票) + 收尾对齐 → v6
"""
import re, sys, collections, hashlib, bisect as bs

A1   = "<workspace>/firmware_reverse/decompiled/a1_appfw.c"
A1M2 = "<workspace>/firmware_reverse/decompiled/a1m2_appfw.c"
TSV_IN  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v5.tsv"
OUT  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v6.tsv"

HDR  = re.compile(r"^// ==== (FUN_[0-9a-f]+) @ ([0-9a-fA-F]+) ====")
TOKC = re.compile(r'\b(?:thunk_)?FUN_[0-9a-f]{6,}')
MASK = re.compile(r'\b(FUN|DAT|_DAT|s|u|UNK|thunk_FUN)_[0-9a-fA-F]{6,}\b')
ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')

def parse(path):
    cur_name, cur_addr, calls, body = None, None, [], []
    with open(path, "r", errors="replace") as f:
        for ln in f:
            m = HDR.match(ln.rstrip("\n"))
            if m:
                if cur_name is not None:
                    yield cur_addr, cur_name, calls, body
                cur_name, cur_addr, calls, body = m.group(1), int(m.group(2), 16), [], []
            elif cur_name is not None:
                calls += [int(x.split('_')[-1], 16) for x in TOKC.findall(ln)]
                body.append(ln)
    if cur_name is not None:
        yield cur_addr, cur_name, calls, body

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
    for addr, name, calls, body in parse(path):
        F[addr] = [name, calls, line_hashes(body) if len(body) >= 6 else set(), len(body)]
        n += 1
        if n % 50000 == 0: print(f"  {n} ...", flush=True)
    return F

def lh_jac(ha, hb):
    if not ha or not hb: return 0.0
    return len(ha & hb) / len(ha | hb)

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

    cal_A = collections.defaultdict(list)
    cal_B = collections.defaultdict(list)
    for a, (_, cl, _, _) in FA.items():
        for c in set(cl):
            if c in FA: cal_A[c].append(a)
    for b, (_, cl, _, _) in FB.items():
        for c in set(cl):
            if c in FB: cal_B[c].append(b)

    def sane(x, y):
        sa, sb = FA[x][3], FB[y][3]
        if sa and sb and not (0.4 <= sa / sb <= 2.5): return False
        return True

    print("dense propagation ...", flush=True)
    for it in range(15):
        added = 0
        # --- 规则1: 唯一未配对 callee/caller 直配 ---
        for a, b in list(match.items())[:]:
            ca = [x for x in FA[a][1] if x in FA and x not in match]
            cb = [y for y in FB[b][1] if y in FB and y not in used_b]
            if len(set(ca)) == 1 and len(set(cb)) == 1:
                x, y = ca[0], cb[0]
                if x not in match and y not in used_b and sane(x, y):
                    match[x] = y; used_b.add(y); added += 1
                    continue
            ra = [x for x in cal_A[a] if x not in match]
            rb = [y for y in cal_B[b] if y not in used_b]
            if len(set(ra)) == 1 and len(set(rb)) == 1:
                x, y = ra[0], rb[0]
                if x not in match and y not in used_b and sane(x, y):
                    match[x] = y; used_b.add(y); added += 1
        # --- 规则2: 投票 (callee+caller, 非枢纽) ---
        votes = {}
        MAXV = 64
        for a, b in match.items():
            ca = {x for x in FA[a][1] if x in FA and x not in match and len(cal_A[x]) <= MAXV}
            cb = {y for y in FB[b][1] if y in FB and y not in used_b and len(cal_B[y]) <= MAXV}
            for x in ca:
                if len(ca) > 24 or len(cb) > 24: break
                for y in cb:
                    k = (x, y); votes[k] = votes.get(k, 0) + 1
            ra = [x for x in cal_A[a] if x not in match and len(FA[x][1]) <= 96]
            rb = [y for y in cal_B[b] if y not in used_b and len(FB[y][1]) <= 96]
            if 0 < len(ra) <= 16 and 0 < len(rb) <= 16:
                for x in ra:
                    for y in rb:
                        k = (x, y); votes[k] = votes.get(k, 0) + 1
        # 期望偏移
        pts = sorted(((a, b) for a, b in match.items()))
        tails, tidx, prev = [], [], []
        for k, (_, kb) in enumerate(pts):
            pos = bs.bisect_left(tails, kb)
            if pos == len(tails): tails.append(kb); tidx.append(k)
            else: tails[pos] = kb; tidx[pos] = k
            prev.append(tidx[pos - 1] if pos > 0 else -1)
        ci = tidx[-1] if tidx else -1
        chain = []
        while ci >= 0:
            chain.append(pts[ci]); ci = prev[ci]
        chain.reverse()
        cxs = [la.index(a) if False else a for a, _ in chain]  # a 值
        offs = [b - a for a, b in chain]
        def expect_off(a):
            i = bs.bisect_right(cxs, a) - 1
            if i < 0 or i >= len(cxs) - 1: return None
            # 线性插值偏移
            a0, a1v = cxs[i], cxs[i + 1]
            o0, o1 = offs[i], offs[i + 1]
            if a1v == a0: return o0
            return int(o0 + (o1 - o0) * (a - a0) / (a1v - a0))
        acc = []
        for (x, y), v in votes.items():
            if v < 1: continue
            if x in match or y in used_b: continue
            eo = expect_off(x)
            ok = False
            if v >= 2: ok = True
            elif eo is not None and abs((y - x) - eo) < 0x60000: ok = True
            if ok and sane(x, y): acc.append((v, abs((y - x) - (eo or 0)), x, y))
        acc.sort(reverse=True)
        nv = 0
        for v, dev, x, y in acc:
            if x in match or y in used_b: continue
            match[x] = y; used_b.add(y); nv += 1
        added += nv
        print(f"  iter{it}: unique-edge+votes +{added} (total {len(match)})", flush=True)
        if added == 0: break

    # --- 收尾顺序对齐 ---
    print("final alignment ...", flush=True)
    unmatched_a = [a for a in la if a not in match]
    unmatched_b = [b for b in lb if b not in used_b]
    ia = {a: i for i, a in enumerate(la)}
    ib = {b: i for i, b in enumerate(lb)}
    pts = sorted(((a, b) for a, b in match.items()))
    tails, tidx, prev = [], [], []
    for k, (_, kb) in enumerate(pts):
        pos = bs.bisect_left(tails, kb)
        if pos == len(tails): tails.append(kb); tidx.append(k)
        else: tails[pos] = kb; tidx[pos] = k
        prev.append(tidx[pos - 1] if pos > 0 else -1)
    ci = tidx[-1] if tidx else -1
    chain = []
    while ci >= 0:
        chain.append((ia[pts[ci][0]], ib[pts[ci][1]])); ci = prev[ci]
    chain.reverse()
    print(f"  chain: {len(chain)}", flush=True)
    ua_sorted = sorted(unmatched_a, key=lambda x: ia[x])
    ub_sorted = sorted(unmatched_b, key=lambda x: ib[x])
    def score(x, y, eo):
        clx, lhx, sx = FA[x][1], FA[x][2], FA[x][3]
        cly, lhy, sy = FB[y][1], FB[y][2], FB[y][3]
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
            if dev < 0x8000: s += 2.0
            elif dev > 0x400000: s -= 3.0
        return s
    added = 0
    for k in range(len(chain) - 1):
        alo, ahi = chain[k][0], chain[k + 1][0]
        blo, bhi = chain[k][1], chain[k + 1][1]
        a_seg = [a for a in ua_sorted if alo < ia[a] < ahi]
        b_seg = [b for b in ub_sorted if blo < ib[b] < bhi]
        if not a_seg or not b_seg: continue
        o0 = lb[blo] - la[alo]; o1 = lb[bhi] - la[ahi]
        i = j = 0
        while i < len(a_seg) and j < len(b_seg):
            x, y = a_seg[i], b_seg[j]
            fr = (ia[x] - alo) / max(1, ahi - alo)
            eo = int(o0 + (o1 - o0) * fr)
            s = score(x, y, eo)
            cly_s = set(FB[y][1])
            strong = any(match.get(c) in cly_s for c in FA[x][1]) or lh_jac(FA[x][2], FB[y][2]) >= 0.4
            if s >= (3.5 if strong else 5.0):
                match[x] = y; used_b.add(y); added += 1
                i += 1; j += 1
            else:
                if FA[x][3] <= FB[y][3]: i += 1
                else: j += 1
    print(f"  final alignment +{added} (total {len(match)})", flush=True)

    nA, nB = len(FA), len(FB)
    a1_only = [a for a in la if a not in match]
    m2_only = [b for b in lb if b not in used_b]
    print(f"\n===== R3d 结果 =====")
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
