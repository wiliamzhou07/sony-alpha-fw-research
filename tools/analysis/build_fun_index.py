#!/usr/bin/env python3
"""build_fun_index.py <decompiled.c> <out.tsv>
为 Ghidra 全量反编译产物建函数索引 TSV（模块聚类用）。
列: addr / func_name / size(字节,下一函数地址差) / nstrings / string_refs(截断) / ncalls / callees(截断)
字符串口径: 函数体内所有 C 字符串字面量 + Ghidra 符号引用(s_xxx/u_xxx 名内的可读段)。
"""
import re, sys, collections

HDR = re.compile(r"^// ==== (.+?) @ ([0-9a-fA-F]+) ====")
STR = re.compile(r'"((?:[^"\\]|\\.)*)"')
CALL = re.compile(r'\b([A-Za-z_][A-Za-z0-9_:<>~]*)\s*\(')

def main(src, dst):
    funcs = []  # (addr_int, name, start_line)
    with open(src, "r", errors="replace") as f:
        lines = f.readlines()
    for i, ln in enumerate(lines):
        if ln.startswith("// ==== "):
            m = HDR.match(ln.rstrip("\n"))
            if m:
                funcs.append((int(m.group(2), 16), m.group(1), i))
    n = len(funcs)
    out = open(dst, "w")
    print(f"# {n} functions from {src}", file=out)
    for k, (addr, name, s0) in enumerate(funcs):
        s1 = funcs[k + 1][2] if k + 1 < n else len(lines)
        body = "".join(lines[s0 + 1:s1])
        strs = collections.OrderedDict()
        for m in STR.finditer(body):
            t = m.group(1)
            if len(t) >= 4:
                strs[t] = 1
        calls = collections.Counter()
        for m in CALL.finditer(body):
            calls[m.group(1)] += 1
        sl = [t for t in strs if len(t) <= 160][:24]
        cl = [f"{c}x{cnt}" for c, cnt in calls.most_common(16) if c not in
              ("if", "for", "while", "switch", "return", "sizeof")]
        out.write(f"{addr:x}\t{name}\t{s1-s0}\t{len(strs)}\t{' | '.join(sl)}\t{sum(calls.values())}\t{','.join(cl)}\n")
    out.close()
    print(f"wrote {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
