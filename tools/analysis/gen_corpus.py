#!/usr/bin/env python3
"""Generate complete reverse-engineering corpus for a1/a1M2 decrypted trees."""
import os, sys, re, hashlib, gzip, struct

OUT = "<workspace>/firmware_reverse"
CAMS = {"a1": "/tmp/a1_v400", "a1m2": "/tmp/a1m2_v400"}

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            yield p, rel

def invent(cam, root):
    rows = []
    for p, rel in walk(root):
        try:
            st = os.stat(p)
        except OSError:
            continue
        size = st.st_size
        try:
            with open(p, "rb") as f:
                head = f.read(16)
        except OSError:
            head = b""
        magic = "elf" if head[:4] == b"\x7fELF" else head[:4].hex()
        try:
            h = md5(p)
        except OSError:
            h = "UNREADABLE"
        rows.append((rel, size, h, magic))
        print(f"[{cam}] {len(rows)} {rel}", file=sys.stderr)
    with open(f"{OUT}/{cam}_inventory.tsv", "w") as f:
        for rel, size, h, magic in rows:
            f.write(f"{rel}\t{size}\t{h}\t{magic}\n")
    return rows

def version_sweep(cam, root, rows):
    pat_ver = re.compile(rb"Ver\.?\s?[0-9]{1,2}\.[0-9]{1,3}(?:\.[0-9]{1,3})?")
    pat_date = re.compile(rb"(?:20[12][0-9])[./-](?:0[1-9]|1[0-2])[./-](?:0[1-9]|[12][0-9]|3[01])")
    out = []
    for rel, size, h, magic in rows:
        if size > 60_000_000:
            continue
        p = os.path.join(root, rel)
        hits = set()
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError:
            continue
        for m in list(pat_ver.finditer(data))[:200]:
            hits.add(b"Ver:" + data[m.start():m.end()])
            if len(hits) >= 6: break
        for m in list(pat_date.finditer(data))[:100]:
            hits.add(b"Date:" + data[m.start():m.end()])
            if len(hits) >= 10: break
        if hits:
            out.append((rel, size, b"; ".join(sorted(hits)[:6]).decode("ascii", "replace")))
    with open(f"{OUT}/{cam}_versions.tsv", "w") as f:
        for rel, size, v in out:
            f.write(f"{rel}\t{size}\t{v}\n")
    print(f"[{cam}] versions: {len(out)} files", file=sys.stderr)

def vermagic(cam, root, rows):
    out = []
    for rel, size, h, magic in rows:
        if rel.endswith(".ko"):
            p = os.path.join(root, rel)
            try:
                data = open(p, "rb").read()
            except OSError:
                continue
            i = data.find(b"vermagic=")
            v = data[i:i+120].split(b"\x00")[0].decode("ascii", "replace") if i >= 0 else "(no vermagic)"
            out.append((rel, size, v))
    with open(f"{OUT}/{cam}_kmod_vermagic.tsv", "w") as f:
        for rel, size, v in out:
            f.write(f"{rel}\t{size}\t{v}\n")
    print(f"[{cam}] kmods: {len(out)}", file=sys.stderr)

def elf_symbols(cam, root, rows):
    try:
        from elftools.elf.elffile import ELFFile
        ok = True
    except ImportError:
        ok = False
    out = []
    for rel, size, h, magic in rows:
        if magic != "elf" or size > 80_000_000:
            continue
        p = os.path.join(root, rel)
        entry = machine = symcount = stripped = "?"
        try:
            if ok:
                with open(p, "rb") as f:
                    e = ELFFile(f)
                    machine = e.header["e_machine"].replace("EM_", "")
                    entry = hex(e.header["e_entry"])
                    st = e.get_section_by_name(".symtab")
                    if st:
                        symcount = st.num_symbols(); stripped = "no"
                    else:
                        symcount = 0; stripped = "yes"
            else:
                data = open(p, "rb").read()
                machine = {0x3e: "X86_64", 0xb7: "AARCH64", 0x28: "ARM", 0xf3: "RISCV"}.get(struct.unpack("<H", data[18:20])[0], hex(struct.unpack("<H", data[18:20])[0]))
        except Exception as ex:
            entry = f"ERR:{type(ex).__name__}"
        out.append((rel, size, machine, entry, symcount, stripped))
    with open(f"{OUT}/{cam}_elf_audit.tsv", "w") as f:
        f.write("rel\tsize\tmachine\tentry\tsymbols\tstripped\n")
        for r in out:
            f.write("\t".join(map(str, r)) + "\n")
    print(f"[{cam}] elfs: {len(out)}", file=sys.stderr)

