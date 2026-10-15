#!/usr/bin/env python3
"""
extract_key.py —— 从相机侧二进制（libupdatertalk.so / sauu / initrd dump）中提取 gen5 AES 密钥。

原理：Sony 将内部 AES 密钥以常量形式编译进二进制。本脚本扫描文件中所有窗口
（16/24/32 字节），用"黄金判据"逐个验证：候选密钥在 CBC(IV=payload[-0x110:-0x100])
模式下解密 BODYDATA 的 firmware 区，若前 6 字节 == b'ustaR'（tar 魔数，随机概率 2^-48）
即为真密钥。

用法：
  python3 extract_key.py <binfile>... --fdat BODYDATA.DAT [--mode cbce|cbc0|ecb]
输出：找到的密钥（hex）；随后 `python3 unpack_ufu.py unpack --key2 <hex> BODYDATA.DAT -o out`
"""
import argparse
import os
import struct
import sys

from Cryptodome.Cipher import AES

KEY_AES = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
KNOWN = {KEY_AES, bytes.fromhex("E8B0886D97184F1F65C767F7939965BF"),
         bytes.fromhex("C1AA8F7C46341FFED15589FC8170A6BB5925E85F6282D7F95BA3FDF5D303E06B"),
         bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855")}


def load_fdat(path):
    """返回 (FDAT payload, fw 明文字段在 payload 内的偏移)"""
    with open(path, "rb") as f:
        if f.read(8) != b"\x89\x55\x46\x55\x0d\x0a\x1a\x0a":
            sys.exit("not a UFU file")
        off = 8
        while True:
            f.seek(off)
            h = f.read(8)
            if len(h) < 8:
                sys.exit("FDAT chunk not found")
            sz = struct.unpack(">I", h[:4])[0]
            tag = h[4:8]
            if tag == b"FDAT":
                payload = f.read(sz)
                break
            off += 8 + sz
    dec = AES.new(KEY_AES, AES.MODE_ECB).decrypt(payload[:512])
    base = 4 if dec[4:12] == b"UDTRFIRM" else 0
    fw_off = struct.unpack("<I", dec[base + 48: base + 52])[0]
    return payload, fw_off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bins", nargs="+", help="binary files from the camera")
    ap.add_argument("--fdat", required=True, help="BODYDATA.DAT to validate against")
    ap.add_argument("--mode", default="cbce", choices=["cbce", "cbc0", "ecb"])
    args = ap.parse_args()

    payload, fw_off = load_fdat(args.fdat)
    with open(args.fdat, "rb") as f:
        f.seek(0)
        assert f.read(8) == b"\x89\x55\x46\x55\x0d\x0a\x1a\x0a"
        off = 8
        while True:
            f.seek(off)
            h = f.read(8)
            sz = struct.unpack(">I", h[:4])[0]
            if h[4:8] == b"FDAT":
                # CBC 流中段：读 fw_off 前 16 字节作为解密首块的 IV(=前一块密文)
                f.seek(off + 8 + fw_off - 16)
                ct_fw = f.read(16 + 0x200)
                break
            off += 8 + sz
    ct_iv = ct_fw[:16]           # 前一块密文
    ct_fw = ct_fw[16:16 + 0x200]
    ct_fw = ct_fw[:len(ct_fw) // 16 * 16]

    def check(key):
        try:
            if args.mode == "ecb":
                d = AES.new(key, AES.MODE_ECB).decrypt(ct_fw)
            elif args.mode == "cbc0":
                d = AES.new(key, AES.MODE_CBC, iv=bytes(16)).decrypt(ct_fw)
            else:
                d = AES.new(key, AES.MODE_CBC, iv=ct_iv).decrypt(ct_fw)
            # 黄金判据：tar 魔数在偏移 257（ushar）或 gzip 魔数
            return d[257:262] == b"ustar" or d[:6] == b"ustaR" or d[:8] == b"\x1f\x8b\x08\x00"
        except Exception:
            return False

    found = []
    for path in args.bins:
        data = open(path, "rb").read()
        n = len(data)
        print(f"scanning {path} ({n} bytes, mode={args.mode}) ...")
        # 快速跳过：先只在 .rodata/.data 区域内找高熵窗口? 直接全扫，逐窗口即时验证
        for size in (16, 24, 32):
            cnt = 0
            for i in range(0, n - size, 1):
                k = data[i:i + size]
                if k in KNOWN:
                    continue
                if check(k):
                    print(f"  *** FOUND KEY ({args.mode}, size={size}) @0x{i:x}: {k.hex()} in {path}")
                    found.append((path, k.hex()))
                cnt += 1
                if cnt % 2000000 == 0:
                    print(f"  ... {cnt}/{n} windows (size={size})")
        print(f"  done size={size}")
    if not found:
        print("no key found in these binaries (may need more extraction: sauu / initrd.img)")

    # 对找到的密钥，立即给出完整解包指令
    for path, khex in found:
        print(f"\nuse: python3 unpack_ufu.py unpack --key2 {khex} --mode {args.mode} "
              f"'{args.fdat}' -o unpacked")


if __name__ == "__main__":
    main()
