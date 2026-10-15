#!/usr/bin/env python3
"""
gen5_pack.py — Sony gen5 (CXD90057+CXD90058) 固件重打包/重加密工具。

与 fwtool.py 的 AesCbcCrypter 完全互逆：
  明文流 --[1020B 分块 + packBlock(2B校验+2B大小/结束标志+0xFF填充)]--> 1024B 块
        --[首块: 前512B AES-ECB(key_aes), 后512B AES-CBC(key2); 其余块: CBC 续链]--> 密文
  密文尾部: [IV 16B][尾部 256B]  (payload 总长 = N*1024 + 0x110)

用法:
  # 回环验证: 解出明文 -> 重加密 -> 应与原 payload 逐字节一致
  python3 gen5_pack.py roundtrip BODYDATA.DAT

  # 修改测试: 在明文流 offset 处写入字节 -> 重打包 -> 输出新 .DAT
  python3 gen5_pack.py modify BODYDATA.DAT --offset 0x12345 --bytes deadbeef -o out.DAT

  # 完整重打包: 用 fwtool 解包目录 (firmware.fdat) 重新生成 .DAT
  python3 gen5_pack.py repack BODYDATA.DAT --fdat firmware.fdat -o out.DAT
"""
import argparse
import os
import struct
import sys
import zlib

try:
    from Cryptodome.Cipher import AES
except ImportError:
    from Crypto.Cipher import AES

KEY_AES = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
KEY_GEN5_V1 = bytes.fromhex("376A61D907035CF18300F2ADD6503E649FCCF0C0191DCC38C3B05895150A7FB6")  # α1 V1.35
KEY_GEN5_V2 = bytes.fromhex("434589432D319010F1132727353286CE4D7EDE8B9C4F7217A0E0226E0F0EDC69")  # α1 V2.01+/α1 II

MAGIC_UFU = b"\x89UFU\r\n\x1a\n"
BLOCK = 1024
CHUNK = BLOCK - 4          # 1020
TRAILER = 0x110            # IV(16) + 256B tail


# ---------- UFU / FDAT 容器 ----------

def read_ufu(path):
    data = open(path, "rb").read()
    if data[:8] != MAGIC_UFU:
        raise ValueError("not a UFU container")
    chunks = []
    off = 8
    while off + 8 <= len(data):
        sz, tag = struct.unpack(">I", data[off:off+4])[0], data[off+4:off+8]
        chunks.append((tag, data[off+8:off+8+sz]))
        off += 8 + sz
    return data, chunks


def get_fdat(chunks):
    for tag, payload in chunks:
        if tag == b"FDAT":
            return payload
    raise ValueError("no FDAT chunk")


def write_ufu(chunks):
    """chunks: [(tag4, payload)]; 自动重算 DEND(crc32 of 全部前文)"""
    out = bytearray()
    out += MAGIC_UFU
    body = bytearray()
    for tag, payload in chunks:
        if tag == b"DEND":
            continue
        body += struct.pack(">I", len(payload)) + tag + payload
    out += body
    crc = zlib.crc32(bytes(out)) & 0xffffffff
    out += struct.pack(">I", 4) + b"DEND" + struct.pack(">I", crc)
    return bytes(out)


# ---------- 块层 (packBlock/unpackBlock, 与 fwtool 一致) ----------