def key_strings(cam, root):
    keys = ["cpapp-b.bin", "adam_app.bin", "mini_ldr.bin", "loader_spi.bin", "loader_nor.bin",
            "av-cam.bin", "bonobo.bin", "wole_app.bin", "darwin_core.bin", "appFw.so",
            "pcie_phy_fw.bin", "vmlinux.bin"]
    import subprocess
    for rel, size, h, magic in invent_rows[cam]:
        base = os.path.basename(rel)
        if base in keys and size < 90_000_000:
            p = os.path.join(root, rel)
            gz = f"{OUT}/strings_corpus/{cam}_{base}.strings.txt.gz"
            r = subprocess.run(f"strings -n 6 '{p}' | gzip > '{gz}'", shell=True, capture_output=True)
            print(f"[{cam}] strings {base} -> {os.path.getsize(gz)} bytes gz", file=sys.stderr)

def copy_small_text(cam, root):
    picks = ["firmware.tar_unpacked/0100_config/mount.conf",
             "firmware.tar_unpacked/0100_config/big_backup.conf",
             "firmware.tar_unpacked/0300_partconf/partinf.conf",
             "firmware.tar_unpacked/0700_part_image/dev/nflasha8_unpacked/tomco.txt",
             "config.yaml"]
    os.makedirs(f"{OUT}/{cam}_meta", exist_ok=True)
    for rel in picks:
        src = os.path.join(root, rel)
        if os.path.exists(src):
            dst = f"{OUT}/{cam}_meta/" + rel.replace("/", "__")
            try:
                data = open(src, "rb").read()
                open(dst, "wb").write(data)
            except OSError:
                pass

invent_rows = {}
for cam, root in CAMS.items():
    invent_rows[cam] = invent(cam, root)
    version_sweep(cam, root, invent_rows[cam])
    vermagic(cam, root, invent_rows[cam])
    elf_symbols(cam, root, invent_rows[cam])
    key_strings(cam, root)
    copy_small_text(cam, root)

# cross diff
r1 = {rel: (size, h) for rel, size, h, magic in invent_rows["a1"]}
r2 = {rel: (size, h) for rel, size, h, magic in invent_rows["a1m2"]}
same = diff = only1 = only2 = 0
with open(f"{OUT}/cross_diff.tsv", "w") as f:
    f.write("rel\tstatus\ta1_size\ta1m2_size\n")
    for rel in sorted(set(r1) | set(r2)):
        if rel in r1 and rel in r2:
            if r1[rel][1] == r2[rel][1]:
                same += 1; st = "SAME"
            else:
                diff += 1; st = "DIFF"
            f.write(f"{rel}\t{st}\t{r1[rel][0]}\t{r2[rel][0]}\n")
        elif rel in r1:
            only1 += 1; f.write(f"{rel}\tONLY_A1\t{r1[rel][0]}\t\n")
        else:
            only2 += 1; f.write(f"{rel}\tONLY_A1M2\t\t{r2[rel][0]}\n")
print(f"cross-diff: SAME={same} DIFF={diff} ONLY_A1={only1} ONLY_A1M2={only2}", file=sys.stderr)
print("CORPUS DONE", file=sys.stderr)
