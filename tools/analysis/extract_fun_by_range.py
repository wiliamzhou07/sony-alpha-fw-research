#!/usr/bin/env python3
"""按地址范围提取 a1m2_cpapp.c 中的函数. usage: extract_fun_by_range.py <start_hex> <end_hex> [out]"""
import sys, re
lo, hi = int(sys.argv[1], 16), int(sys.argv[2], 16)
FUN_SPLIT = re.compile(r'// ==== (FUN_[0-9a-f]+) @ ([0-9a-f]+) ====')
out, on = [], False
SRC = "<workspace>/firmware_reverse/decompiled/a1m2_cpapp.c"
with open(SRC) as f:
    for line in f:
        m = FUN_SPLIT.match(line)
        if m:
            a = int(m.group(2), 16)
            on = (lo <= a < hi)
            if on: out.append(line)
        elif on:
            out.append(line)
text = ''.join(out)
if len(sys.argv) > 3:
    open(sys.argv[3], 'w').write(text)
    print(f'{len(text)} bytes → {sys.argv[3]}')
else:
    sys.stdout.write(text)
