#!/usr/bin/env python3
"""Sony default.nab (Vivante ACuity/VIP 多网容器) 结构解析器.

已确认的容器层格式:
  文件头: magic 'NA\\0\\0' | u32 f1 | u32 f2 | u32 n_sections
          + 4×(ptr,size) 指向子表
  17 × { 32B 描述符: id,a,b,c,d | VPMN section: 'VPMN' ver flags hdrlen name...
         section 总长 = c + 32 (描述符随行) }
  全局区(文件头 0x20..0x510): 张量名/层名记录 (本次也一并 dump)

section 内部 (数据驱动, 结构推断中):
  VPMN 头 212B(name@+12) -> 元数据区(低熵: 张量记录+层表+参数) -> 权重块(高熵)
  张量记录: [...][ndim][dims..][dtype][zp i32][scale fp32][pad] name
  层记录:   [小u32序列(疑似边表)] name
"""
import struct, json, math, collections, sys, re

PATH = sys.argv[1] if len(sys.argv) > 1 else 'default.nab'
data = open(PATH, 'rb').read()

# ---------- 容器层 ----------
magic, f1, f2, nsec = struct.unpack('<4sIII', data[:16])
subtabs = [struct.unpack('<II', data[0x10 + i*8: 0x18 + i*8]) for i in range(4)]

# VPMN section 定位
SECS = [m.start() for m in re.finditer(b'VPMN', data)]
# 每个 section 前面 32B 是描述符(跳过第一个紧邻全局区的情况: 检查 magic 特征)
sections = []
for s in SECS:
    u = struct.unpack('<4sHHI', data[s:s+12])
    name = data[s+12:s+44].split(b'\0')[0].decode('ascii', 'replace')
    desc = struct.unpack('<5I', data[s-20:s])  # 32B 描述符的后 20B 在 name 之后? 前置描述符在 s-32..s
    sections.append({'off': s, 'ver': f'{u[1]}.{u[2]}', 'hdrlen': u[3], 'name': name})

# section 总长: 下一个 section 的前置描述符起点 = 本 section off + 212 + payload
# 用实测: desc@ (next_sec-52..next_sec-20)? — 直接用间距
ends = []
for i, s in enumerate(SECS):
    nxt = SECS[i+1] if i+1 < len(SECS) else len(data)
    ends.append(nxt - 32 if i+1 < len(SECS) else len(data))

print(f"容器: f1={f1} f2={f2} nsec={nsec}")
for i, (sec, e) in enumerate(zip(sections, ends)):
    s = sec['off']
    desc = struct.unpack('<8I', data[s-32:s])
    print(f"S{i:2d} @{s:>10,} len={e-s:>10,} ver={sec['ver']:>5} desc_id={desc[0]:>2} "
          f"a={desc[1]:>9,} b={desc[2]:>9,} c={desc[3]:>9,} d={desc[4]} name={sec['name']}")

# ---------- section 内部 ----------
def entropy(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

report = {'sections': []}
for i, (sec, e) in enumerate(zip(sections, ends)):
    s = sec['off']
    body = data[s+212:e]
    # 熵剖面 4KB, 找元数据->权重边界
    blk = 4096
    ents = [(s+212+o, entropy(body[o:o+blk])) for o in range(0, len(body)-blk, blk)]
    wstart = next((off for off, h in ents if h > 7.2), e)
    # 字符串(相对 section 起点)
    strs = [(m.start() - 212, m.group().decode('ascii')) for m in
            re.finditer(rb'[\x20-\x7e]{4,}', body[:wstart-212] if wstart > s+212 else body[:0])]
    report['sections'].append({
        'idx': i, 'off': s, 'end': e, 'name': sec['name'],
        'meta_len': wstart - (s+212), 'weights_len': e - wstart,
        'strings': strs,
    })
    print(f"\nS{i:2d} {sec['name']}: 元数据 {wstart-(s+212):,}B + 权重 {e-wstart:,}B, "
          f"字符串 {len(strs)} 条 (前8: {[t[1][:24] for t in strs[:8]]})")

json.dump(report, open('nab_sections.json', 'w'), ensure_ascii=False, indent=1)
print("\n已写出 nab_sections.json")
