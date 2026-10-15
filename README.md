**English** | [简体中文](README.zh-CN.md)

# sony-alpha-fw-research

Firmware reverse engineering of the Sony α1 (ILCE-1) / α1 II (ILCE-1M2) and research on porting the α1 II's AI autofocus — analysis documents, tools, and data tables.

> **Important notice**: this repository **does not contain or distribute any Sony firmware, models, or binaries**.
> Everything here falls into three categories: (1) research documents derived from analyzing official
> firmware we decrypted ourselves; (2) original tooling; (3) factual data tables extracted from the
> firmware (registries / function indexes / diff results).
> To use the tools you must supply your own legally obtained firmware update package.

## Overview

Goal: fully understand the α1 II's new "AI autofocus" (human pose estimation + new subject recognition)
and assess whether it can be ported to the α1, the previous-flagship on the same platform.

Both cameras share the same dual-chip platform — CXD90057 (main SoC, 4× Cortex-A35, running Linux)
plus CXD90058 (coprocessor with an NPU) — and the α1 II's differences are concentrated in the
software layer. This conclusion comes from a file-by-file comparison of the fully decrypted
firmware trees of both generations.

### Highlights

- **gen5 firmware decryption fully worked out**: UFU container → FDAT (AES header + CBC body); decrypt/repack verified byte-identical round-trip (`tools/firmware/gen5_pack.py`)
- **Complete hardware architecture analysis**: device tree, per-driver diff of 123 kernel modules, comparison of 15 coprocessor firmware blobs (`docs/hardware/`)
- **Full-chain AI autofocus reverse engineering**: the recognize → keypoint → AF decision pipeline inside the CP-side `cpapp`; Adam sequencer, STAPLE/ReID/face ID, eye selection, priority judgment, human-crossing occlusion, PDAF/defocus chain, AE/AWB ownership — 16 reports (`docs/ai-af/`)
- **Function-level a1 ↔ a1m2 appFw diff**: a multi-stage matching engine chain (string anchors → call-graph propagation → LIS landmark chains → greedy optimal pairs) reaching **88% coverage / ~95% pairing accuracy**; A/B/C/D porting-risk grading of 45 PIDs missing on the α1 (`data/diff/`, `data/registries/`)
- **A7M4 eMMC dump decryption**: SDM2 partition table + AES-XTS key derivation; rootfs/usr partitions decrypted and verified running under QEMU (`tools/firmware/decrypt_a7m4_emmc.py`)
- **Booting Sony's firmware Linux in QEMU**: generic ARM64 kernel + official rootfs → busybox shell (`tools/qemu/`)
- **Serial access routes**: a senser service-channel bridge (PTY+TCP+logging, read-only by design) and a bootrom serial-boot bridge (`tools/serial-bridge/`)
- **The default.nab pose model format largely decoded**: conclusion that weight blocks are NPU SRAM mirrors, plus the parsing process (`docs/ai-af/NOTES_NAB_REVERSE.md`)

> Note: most of the in-depth documents under `docs/` are written in Chinese; tool comments and data tables are mixed Chinese/English.

## Repository layout

```
docs/
  overview/      Project master report & state archive (start with FIRMWARE_REVERSE_REPORT.md)
  hardware/      Hardware architecture, driver mapping, firmware partition map, cross-gen comparison, device tree
  ai-af/         AI-AF main document (AF_LOGIC.md) + 12 topic reports + enum notes
  porting/       Porting feasibility analysis, brick-safety analysis
  keys-access/   Key derivation system, key-hunting log, senser service mode, access routes
tools/
  firmware/      Firmware unpack / decrypt / repack (bring your own official update package)
  qemu/          QEMU launch scripts
  analysis/      Ghidra-output analysis: diff engine chain, disassembly scanners, function extraction, .nab parsing
  ghidra/        Ghidra headless batch scripts
  serial-bridge/ Camera serial bridge tools (GPL-3.0, see LICENSE in that directory)
data/
  registries/    PID/NID property registries (CP side + appFw side + cross-gen diff grading)
  fun-index/     Function→string-reference indexes (cpapp / appFw / avcam, for a1 and a1m2)
  diff/          Final a1↔a1m2 appFw function diff results (appfw_diff_summary_v9.tsv)
  nab/           default.nab parsing artifacts (block tables / weight-table structure)
  inventory/     Firmware tree inventories, ELF audits, kmod vermagic, cross-gen diff
vendor/fwtool-gen5/  gen5-enhanced branch of fwtool.py (MIT, see LICENSE.txt inside vendor)
```

## Getting started (reproducing the decryption)

```bash
# 1) Bring your own official firmware update package (BODYDATA.DAT, from Sony's download site)
# 2) Extract the FDAT with fwtool-gen5, then decrypt with the gen5 keys
python3 vendor/fwtool-gen5/fwtool.py unpack -f your_updater.exe -o outDir
python3 tools/firmware/gen5_pack.py --help   # decrypt / repack

# 3) Keys and format details: docs/keys-access/KEY_DERIVATION.md
#    (the gen5 AES keys were first published by q19032/Sony-firmware-unpacker;
#     this project only provides an engineered wrapper)
```

## Suggested reading order

1. `docs/overview/FIRMWARE_REVERSE_REPORT.md` — project-wide summary
2. `docs/hardware/HARDWARE_ARCHITECTURE.md` — the dual-chip platform conclusion
3. `docs/ai-af/AF_LOGIC.md` — main document on the AI-AF decision layer
4. `docs/ai-af/REPORT_a1_a1m2_appfw_diff.md` — cross-gen diff methodology and findings
5. `docs/porting/AI_AF_PORTING_FEASIBILITY.md` — porting feasibility (incl. dead ends)

## Confirmed dead ends (so you don't repeat them)

- The 256-byte RSA-2048 signature at the end of FDAT is verified by the boot ROM — **flashing modified firmware is a dead end** (error code 0x56)
- On China-market (CN2) α1 bodies, all three senser read channels are locked by `libsencore.so` (present since V1.35)
- MSC-ext is read-only; updater commands don't respond in MSC mode
- The camera-specific kernel won't boot on QEMU's virt machine (memory base / UART mismatch) — use a generic kernel + the official rootfs

See `docs/porting/BRICK_SAFETY.md` and the "dead ends" sections of individual documents.

## License

- Main repository: **MIT** (`LICENSE`)
- `tools/serial-bridge/`: **GPL-3.0** (reuses the protocol implementation of [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) at runtime, see `LICENSE` in that directory)
- `vendor/fwtool-gen5/`: retains the MIT license of upstream [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py)

## Credits

- [q19032/Sony-firmware-unpacker](https://github.com/q19032/Sony-firmware-unpacker) — the gen5 AES keys
- [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py) — the firmware unpacking foundation
- [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) — senser/PMCA protocol implementation
- [DavidBuchanan314/ILCE-7M4-RE](https://github.com/DavidBuchanan314/ILCE-7M4-RE) — the A7M4 bootrom serial-boot route (this project's A7M4_ROUTE builds on it)
- [whc2001/SonyMultiPortRemoteControl](https://github.com/whc2001/SonyMultiPortRemoteControl) — Multi-port remote-control protocol reference

## Disclaimer

This project is provided for **security research, interoperability research, and personal learning** only.
The repository contains no copyrighted Sony material; all encryption keys appearing in the documents
and tools were already public community knowledge. Any write operation against camera firmware
(flashing) carries a brick risk; the analyses here do not constitute operational advice, and you assume
all risk. Not affiliated with Sony Corporation.
