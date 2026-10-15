#!/bin/bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export _JAVA_OPTIONS="-Xmx14g -Xms4g"
AH=/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless
SP="<workspace>/firmware_reverse/ghidra_scripts"
OD="<workspace>/firmware_reverse/decompiled"
A9=/tmp/a9m2_fw/firmware.tar_unpacked/0700_part_image/dev/nflasha3_unpacked
A1=/tmp/a1_v400/firmware.tar_unpacked/0700_part_image/dev/nflasha3_unpacked
echo "[$(date +%H:%M)] START a9m2 avcam"
$AH /tmp/ghidra_proj fwproj -import "$A9/av-cam.bin" -overwrite -processor ARM:LE:32:v7 -loader BinaryLoader -loader-baseaddr 0x635c6000 -scriptPath "$SP" -postScript DumpDecomp.java "$OD/a9m2_avcam.c" 100000 > /tmp/gh_a9m2_avcam.log 2>&1
echo "[$(date +%H:%M)] DONE a9m2 avcam exit=$?"
echo "[$(date +%H:%M)] START a1 avcam"
$AH /tmp/ghidra_proj fwproj -import "$A1/av-cam.bin" -overwrite -processor AARCH64:LE:64:v8A -loader BinaryLoader -loader-baseaddr 0xffffffc001000000 -scriptPath "$SP" -postScript DumpDecomp.java "$OD/a1_avcam.c" 100000 > /tmp/gh_a1_avcam.log 2>&1
echo "[$(date +%H:%M)] DONE a1 avcam exit=$?"
echo "[$(date +%H:%M)] A9M2 QUEUE DONE"
