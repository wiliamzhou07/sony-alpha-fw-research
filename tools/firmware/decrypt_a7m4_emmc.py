#!/usr/bin/env python3
"""多进程解密 A7M4 eMMC 转储的指定分区（AES-XTS，tweak=绝对扇区号）。
用法: decrypt_a7m4.py <output_dir> <nflashaN> ..."""
import os, sys, struct
from multiprocessing import Pool
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BIN = "<workspace>/A7M4_EMMC_DUMP.BIN"
BROM = "<workspace>/ILCE-7M4-RE/bootrom/CXD90057_Mira_0xFFFF0000.bin"
LOADER = "<workspace>/ILCE-7M4-RE/emmc_boot/esram_0xfe040000.bin"
SECTOR = 512
CHUNK = 8192  # 4MB per task

u32 = lambda b, o: int.from_bytes(b[o:o+4], "little")

def derive_key():
    brom = open(BROM, "rb").read()
    loader = open(LOADER, "rb").read()
    tbl = [u32(loader, 0x239b0 + i) >> 16 for i in range(0, 0x100, 4)]
    return bytes(brom[0xb800 + i] for i in tbl)

KEY = derive_key()

def read_table():
    f = open(BIN, "rb")
    assert f.read(8) == b"82462.00"
    n = u32(f.read(4), 0)
    parts = {}
    for i in range(n):
        f.seek(32 + i * 16)
        start, count, ptype, flag = (u32(f.read(4), 0) for _ in range(4))
        if flag & 1:
            parts[f"nflasha{i+1}"] = (start, count)
    return parts

def decrypt_chunk(args):
    start, nsec = args
    f = open(BIN, "rb")
    out = bytearray()
    for i in range(nsec):
        f.seek(SECTOR * (start + i))
        tweak = (start + i).to_bytes(16, "little")
        dec = Cipher(algorithms.AES(KEY), modes.XTS(tweak)).decryptor()
        out += dec.update(f.read(SECTOR)) + dec.finalize()
    return bytes(out)

def decrypt_partition(name, start, count, outdir):
    dst = os.path.join(outdir, name)
    tasks = [(start + s, min(CHUNK, count - s)) for s in range(0, count, CHUNK)]
    with open(dst, "wb") as out, Pool(os.cpu_count()) as pool:
        off = 0
        for blob in pool.imap(decrypt_chunk, tasks):
            out.seek(off)
            out.write(blob)
            off += len(blob)
    print(f"{name}: {count*512/1048576:.0f} MB -> {dst}")

if __name__ == "__main__":
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    parts = read_table()
    for name in sys.argv[2:]:
        start, count = parts[name]
        decrypt_partition(name, start, count, outdir)
