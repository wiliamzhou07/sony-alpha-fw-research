#!/usr/bin/env python3
"""diff_appfw_r2.py — a1/a1m2 appFw 函数级差分 第二轮引擎
输入: appfw_diff_summary.tsv 中 identical/modified 锚点 + 两个全量反编译 .c
方法: ① 调用图传播 (callee/caller 投票, 迭代到不动点)
      ② 地标序列对齐 (已配对锚点之间的未匹配函数做单调对齐, 尺寸+行集+callee重合计分)
输出: appfw_diff_summary_v2.tsv + 覆盖率统计
"""
import re, sys, collections, hashlib

A1   = "<workspace>/firmware_reverse/decompiled/a1_appfw.c"
A1M2 = "<workspace>/firmware_reverse/decompiled/a1m2_appfw.c"
TSV  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary.tsv"
OUT  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v2.tsv"

HDR = re.compile(r"^// ==== (FUN_[0-9a-f]+) @ ([0-9a-fA-F]+) ====")
CALL = re.compile(r'\b(?:thunk_)?FUN_[0-9a-f]{6,}')
MASK = re.compile(r'\b(FUN|DAT|_DAT|s|u|UNK|thunk_FUN)_[0-9a-fA-F]{6,}\b')
ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')

def parse(path):
    """流式: (addr, name, callees[list], lh[set[int] 行哈希], nlines)"""
    cur_name, cur_addr, cur, callees = None, None, [], []
    with open(path, "r", errors="replace") as f:
        for ln in f:
            m = HDR.match(ln.rstrip("\n"))
            if m:
                if cur_name is not None:
                    yield cur_addr, cur_name, callees, cur
                cur_name, cur_addr, cur, callees = m.group(1), int(m.group(2), 16), [], []
            elif cur_name is not None:
                for mm in CALL.finditer(ln):
                    callees.append(int(mm.group(0).split('_')[-1], 16))
                cur.append(ln)
    if cur_name is not None:
        yield cur_addr, cur_name, callees, cur

def line_hashes(lines, minlen=16):
    out = set()
    for ln in lines:
        t = MASK.sub('X', ln)
        t = ADDR.sub('0xA', t)
        t = re.sub(r'\s+', ' ', t).strip()
        if len(t) >= minlen:
            out.add(int.from_bytes(hashlib.blake2b(t.encode(), digest_size=8).digest(), 'big'))
    return out

def lh_jac(ha, hb):
    if not ha or not hb: return 0.0
    return len(ha & hb) / len(ha | hb)

def load(path):
    funcs = {}
    n = 0
    for addr, name, callees, body in parse(path):
        lh = line_hashes(body) if len(body) >= 6 else set()
        funcs[addr] = [name, callees, lh, len(body)]
        n += 1
        if n % 50000 == 0: print(f"  {n} ...", flush=True)
    return funcs

