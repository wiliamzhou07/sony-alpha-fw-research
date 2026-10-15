#!/usr/bin/env python3
"""
Sony Alpha firmware package (UFU/FDAT container) inspector & gen5/legacy unpacker.

Based on the reverse-engineered format documented by ma1co/fwtool.py
(https://github.com/ma1co/fwtool.py, MIT) plus the gen4/gen5 findings from
fwtool issue #39 (https://github.com/ma1co/fwtool.py/issues/39):
  - FDAT payload header  : AES-128-ECB with the known key_aes (public constant)
  - FDAT payload body    : gen5 = AES-CBC( key2 ) with IV stored at the end
    of the payload (key2 lives in the camera's libupdatertalk.so / newer
    platform firmware), gen4 = AES-CBC with key_cxd90045.

Usage:
  python3 unpack_ufu.py inspect BODYDATA.DAT [BODYDATA2.DAT ...]
      -> decode and print all unencrypted metadata (model, version, USB
         descriptor list, partition layout, CRC verification).

  python3 unpack_ufu.py unpack --key2 <hex64> BODYDATA.DAT -o outdir
      -> decrypt the body (gen5 AesCbc), extract updater fs image and the
         firmware archive, list tar contents.

  python3 unpack_ufu.py unpack --key2 <hex64> --mode ecb BODYDATA.DAT -o outdir
      -> try plain AES-ECB body decryption (alternative/legacy variants).

Requires: pycryptodomex (pip install pycryptodomex)
"""
import argparse
import hashlib
import os
import re
import struct
import sys
import tarfile
import zlib
import io

try:
    from Cryptodome.Cipher import AES
except ImportError:
    from Crypto.Cipher import AES

# ---- public constants from ma1co/fwtool.py (fwtool/sony/constants.py) ----
KEY_AES = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")   # AES-128-ECB (header, gen2/3/4/5)
KEY_CXD90014 = bytes.fromhex("E8B0886D97184F1F65C767F7939965BF")  # gen3 2nd key
KEY_CXD90045 = bytes.fromhex("C1AA8F7C46341FFED15589FC8170A6BB5925E85F6282D7F95BA3FDF5D303E06B")  # gen4 CBC key

MAGIC_UFU = b"\x89\x55\x46\x55\x0d\x0a\x1a\x0a"   # .UFU
MAGIC_UDTRFIRM = b"UDTRFIRM"


class UfuError(Exception):
    pass


def read_chunks(path):
    """Walk the top-level [size u32 BE][tag 4] chain of a .DAT (UFU) file."""
    size = os.path.getsize(path)
    chunks = []
    with open(path, "rb") as f:
        magic = f.read(8)
        if magic != MAGIC_UFU:
            raise UfuError("not a UFU container (bad magic: %s)" % magic.hex())
        off = 8
        while off + 8 <= size:
            f.seek(off)
            h = f.read(8)
            if len(h) < 8:
                break
            sz, tag = struct.unpack(">I", h[:4])[0], h[4:8]
            if not all(32 <= b < 127 for b in tag):
                raise UfuError("corrupt chunk header @%#x: %s" % (off, h.hex()))
            chunks.append((tag.decode("latin1"), sz, off))
            off += 8 + sz
    return chunks, size


def parse_udid(payload):
    """UDID chunk: u32 count + count x (pid u16, vid u16, mode u8, reserved u24)."""
    count = struct.unpack(">I", payload[:4])[0]
    descs = []
    for i in range(count):
        e = payload[4 + i * 8: 4 + i * 8 + 8]
        if len(e) < 8:
            break
        pid = struct.unpack(">H", e[0:2])[0]
        vid = struct.unpack(">H", e[2:4])[0]
        mode = e[4]
        descs.append((vid, pid, mode))
    return descs