def _calc_sum(data):
    """sum of u16le words & 0xffff (fwtool BlockCrypter._calcSum)"""
    if len(data) % 2:
        data += b"\x00"
    return sum(struct.unpack("<%dH" % (len(data) // 2), data)) & 0xffff


def pack_block(data, is_last):
    """1020B 明文 -> 1024B 块"""
    assert len(data) <= CHUNK
    size_flag = len(data) | (0x8000 if is_last else 0)
    d = struct.pack("<H", size_flag) + data + b"\xff" * (CHUNK - len(data))
    return struct.pack("<H", _calc_sum(d)) + d


def unpack_block(block, is_last):
    """fwtool 校验逻辑: 校验和 + 结束标志"""
    checksum, size_flag = struct.unpack("<HH", block[:4])
    size = size_flag & 0x7fff
    end = bool(size_flag & 0x8000)
    if _calc_sum(block[2:]) != checksum:
        raise ValueError("block checksum mismatch")
    if end != is_last:
        raise ValueError("end flag mismatch")
    return block[4:4 + size]


# ---------- 加解密层 ----------

def gen5_decrypt_payload(payload, key2):
    """完整 FDAT payload -> 明文流 (unpack 后)"""
    if len(payload) < TRAILER or (len(payload) - TRAILER) % BLOCK:
        raise ValueError("bad payload size")
    iv = payload[-TRAILER:-0x100]
    ct = payload[:len(payload) - TRAILER]
    cipher1 = AES.new(KEY_AES, AES.MODE_ECB)
    cipher2 = AES.new(key2, AES.MODE_CBC, iv)
    plain = bytearray()
    nblocks = len(ct) // BLOCK
    for i in range(nblocks):
        blk = ct[i * BLOCK:(i + 1) * BLOCK]
        if i == 0:
            dec = cipher1.decrypt(blk[:512]) + cipher2.decrypt(blk[512:])
        else:
            dec = cipher2.decrypt(blk)
        plain += unpack_block(dec, is_last=(i == nblocks - 1))
    return bytes(plain)


def gen5_encrypt_payload(plain, key2, iv, tail256):
    """明文流 -> 完整 FDAT payload (含 IV+尾 256B)"""
    nblocks = (len(plain) + CHUNK - 1) // CHUNK
    blocks = []
    for i in range(nblocks):
        chunk = plain[i * CHUNK:(i + 1) * CHUNK]
        blocks.append(pack_block(chunk, is_last=(i == nblocks - 1)))
    cipher1 = AES.new(KEY_AES, AES.MODE_ECB)
    cipher2 = AES.new(key2, AES.MODE_CBC, iv)
    ct = bytearray()
    for i, blk in enumerate(blocks):
        if i == 0:
            ct += cipher1.encrypt(blk[:512]) + cipher2.encrypt(blk[512:])
        else:
            ct += cipher2.encrypt(blk)
    return bytes(ct) + iv + tail256


def pick_key(plain):
    """按明文头部版本字段粗判: 无所谓, 仅用于提示; 默认用 V2"""
    return KEY_GEN5_V2


# ---------- 命令 ----------

def cmd_roundtrip(path):
    data, chunks = read_ufu(path)
    payload = get_fdat(chunks)
    print("[*] payload: 0x%x bytes (%d blocks + 0x110)" %
          (len(payload), (len(payload) - TRAILER) // BLOCK))
    iv = payload[-TRAILER:-0x100]
    tail256 = payload[-0x100:]
    last_err = None
    for kname, key in [("gen5_v2(4345..)", KEY_GEN5_V2), ("gen5_v1(376A..)", KEY_GEN5_V1)]:
        try:
            plain = gen5_decrypt_payload(payload, key)
        except Exception as e:
            last_err = e
            continue
        print("[*] 解密成功, 密钥 = %s, 明文流 = 0x%x bytes" % (kname, len(plain)))
        re_payload = gen5_encrypt_payload(plain, key, iv, tail256)
        same = re_payload == payload
        print("[%s] 重加密回环: %s" % ("PASS" if same else "FAIL",
              "逐字节一致" if same else "不一致!"))
        if not same:
            for i, (a, b) in enumerate(zip(re_payload, payload)):
                if a != b:
                    print("    首个差异 @0x%x: 新%02x 原%02x" % (i, a, b))
                    break
            print("    长度: 新 0x%x vs 原 0x%x" % (len(re_payload), len(payload)))
        # UFU 容器层回环
        rebuilt = write_ufu(chunks)
        print("[%s] UFU 容器回环: %s" % ("PASS" if rebuilt == data else "FAIL",
              "逐字节一致(含 DEND CRC)" if rebuilt == data else "不一致"))
        return 0 if same and rebuilt == data else 1
    raise SystemExit("解密失败: %s" % last_err)


def cmd_modify(path, offset, hexbytes, out):
    data, chunks = read_ufu(path)
    payload = get_fdat(chunks)
    iv = payload[-TRAILER:-0x100]
    tail256 = payload[-0x100:]
    plain = None
    for kname, key in [("gen5_v2", KEY_GEN5_V2), ("gen5_v1", KEY_GEN5_V1)]:
        try:
            plain = gen5_decrypt_payload(payload, key)
            print("[*] 解密成功 (%s), 明文 0x%x" % (kname, len(plain)))
            break
        except Exception:
            continue
    if plain is None:
        raise SystemExit("解密失败")
    patch = bytes.fromhex(hexbytes)
    print("[*] 修改: offset=0x%x  %s -> %s" %
          (offset, plain[offset:offset + len(patch)].hex(), patch.hex()))
    plain2 = plain[:offset] + patch + plain[offset + len(patch):]
    payload2 = gen5_encrypt_payload(plain2, key, iv, tail256)
    chunks2 = [(t, payload2 if t == b"FDAT" else p) for t, p in chunks]
    open(out, "wb").write(write_ufu(chunks2))
    print("[*] 已写出 %s (0x%x bytes)" % (out, os.path.getsize(out)))
    # 自校验: 再解一遍
    data2, chunks2r = read_ufu(out)
    plain3 = gen5_decrypt_payload(get_fdat(chunks2r), key)
    ok = plain3 == plain2
    print("[%s] 二次解密校验: %s" % ("PASS" if ok else "FAIL",
          "修改生效且全部块校验通过" if ok else "回环失败"))


def cmd_repack(path, fdat_path, out):
    """用现成明文流(fwtool 解出的 firmware.fdat)重打包"""
    data, chunks = read_ufu(path)
    payload = get_fdat(chunks)
    iv = payload[-TRAILER:-0x100]
    tail256 = payload[-0x100:]
    plain = open(fdat_path, "rb").read()
    for kname, key in [("gen5_v2", KEY_GEN5_V2), ("gen5_v1", KEY_GEN5_V1)]:
        try:
            gen5_decrypt_payload(payload, key)
            break
        except Exception:
            continue
    payload2 = gen5_encrypt_payload(plain, key, iv, tail256)
    chunks2 = [(t, payload2 if t == b"FDAT" else p) for t, p in chunks]
    open(out, "wb").write(write_ufu(chunks2))
    print("[*] 已写出 %s" % out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("roundtrip"); p.add_argument("file")
    p = sub.add_parser("modify"); p.add_argument("file")
    p.add_argument("--offset", required=True)
    p.add_argument("--bytes", required=True)
    p.add_argument("-o", required=True)
    p = sub.add_parser("repack"); p.add_argument("file")
    p.add_argument("--fdat", required=True)
    p.add_argument("-o", required=True)
    args = ap.parse_args()
    if args.cmd == "roundtrip":
        return cmd_roundtrip(args.file)
    if args.cmd == "modify":
        return cmd_modify(args.file, int(args.offset, 0), args.bytes, args.o)
    if args.cmd == "repack":
        return cmd_repack(args.file, args.fdat, args.o)


if __name__ == "__main__":
    sys.exit(main() or 0)
