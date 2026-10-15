import sys, re
name = sys.argv[1]
FUN_SPLIT = re.compile(r'// ==== (FUN_[0-9a-f]+) @ ([0-9a-f]+) ====')
out, cur, on = [], [], False
with open("<workspace>/firmware_reverse/decompiled/a1m2_cpapp.c") as f:
    for line in f:
        m = FUN_SPLIT.match(line)
        if m:
            if on:
                break
            on = (m.group(1) == name)
            if on: out.append(line)
        elif on:
            out.append(line)
sys.stdout.write(''.join(out))
