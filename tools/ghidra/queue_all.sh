#!/bin/bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
AH=/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless
SP="<workspace>/firmware_reverse/ghidra_scripts"
OD="<workspace>/firmware_reverse/decompiled"
A1=/tmp/a1_v400/firmware.tar_unpacked/0700_part_image
A2=/tmp/a1m2_v400/firmware.tar_unpacked/0700_part_image
run(){ echo "[$(date +%H:%M)] START $4"; $AH /tmp/ghidra_proj fwproj -import "$1" -overwrite -processor "$2" -loader BinaryLoader -loader-baseaddr "$3" -scriptPath "$SP" -postScript DumpDecomp.java "$4" 100000 > "$5" 2>&1; echo "[$(date +%H:%M)] DONE $4 exit=$?"; }
run "$A2/dev/nflasha8_unpacked/cpapp-b.bin"  ARM:LE:32:v8     0x00108000           "$OD/a1m2_cpapp.c"      /tmp/gh_cpapp_a1m2.log
run "$A1/dev/nflasha8_unpacked/cpapp-b.bin"  ARM:LE:32:v8     0x00108000           "$OD/a1_cpapp.c"        /tmp/gh_cpapp_a1.log
run "$A2/dev/nflasha3_unpacked/wole_app.bin" AARCH64:LE:64:v8A 0x0                  "$OD/a1m2_wole.c"       /tmp/gh_wole.log
run "$A2/dev/nflasha3_unpacked/av-cam.bin"   AARCH64:LE:64:v8A 0xffffffc001000000   "$OD/a1m2_avcam.c"      /tmp/gh_avcam.log
echo "[$(date +%H:%M)] ALL QUEUE DONE"