def decrypt_fdat_header(payload):
    """Decrypt the 512-byte FDAT header: AES-128-ECB(KEY_AES) on payload[:512]."""
    if len(payload) < 512:
        raise UfuError("FDAT payload too small")
    return AES.new(KEY_AES, AES.MODE_ECB).decrypt(payload[:512])


def parse_fdat_header(dec, payload_len):
    """
    Parse the (decrypted) FDAT header. Two layouts are handled:
      old: magic at +0   new (gen4/5): 4-byte prefix, magic at +4.
    Returns a dict of values plus the fs table (list of dicts).
    """
    off = None
    if dec[0:8] == MAGIC_UDTRFIRM:
        off = 0
    elif dec[4:12] == MAGIC_UDTRFIRM:
        off = 4
    else:
        raise UfuError("FDAT header magic not found after ECB decrypt")
    h = dict(base=off)
    h["magic"] = dec[off:off + 8]
    h["checksum"] = dec[off + 8:off + 12].hex()
    h["version"] = dec[off + 12:off + 16].decode("latin1")
    h["modeType"] = dec[off + 16:off + 17].decode("latin1")
    h["luwFlag"] = dec[off + 20:off + 21].decode("latin1")
    h["versionMinor"] = dec[off + 32]
    h["versionMajor"] = dec[off + 33]
    h["versionStr"] = "%x.%02x" % (h["versionMajor"], h["versionMinor"])
    h["model"] = struct.unpack("<I", dec[off + 36:off + 40])[0]
    h["region"] = struct.unpack("<I", dec[off + 40:off + 44])[0]
    h["firmwareOffset"] = struct.unpack("<I", dec[off + 48:off + 52])[0]
    h["firmwareSize"] = struct.unpack("<I", dec[off + 52:off + 56])[0]
    h["numFileSystems"] = struct.unpack("<I", dec[off + 56:off + 60])[0]
    fss = []
    for i in range(min(h["numFileSystems"], 28)):
        o = off + 64 + i * 16
        mt = dec[o:o + 1].decode("latin1", "replace")
        f_off = struct.unpack("<I", dec[o + 4:o + 8])[0]
        f_size = struct.unpack("<I", dec[o + 8:o + 12])[0]
        fss.append(dict(modeType=mt, offset=f_off, size=f_size))
    h["fileSystems"] = fss
    h["payloadLen"] = payload_len
    return h


def print_header(h, udid, path):
    print("=" * 62)
    print("FILE:", os.path.basename(path))
    print("  FDAT header (offset=%d):" % h["base"])
    print("    magic       :", h["magic"].decode("latin1"), " version:", h["version"],
          " mode:", h["modeType"], " LUW:", h["luwFlag"])
    print("    fw version  :", h["versionStr"], " model: 0x%08x" % h["model"],
          " region: 0x%08x" % h["region"])
    print("    firmware    : offset 0x%x size 0x%x (%.1f MiB)"
          % (h["firmwareOffset"], h["firmwareSize"], h["firmwareSize"] / 1048576))
    for fss in h["fileSystems"]:
        print("    filesystem  : mode %s offset 0x%x size 0x%x (%.2f MiB)"
              % (fss["modeType"], fss["offset"], fss["size"], fss["size"] / 1048576))
    print("  USB descriptors (VID 0x%04x):" % 0x054c)
    for vid, pid, mode in udid:
        print("    PID 0x%04x  mode %s" % (pid, {1: "normal", 2: "updater"}.get(mode, str(mode))))
    # integrity
    with open(path, "rb") as f:
        sz = os.path.getsize(path)
        f.seek(sz - 12)
        crc_stored = struct.unpack(">I", f.read(12)[8:12])[0]
        crc = 0
        f.seek(0)
        left = sz - 12
        while left > 0:
            c = f.read(min(1 << 22, left))
            crc = zlib.crc32(c, crc)
            left -= len(c)
        match = (crc & 0xffffffff) == crc_stored
    print("  DEND crc32    : stored 0x%08x  computed 0x%08x  %s"
          % (crc_stored, crc & 0xffffffff, "OK" if match else "MISMATCH"))


