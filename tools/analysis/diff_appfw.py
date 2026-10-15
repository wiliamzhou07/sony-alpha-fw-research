#!/usr/bin/env python3
"""diff_appfw.py — a1/a1m2 appFw 反编译产物的函数级差分
匹配: 字符串锚(Jaccard) → 数值常量签名 → 规模; 输出四类:
  identical / modified / a1_only / a1m2_only
产物: appfw_diff_summary.tsv + appfw_diff_modified.tsv(前 N 详细) + stdout 摘要
"""
import re, sys, collections, difflib

A1  = "<workspace>/firmware_reverse/decompiled/a1_appfw.c"
A1M2 = "<workspace>/firmware_reverse/decompiled/a1m2_appfw.c"
OUT_DIR = "<workspace>/a1m2_ai_pipeline"

HDR = re.compile(r"^// ==== (FUN_[0-9a-f]+) @ ([0-9a-fA-F]+) ====")
STR = re.compile(r'"((?:[^"\\]|\\.)*)"')
MASK = re.compile(r'\b(FUN|DAT|_DAT|s|u|UNK|thunk_FUN)_[0-9a-fA-F]{6,}\b')
ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')
CONST = re.compile(r'\b(0x[0-9a-fA-F]{1,6}|-?[0-9]{2,7})\b')

def parse(path):
    """生成器: 流式产出 (addr, name, body_lines)，控制峰值内存"""
    cur_name, cur_addr, cur = None, None, []
    with open(path, "r", errors="replace") as f:
        for ln in f:
            m = HDR.match(ln.rstrip("\n"))
            if m:
                if cur_name is not None:
                    yield cur_addr, cur_name, cur
                cur_name, cur_addr, cur = m.group(1), int(m.group(2), 16), []
            elif cur_name is not None:
                cur.append(ln)
    if cur_name is not None:
        yield cur_addr, cur_name, cur

def norm_body(lines):
    """掩蔽地址符号后压缩空白 → 跨版本可比指纹文本"""
    out = []
    for ln in lines:
        t = MASK.sub(r'\1_X', ln)
        t = ADDR.sub('0xA', t)
        t = re.sub(r'\s+', ' ', t).strip()
        if t: out.append(t)
    return out

def feats(body_lines):
    strs = set()
    consts = collections.Counter()
    for ln in body_lines:
        for m in STR.finditer(ln):
            t = m.group(1)
            if len(t) >= 6: strs.add(t)
        for m in CONST.finditer(ln):
            t = m.group(1)
            try:
                v = int(t, 0)
            except ValueError:
                try: v = int(t, 10)
                except ValueError: continue
            if 0x100 <= (v & 0xFFFFFFFF) <= 0xFFFFFF or 100 <= v <= 999999:  # 有区分度的量级
                consts[v] += 1
    return strs, consts

def load(path):
    """流式: 返回 [(addr, name, strs, consts, normlines)]，丢弃原始体"""
    out = []
    n = 0
    for addr, name, body in parse(path):
        s, c = feats(body)
        out.append((addr, name, s, c, norm_body(body)))
        n += 1
        if n % 50000 == 0: print(f"  {n} ...", flush=True)
    return out

