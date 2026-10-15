#!/bin/bash
# queue_full_traversal.sh — 阶段0 新反编译队列（2026-10-11）
# 顺序：Block B 依赖的小文件优先 → 杂项 → appFw 两个大头
# ELF 文件走默认 ELF loader（自动识别语言）；裸二进制走 BinaryLoader+baseaddr
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export _JAVA_OPTIONS="-Xmx12g -Djava.awt.headless=true"
AH=/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless
SP="<workspace>/firmware_reverse/ghidra_scripts"
OD="<workspace>/firmware_reverse/decompiled"
RA="<workspace>/re_assets"
PROJ=/tmp/ghidra_proj
mkdir -p "$PROJ" "$OD"

# run_elf <in> <out.c> <log>
run_elf(){ echo "[$(date +%H:%M)] ELF START $(basename "$1")"; "$AH" "$PROJ" fwproj -import "$1" -overwrite -scriptPath "$SP" -postScript DumpDecomp.java "$2" 100000 > "$3" 2>&1; echo "[$(date +%H:%M)] ELF DONE $(basename "$1") exit=$?"; }
# run_raw <in> <proc> <base> <out.c> <log>
run_raw(){ echo "[$(date +%H:%M)] RAW START $(basename "$1")"; "$AH" "$PROJ" fwproj -import "$1" -overwrite -processor "$2" -loader BinaryLoader -loader-baseaddr "$3" -scriptPath "$SP" -postScript DumpDecomp.java "$4" 100000 > "$5" 2>&1; echo "[$(date +%H:%M)] RAW DONE $(basename "$1") exit=$?"; }

# --- 1) Block B 依赖（kmod 未剥符号，反编译快）---
run_elf "$RA/a1m2/kmod/liro.ko"                          "$OD/a1m2_liro.c"           /tmp/gh2_liro.log
run_elf "$RA/a1m2/kmod/pci_ep_cp.ko"                     "$OD/a1m2_pci_ep_cp.c"      /tmp/gh2_pci_ep_cp.log
run_elf "$RA/a1m2/kmod/icdt.ko"                          "$OD/a1m2_icdt.c"           /tmp/gh2_icdt.log
run_elf "$RA/a1m2/kmod/mcmn_drv.ko"                      "$OD/a1m2_mcmn.c"           /tmp/gh2_mcmn.log
run_elf "$RA/a1m2/kmod/pcie-if.ko"                       "$OD/a1m2_pcie_if.c"        /tmp/gh2_pcie_if.log
run_elf "$RA/a1m2/kmod/pcieatu.ko"                       "$OD/a1m2_pcieatu.c"        /tmp/gh2_pcieatu.log
run_elf "$RA/a1m2/lib/libInfraInterchipDatatrans.so"     "$OD/a1m2_interchip.c"      /tmp/gh2_interchip.log
run_elf "$RA/a1m2/lib/libInfraSKD.so"                    "$OD/a1m2_skd.c"            /tmp/gh2_skd.log

# --- 2) 杂项小裸二进制 ---
run_raw "$RA/a1m2/system/bonobo.bin"   AARCH64:LE:64:v8A 0x0 "$OD/a1m2_bonobo.c"    /tmp/gh2_bonobo.log
run_raw "$RA/a1m2/nor/darwin_core.bin" AARCH64:LE:64:v8A 0x0 "$OD/a1m2_darwin.c"    /tmp/gh2_darwin.log
run_raw "$RA/a1m2/nor/loader_nor.bin"  AARCH64:LE:64:v8A 0x0 "$OD/a1m2_loader_nor.c" /tmp/gh2_loader_nor.log

# --- 3) appFw 两个大头（数小时级）---
run_elf "$RA/a1m2/lib/appFw.so" "$OD/a1m2_appfw.c" /tmp/gh2_appfw_a1m2.log
run_elf "$RA/a1/lib/appFw.so"   "$OD/a1_appfw.c"   /tmp/gh2_appfw_a1.log
echo "[$(date +%H:%M)] ALL QUEUE2 DONE"