def main():
    print("loading anchors ...", flush=True)
    anchors = {}
    for ln in open(TSV):
        p = ln.rstrip('\n').split('\t')
        if p[0] in ('identical', 'modified') and p[1] and p[3]:
            anchors[int(p[1], 16)] = int(p[3], 16)
    print(f"  {len(anchors)} anchor pairs", flush=True)

    print("parsing a1 ...", flush=True);   FA = load(A1)
    print(f"  {len(FA)} funcs", flush=True)
    print("parsing a1m2 ...", flush=True); FB = load(A1M2)
    print(f"  {len(FB)} funcs", flush=True)

    match = dict(anchors)          # a1_addr -> a1m2_addr
    used_b = set(match.values())

    # 倒排: callee -> 调用者
    cal_A = collections.defaultdict(list)
    cal_B = collections.defaultdict(list)
    for a, (_, cl, _, _) in FA.items():
        for c in set(cl): cal_A[c].append(a)
    for b, (_, cl, _, _) in FB.items():
        for c in set(cl): cal_B[c].append(b)

    # ============ ① 调用图传播 ============
    print("propagation ...", flush=True)
    MAXV = 48   # 枢纽(调用者/被调者过多)不产票: 它们靠行哈希匹配, 且票生成会爆炸
    for it in range(12):
        votes = {}
        # callee 边投票: matched(a->b) 的 callee 对 (跳过枢纽锚)
        for a, b in match.items():
            ca = FA[a][1]; cb = FB[b][1]
            if not ca or not cb: continue
            seta = {x for x in ca if x != a and x in FA and len(cal_A[x]) <= MAXV}
            setb = {y for y in cb if y != b and y in FB and len(cal_B[y]) <= MAXV}
            if not seta or not setb: continue
            for x in seta:
                if x in match: continue
                for y in setb:
                    if y in used_b: continue
                    k = (x, y)
                    votes[k] = votes.get(k, 0) + 1
        # caller 边投票
        for a, b in match.items():
            xs = [x for x in cal_A[a] if x in FA and len(FA[x][1]) <= 96 and x not in match]
            ys = [y for y in cal_B[b] if y in FB and len(FB[y][1]) <= 96 and y not in used_b]
            if len(xs) > 32 or len(ys) > 32: continue   # 枢纽锚跳过
            for x in xs:
                for y in ys:
                    k = (x, y)
                    votes[k] = votes.get(k, 0) + 1
        added = 0
        for (x, y), v in sorted(votes.items(), key=lambda t: -t[1]):
            if v < 2: break
            if x in match or y in used_b: continue
            sa, sb = FA[x][3], FB[y][3]
            if sa and sb and not (0.33 <= sa / sb <= 3.0): continue
            match[x] = y; used_b.add(y); added += 1
        print(f"  iter{it}: votes={len(votes)} +{added} (total {len(match)})", flush=True)
        if not added: break

    # ============ ② 地标序列对齐 ============
    print("landmark alignment ...", flush=True)
    la = sorted(FA.keys())
    lb = sorted(FB.keys())
    ia = {a: i for i, a in enumerate(la)}
    ib = {b: i for i, b in enumerate(lb)}
    # 锚点按 a1 地址排序, 过滤掉 a1m2 侧非单调的锚 (LIS 简化: 直接丢制造逆序的)
    pts = sorted(((a, b) for a, b in match.items()), key=lambda t: t[0])
    land_a, land_b = [], []
    lastb = -1
    for a, b in pts:
        if b > lastb:
            land_a.append(ia[a]); land_b.append(ib[b]); lastb = b
    print(f"  monotonic landmarks: {len(land_a)}", flush=True)

    # 未匹配序列
    unmatched_a = [a for a in la if a not in match]
    unmatched_b = [b for b in lb if b not in used_b]

    def score(x, y):
        _, clx, lhx, sx = FA[x]
        _, cly, lhy, sy = FB[y]
        # callee 重合 (两侧的 callee 中已被配对的)
        common = 0
        for c in clx:
            if c in match and match[c] in set(cly): common += 1
        s = common * 3.0
        j = lh_jac(lhx, lhy)
        s += j * 4.0
        if sx and sy:
            r = sx / sy
            if 0.75 <= r <= 1.33: s += 1.0
            elif not (0.5 <= r <= 2.0): s -= 1.5
        return s

    # 区间对齐: 地标 i..i+1 之间的未匹配函数
    import bisect
    def align_interval(a_list, b_list):
        """两指针单调对齐, 接受 score>=4.0 的 1:1 对"""
        nadd = 0
        i = j = 0
        while i < len(a_list) and j < len(b_list):
            x, y = a_list[i], b_list[j]
            s = score(x, y)
            if s >= 4.0:
                match[x] = y; used_b.add(y); nadd += 1
                i += 1; j += 1
            else:
                # 跳过较小者 (插入/删除), 用尺寸差决定
                if FA[x][3] <= FB[y][3]: i += 1
                else: j += 1
        return nadd

    # 分区间
    bounds = land_a
    added_total = 0
    for k in range(len(bounds) - 1):
        alo, ahi = bounds[k], bounds[k + 1]
        blo, bhi = land_b[k], land_b[k + 1]
        a_seg = [a for a in unmatched_a if alo < ia[a] < ahi]
        b_seg = [b for b in unmatched_b if blo < ib[b] < bhi]
        if not a_seg or not b_seg: continue
        added_total += align_interval(a_seg, b_seg)
    print(f"  alignment added {added_total} (total {len(match)})", flush=True)

    # ============ 输出 ============
    nA, nB = len(FA), len(FB)
    ident = mod = 0
    rows = []
    for a, b in match.items():
        na, cla, lha, sa = FA[a]
        nb, clb, lhb, sb = FB[b]
        # 粗分: 行集完全同 → identical
        cls = 'matched'
        rows.append((a, na, b, nb, cls))
    a1_only = [a for a in la if a not in match]
    m2_only = [b for b in lb if b not in used_b]
    print(f"\n===== R2 结果 =====")
    print(f"a1 {nA} / a1m2 {nB}")
    print(f"配对 {len(match)} ({len(match)/nA*100:.1f}% / {len(match)/nB*100:.1f}%)")
    print(f"未配对: a1 {len(a1_only)} (new/rem 候选)  a1m2 {len(m2_only)}")
    with open(OUT, "w") as f:
        f.write("class\ta1_addr\ta1m2_addr\tnote\n")
        for a, na, b, nb, cls in sorted(rows):
            f.write(f"{cls}\t{a:x}\t{b:x}\t\n")
        for a in a1_only:
            f.write(f"a1_only\t{a:x}\t\t{FA[a][0]}\n")
        for b in m2_only:
            f.write(f"a1m2_only\t\t{b:x}\t{FB[b][0]}\n")
    print(f"wrote {OUT}")

if __name__ == '__main__':
    main()
