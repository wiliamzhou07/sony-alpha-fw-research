#!/usr/bin/env python3
"""default.nab v2 解析器: 张量记录 + 层表 + 参数流 + 权重块边界 + 尺寸算术验证."""
import struct, re, json, math, collections, sys
import numpy as np

PATH = 'default.nab'
data = open(PATH, 'rb').read()
SECS = [m.start() for m in re.finditer(b'VPMN', data)]
NAMES_RE = re.compile(rb'(input\[\d+\]|output\[\d+\]|uid_\d+_out_\d+)')

def entropy(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def parse_tensor_record(body, name_off):
    """名称前 52B(13 u32) 是记录头; 向前找 pad 边界由调用方定."""
    pre = struct.unpack('<13I', body[name_off-52:name_off])
    ndim = pre[0]
    dims = list(pre[1:5])[:max(ndim,1)] if 1 <= ndim <= 4 else list(pre[1:5])
    s0, s1, dtype, x0, dtype2 = pre[5:10]
    zp = struct.unpack('<i', struct.pack('<I', pre[10]))[0]
    scale = struct.unpack('<f', struct.pack('<I', pre[11]))[0]
    return dict(ndim=ndim, dims=dims, dtype=dtype, dtype2=dtype2, zp=zp, scale=scale,
                raw=pre, name_off=name_off)

def section_iter():
    for i, s in enumerate(SECS):
        nxt = SECS[i+1] if i+1 < len(SECS) else len(data)
        e = nxt - 32 if i+1 < len(SECS) else len(data)
        u = struct.unpack('<4sHHI', data[s:s+12])
        name = data[s+12:s+44].split(b'\0')[0].decode('ascii', 'replace')
        yield i, s, e, u[3], name

report = {}
for i, s, e, hdrlen, name in section_iter():
    body = data[s+hdrlen:e]          # 去 VPMN 头
    nb = len(body)
    # ---- 熵定位权重首块 ----
    blk = 4096
    ents = [(o, entropy(body[o:o+blk])) for o in range(0, nb-blk, blk)]
    wfirst = next((o for o, h in ents if h > 7.2), nb)

    meta = body[:wfirst] if wfirst else body[:0]
    # ---- 张量记录 ----
    tensors = []
    for m in NAMES_RE.finditer(meta):
        no = m.start()
        if no >= 52:
            try:
                t = parse_tensor_record(meta, no)
                t['name'] = m.group().decode()
                t['off'] = no
                tensors.append(t)
            except Exception:
                pass
    # ---- 层名 ----
    LAYERS_RE = re.compile(rb'(ConvolutionReluPoolingLayer2|PoolingLayer|FullyConnectedReluLayer|'
                           rb'TensorCopy|ConcatLayer|EltwiseLayer|SoftmaxLayer|DeconvolutionReluLayer|'
                           rb'FullyConnectedLayer|ConvolutionLayer|ReluLayer|ScaleLayer|PermuteLayer|'
                           rb'ReshapeLayer|SplitLayer|NormalizationLayer|BatchNormLayer[a-zA-Z0-9_]*)')
    layers = [{'off': m.start(), 'type': m.group().decode()} for m in LAYERS_RE.finditer(meta)]
    # ---- 权重块分段 (4KB 熵, 从 wfirst 起) ----
    chunks = []
    o = wfirst
    state = None
    for o2 in range(wfirst, nb-512, 512):
        h = entropy(body[o2:o2+512])
        st = 'W' if h > 6.9 else ('C' if h > 4.5 else 'L')
        if st != state:
            chunks.append({'off': o2, 'kind': st})
            state = st
    # 合并相邻 W 块
    wc = []
    for c in chunks:
        if c['kind'] == 'W' and wc and wc[-1]['kind'] == 'W' and c['off'] - wc[-1]['end'] <= 512:
            wc[-1]['end'] = c['off'] + 512
        else:
            wc.append({'kind': c['kind'], 'off': c['off'], 'end': c['off']+512})
    wchunks = [{'off': c['off'], 'size': c['end']-c['off']} for c in wc if c['kind']=='W']

    report[i] = dict(name=name, off=s, len=nb, meta_len=wfirst,
                     tensors=tensors, nlayers=len(layers),
                     layer_types=dict(collections.Counter(l['type'] for l in layers)),
                     wchunks=wchunks)
    sizes = [c['size'] for c in wchunks]
    print(f"S{i:2d} {name[:34]:<36} meta={wfirst:>7,} 层={len(layers):>4} 张量记录={len(tensors):>3} "
          f"权重块={sizes}")
    for t in tensors[:6]:
        print(f"     T {t['name']:<18} ndim={t['ndim']} dims={t['dims']} dtype={t['dtype']} "
              f"zp={t['zp']} scale={t['scale']:.6g}")
    if len(tensors) > 6: print(f"     ... 共 {len(tensors)} 条")

json.dump(report, open('nab_v2.json','w'), ensure_ascii=False, indent=1, default=str)
print("\n== 写出 nab_v2.json ==")

# ---- S1 深检: 权重块 int16 检验 + 尺寸算术 ----
print("\n== S1 权重块逐块检验 ==")
s = SECS[1]; body = data[s+212: s+212+128908]
for c in report[1]['wchunks']:
    W = body[c['off']:c['off']+c['size']]
    arr = np.frombuffer(W, dtype=np.uint8)
    hi = collections.Counter(arr[1::2].tolist()); lo = collections.Counter(arr[0::2].tolist())
    def Hh(counter, n):
        return -sum((v/n)*math.log2(v/n) for v in counter.values())
    eh, el = Hh(hi, len(hi)), Hh(lo, len(lo))
    u16 = np.frombuffer(W[:len(W)//2*2], dtype='<i2').astype(int)
    print(f"  +{c['off']:#07x} {c['size']:>6,}B  hi熵={eh:.2f} lo熵={el:.2f} "
          f"| int16幅度 p1={np.percentile(np.abs(u16),1):.0f} p50={np.percentile(np.abs(u16),50):.0f} "
          f"p99={np.percentile(np.abs(u16),99):.0f}")
