#!/usr/bin/env python3
"""diff_appfw_r3.py — 第三轮: 数据引用翻译 + 窗口约束匹配 + 区域单调对齐 → 收敛到全覆盖
输入: appfw_diff_summary_v2.tsv 的 matched 集作为锚
方法:
  ① 由锚建 数据引用翻译表 (DAT_/s_/u_ token 对应投票)
  ② 小函数/访问器: 签名(数据引用+调用, 经翻译表映射到对侧空间) + 偏移窗口 → 唯一候选即配对 (迭代扩表)
  ③ 其余: 按锚点分区间, 带期望偏移的单调两指针对齐 (尺寸/行集/调用重合计分)
  ④ 输出全量四类 + 置信标签
"""
import re, sys, collections, hashlib, bisect

A1   = "<workspace>/firmware_reverse/decompiled/a1_appfw.c"
A1M2 = "<workspace>/firmware_reverse/decompiled/a1m2_appfw.c"
TSV_IN  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v2.tsv"
OUT  = "<workspace>/a1m2_ai_pipeline/appfw_diff_summary_v3.tsv"

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
                datas += TOKD.findall(ln)
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

    # ---- 偏移链: 真 LIS (耐心排序), 鲁棒于离群锚 ----
    print("offset chain (LIS) ...", flush=True)
    spts = sorted(match.items())
    # patience LIS on b (a 已升序)
    tails = []          # tails[k] = LIS 长度 k+1 的最小 b
    tails_idx = []      # 对应 (a_idx, b_idx)
    prev_ptr = []
    import bisect as bs
    for k, (a, b) in enumerate(spts):
        pos = bs.bisect_left(tails, b)
        if pos == len(tails):
            tails.append(b); tails_idx.append((k, -1))
        else:
            tails[pos] = b; tails_idx[pos] = (k, -1)
        prev_ptr.append(tails_idx[pos - 1][0] if pos > 0 else -1)
    # 回溯 LIS
    chain_pts = []
    k = tails_idx[len(tails) - 1][0]
    while k >= 0:
        chain_pts.append(spts[k]); k = prev_ptr[k]
    chain_pts.reverse()
    chain = [(ia[a], ib[b]) for a, b in chain_pts]
    print(f"  LIS chain: {len(chain)} landmarks (of {len(spts)} anchors)", flush=True)

    # ---- ① 数据引用翻译表 ----
    print("data map ...", flush=True)
    dmap_votes = collections.Counter()
    for a, b in list(match.items())[::2]:   # 采样一半, 控制票量
        da = FA[a][2]; db = FB[b][2]
        if not da or not db or len(da) != len(db): continue
        for ta, tb in zip(da, db):
            if ta != tb: dmap_votes[(ta, tb)] += 1
    dmap = {}
    for (ta, tb), v in dmap_votes.items():
        if v >= 2 and ta not in dmap: dmap[ta] = tb
    print(f"  data tokens mapped: {len(dmap)}", flush=True)

    def translate_a1(tokens):
        return tuple(dmap.get(t, t) for t in tokens)

    # ---- ③ 区间单调对齐 ----
    print("region alignment ...", flush=True)
    unmatched_a = [a for a in la if a not in match]
    unmatched_b = [b for b in lb if b not in used_b]
    ua_idx = {a: ia[a] for a in unmatched_a}
    ub_idx = {b: ib[b] for b in unmatched_b}
    ua_sorted = sorted(unmatched_a, key=lambda x: ia[x])
    ub_sorted = sorted(unmatched_b, key=lambda x: ib[x])
    def score(x, y, eo):
        clx, lhx, sx = FA[x][1], FA[x][3], FA[x][4]
        cly, lhy, sy = FB[y][1], FB[y][3], FB[y][4]
        s = 0.0
        common = 0
        sety = set(cly)
        for c in clx:
            mc = match.get(c)
            if mc is not None and mc in sety: common += 1
        s += min(common, 6) * 2.0
        s += lh_jac(lhx, lhy) * 4.0
        if sx and sy:
            r = sx / sy
            if 0.75 <= r <= 1.33: s += 1.0
            elif not (0.4 <= r <= 2.5): s -= 2.0
        if eo is not None:
            dev = abs((y - x) - eo)
            if dev < 0x4000: s += 1.5
            elif dev > 0x300000: s -= 3.0
        return s
    chain_a_idx = [x[0] for x in chain]
    added = 0
    for k in range(len(chain) - 1):
        alo, ahi = chain[k][0], chain[k + 1][0]
        blo, bhi = chain[k][1], chain[k + 1][1]
        if ahi - alo > 4000 or bhi - blo > 4000: continue   # 异常大间隔跳过(防错链拖累)
        a_seg = [a for a in ua_sorted if alo < ia[a] < ahi]
        b_seg = [b for b in ub_sorted if blo < ib[b] < bhi]
        if not a_seg or not b_seg: continue
        eo = lb[blo] - la[alo]
        i = j = 0
        while i < len(a_seg) and j < len(b_seg):
            x, y = a_seg[i], b_seg[j]
            s = score(x, y, eo)
            if s >= 4.5:
                match[x] = y; used_b.add(y); added += 1
                i += 1; j += 1
            else:
                if FA[x][4] <= FB[y][4]: i += 1
                else: j += 1
    print(f"  alignment added {added} (total {len(match)})", flush=True)

    # ---- ② 小函数/访问器: 签名匹配 (迭代) ----
    print("signature pass ...", flush=True)
    unmatched_a = [a for a in la if a not in match]
    unmatched_b = [b for b in lb if b not in used_b]
    # a1m2 签名索引: (calls 签名, datas 签名)
    def sigb(calls, datas):
        return (tuple(calls), tuple(datas))
    idx_b = collections.defaultdict(list)
    for b in unmatched_b:
        _, cl, dt, _, sz = FB[b]
        if sz <= 40:
            idx_b[sigb(cl, dt)].append(b)
    added = 0
    ua_set = set(unmatched_a)
    # 期望偏移查询
    chain_a = [x[0] for x in chain]
    chain_off = {}
    for ka, kb in chain:
        chain_off[ka] = la[ka] and (lb[kb] - la[ka])
    chain_offs = sorted(chain_off.items())
    def expect_off(a):
        i = bisect.bisect_right([x[0] for x in chain_offs], a) - 1
        if i < 0: return None
        return chain_offs[i][1]
    ub_set = set(unmatched_b)
    for rnd in range(4):
        nadd = 0
        newly = []
        for a in unmatched_a:
            if a not in ua_set: continue
            na, cl, dt, _, sz = FA[a]
            if sz > 40: continue
            tcalls = tuple(match.get(c, -c) for c in cl)   # 未匹配 callee 用负地址占位(对侧无对应)
            tdatas = translate_a1(dt)
            key = (tcalls, tdatas)
            cands = [b for b in idx_b.get(key, ()) if b in ub_set]
            if len(cands) == 1:
                b = cands[0]
                o = expect_off(a)
                if o is None or abs((b - a) - o) < 0x200000:
                    match[a] = b; used_b.add(b); ub_set.discard(b); ua_set.discard(a)
                    newly.append((a, b)); nadd += 1
        # 扩数据翻译表
        for a, b in newly:
            da = FA[a][2]; db = FB[b][2]
            if da and db and len(da) == len(db):
                for ta, tb in zip(da, db):
                    if ta != tb and ta not in dmap: dmap[ta] = tb
        print(f"  sig round{rnd}: +{nadd} (total {len(match)})", flush=True)
        if not nadd: break

    # ---- ④ 输出 ----
    nA, nB = len(FA), len(FB)
    a1_only = [a for a in la if a not in match]
    m2_only = [b for b in lb if b not in used_b]
    print(f"\n===== R3 结果 =====")
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

def statistics_median(seq):
    s = sorted(seq)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

if __name__ == '__main__':
    main()