def main():
    nmax = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    print("parsing a1 ...", flush=True)
    A = load(A1)
    print(f"  {len(A)} funcs", flush=True)
    print("parsing a1m2 ...", flush=True)
    B = load(A1M2)
    print(f"  {len(B)} funcs", flush=True)

    Af = [(s, c, nb) for _, _, s, c, nb in A]
    Bf = [(s, c, nb) for _, _, s, c, nb in B]

    # ---- Stage 1: 字符串锚匹配 (一对多时取 Jaccard 最高, 贪心一对一) ----
    print("stage1: string anchors ...", flush=True)
    str_idx = collections.defaultdict(list)  # str -> [b_idx]
    for j, (s, c, nb) in enumerate(Bf):
        if s:
            for t in s: str_idx[t].append(j)
    match_b = {}   # a_idx -> b_idx
    used_b = set()
    cand = []
    for i, (s, c, nb) in enumerate(Af):
        if not s: continue
        votes = collections.Counter()
        for t in s: 
            for j in str_idx.get(t, ()): votes[j] += 1
        for j, v in votes.most_common(3):
            sj = Bf[j][0]
            inter = len(s & sj)
            if not inter: continue
            jac = inter / len(s | sj)
            if jac >= 0.55:
                cand.append((jac, inter, i, j))
    cand.sort(reverse=True)
    for jac, inter, i, j in cand:
        if i in match_b or j in used_b: continue
        match_b[i] = j
        used_b.add(j)

    # ---- Stage 1b: 归一化行集投票 (无字符串锚的主力匹配) ----
    print("stage1b: normalized-line voting ...", flush=True)
    import hashlib
    def line_hashes(nb, minlen=16):
        return {hashlib.blake2b(ln.encode()).digest()[:8]
                for ln in nb if len(ln) >= minlen}
    lh_a = [line_hashes(Af[i][2]) for i in range(len(Af))]
    lh_b = [line_hashes(Bf[j][2]) for j in range(len(Bf))]
    # 倒排索引: 只索引出现 ≤40 次的行(稀有行才有区分度)
    df_b = collections.Counter()
    for j in range(len(Bf)):
        for h in lh_b[j]: df_b[h] += 1
    inv = collections.defaultdict(list)
    for j in range(len(Bf)):
        for h in lh_b[j]:
            if df_b[h] <= 40: inv[h].append(j)
    rem_a = [i for i in range(len(Af)) if i not in match_b]
    cand2 = []
    for i in rem_a:
        votes = collections.Counter()
        for h in lh_a[i]:
            for j in inv.get(h, ()): votes[j] += 1
        for j, v in votes.most_common(2):
            ja, jb = lh_a[i], lh_b[j]
            if not ja or not jb: continue
            inter = len(ja & jb)
            jac = inter / len(ja | jb)
            if jac >= 0.55:
                cand2.append((jac, inter, i, j))
    cand2.sort(reverse=True)
    n_before = len(match_b)
    for jac, inter, i, j in cand2:
        if i in match_b or j in used_b: continue
        match_b[i] = j
        used_b.add(j)
    print(f"  stage1b added {len(match_b) - n_before} matches", flush=True)

    # ---- Stage 2: 无串函数: 常量签名 + 规模 ----
    print("stage2: constant signatures ...", flush=True)
    rem_a = [i for i in range(len(Af)) if i not in match_b]
    rem_b = [j for j in range(len(Bf)) if j not in used_b]
    cidx = collections.defaultdict(list)
    for j in rem_b:
        c = Bf[j][1]
        if c:
            sig = frozenset(v for v, n in c.items() if n >= 2)
            if sig: cidx[sig].append(j)
    for i in rem_a:
        c = Af[i][1]
        sig = frozenset(v for v, n in c.items() if n >= 2)
        if not sig or len(sig) < 2: continue
        for j in cidx.get(sig, ()):
            if j in used_b: continue
            la, lb = len(Af[i][2]), len(Bf[j][2])
            if la and lb and 0.7 <= la / lb <= 1.4:
                match_b[i] = j; used_b.add(j)
                break

    # ---- 分类 ----
    print("classify ...", flush=True)
    identical, modified = [], []
    for i, j in match_b.items():
        if Af[i][2] == Bf[j][2]: identical.append((i, j))
        else: modified.append((i, j))
    a1_only    = [i for i in range(len(Af)) if i not in match_b]
    a1m2_only  = [j for j in range(len(Bf)) if j not in used_b]

    print(f"\n===== appFw 函数级差分 =====")
    print(f"a1 函数: {len(Af)}   a1m2 函数: {len(Bf)}")
    print(f"匹配: {len(match_b)} (全同 {len(identical)} / 有差异 {len(modified)})")
    print(f"仅 a1: {len(a1_only)}   仅 a1m2: {len(a1m2_only)}")

    with open(f"{OUT_DIR}/appfw_diff_summary.tsv", "w") as f:
        f.write("class\ta1_addr\ta1_name\ta1m2_addr\ta1m2_name\tnote\n")
        for i, j in sorted(identical):
            f.write(f"identical\t{A[i][0]:x}\t{A[i][1]}\t{B[j][0]:x}\t{B[j][1]}\t\n")
        for i, j in sorted(modified, key=lambda x: -abs(len(Af[x[0]][2])-len(Bf[x[1]][2]))):
            da, db = len(Af[i][2]), len(Bf[j][2])
            f.write(f"modified\t{A[i][0]:x}\t{A[i][1]}\t{B[j][0]:x}\t{B[j][1]}\tlines {da}->{db}\n")
        for i in a1_only:
            f.write(f"a1_only\t{A[i][0]:x}\t{A[i][1]}\t\t\tlines {len(Af[i][2])}\n")
        for j in a1m2_only:
            f.write(f"a1m2_only\t\t\t{B[j][0]:x}\t{B[j][1]}\tlines {len(Bf[j][2])}\n")

    # 差异最大的对, 输出统一 diff 细节
    with open(f"{OUT_DIR}/appfw_diff_modified_top.tsv", "w") as f:
        f.write("a1_addr\ta1m2_addr\tdiff_lines(+/=)\n")
        for i, j in sorted(modified, key=lambda x: -abs(len(Af[x[0]][2])-len(Bf[x[1]][2])))[:nmax]:
            d = difflib.unified_diff(Af[i][2], Bf[j][2], lineterm='', n=0)
            plus = sum(1 for ln in d if ln.startswith('+') and not ln.startswith('+++'))
            f.write(f"{A[i][0]:x}\t{B[j][0]:x}\t{plus}\n")

    # 仅 a1m2 的函数: 按引用字符串聚类 top (给人工判读)
    cnt = collections.Counter()
    for j in a1m2_only:
        for t in Bf[j][0]:
            cnt[t] += 1
    print("\n仅 a1m2 函数的高频字符串锚 top30 (α1 II appFw 新增面):")
    for t, n in cnt.most_common(30):
        print(f"  {n:5d}x  {t[:90]}")
    cnt2 = collections.Counter()
    for i in a1_only:
        for t in Af[i][0]:
            cnt2[t] += 1
    print("\n仅 a1 函数的高频字符串锚 top20 (α1 独有面):")
    for t, n in cnt2.most_common(20):
        print(f"  {n:5d}x  {t[:90]}")

if __name__ == '__main__':
    main()