def decrypt_body(payload, key2, mode):
    """Decrypt the FDAT body (everything after the 512-byte header)."""
    if mode == "ecb":
        return AES.new(key2, AES.MODE_ECB).decrypt(payload[512:])
    if mode == "cbc":
        # gen4/gen5: IV = 16 bytes at payload[-0x110:-0x100]; body = [512, len-0x110)
        iv = payload[-0x110:-0x100]
        ct = payload[512:len(payload) - 0x110]
        return AES.new(key2, AES.MODE_CBC, iv).decrypt(ct)
    if mode == "cbc-end":
        iv = payload[-0x10:]
        ct = payload[512:]
        return AES.new(key2, AES.MODE_CBC, iv).decrypt(ct)
    raise UfuError("unknown body mode: %s" % mode)


def unpack(payload, h, key2, mode, outdir):
    body = decrypt_body(payload, key2, mode)
    plain = payload[:512] + body
    os.makedirs(outdir, exist_ok=True)
    fs = None
    for fss in h["fileSystems"]:
        if fss["modeType"] == "U":
            fs = fss
    if fs is None:
        raise UfuError("no user filesystem entry found")
    fs_data = plain[fs["offset"]: fs["offset"] + fs["size"]]
    fw_data = plain[h["firmwareOffset"]: h["firmwareOffset"] + h["firmwareSize"]]
    fs_path = os.path.join(outdir, "updater.img")
    fw_path = os.path.join(outdir, "firmware.bin")
    with open(fs_path, "wb") as f:
        f.write(fs_data)
    with open(fw_path, "wb") as f:
        f.write(fw_data)
    print("  wrote %s (%d bytes)" % (fs_path, len(fs_data)))
    print("  wrote %s (%d bytes)" % (fw_path, len(fw_data)))
    try:
        with tarfile.open(fileobj=io.BytesIO(fw_data)) as t:
            print("  firmware is a tar archive; listing:")
            for m in t.getmembers()[:250]:
                print("    %10d  %s" % (m.size, m.name))
    except Exception as e:
        print("  firmware head:", fw_data[:32].hex())
        print("  (not a plain tar: %s; may be compressed or requires further steps)" % e)


def main():
    ap = argparse.ArgumentParser(description="Sony Alpha UFU/FDAT firmware inspector/unpacker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ins = sub.add_parser("inspect", help="decode unencrypted metadata + verify CRC")
    p_ins.add_argument("files", nargs="+")
    p_un = sub.add_parser("unpack", help="decrypt body with a key and extract images")
    p_un.add_argument("file")
    p_un.add_argument("--key2", required=True, help="hex 16/32-byte AES key for the body")
    p_un.add_argument("--mode", default="cbc", choices=["cbc", "cbc-end", "ecb"])
    p_un.add_argument("-o", "--outdir", default="unpacked")
    args = ap.parse_args()

    for path in args.files if args.cmd == "inspect" else [args.file]:
        chunks, size = read_chunks(path)
        udid = None
        fdat = None
        for tag, sz, off in chunks:
            with open(path, "rb") as f:
                f.seek(off + 8)
                data = f.read(sz)
            if tag == "UDID":
                udid = parse_udid(data)
            elif tag == "FDAT":
                fdat = (data, sz)
        if fdat is None:
            raise UfuError("no FDAT chunk found")
        payload, fdat_size = fdat
        dec = decrypt_fdat_header(payload)
        h = parse_fdat_header(dec, len(payload))
        if args.cmd == "inspect":
            print_header(h, udid or [], path)
        else:
            print_header(h, udid or [], path)
            key2 = bytes.fromhex(args.key2)
            print("  decrypting body with key2=%s mode=%s ..." % (args.key2[:8] + "...", args.mode))
            unpack(payload, h, key2, args.mode, args.outdir)


if __name__ == "__main__":
    main()
