#!/bin/bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export _JAVA_OPTIONS="-Xmx14g -Xms4g"
AH=/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless
$AH /tmp/ghidra_proj fwproj -import /tmp/a1_v400/firmware.tar_unpacked/0700_part_image/dev/nflasha8_unpacked/cpapp-b.bin -overwrite -processor ARM:LE:32:v8 -loader BinaryLoader -loader-baseaddr 0x00108000 -scriptPath "<workspace>/firmware_reverse/ghidra_scripts" -postScript DumpDecomp.java "<workspace>/firmware_reverse/decompiled/a1_cpapp.c" 100000
echo "RERUN_EXIT=$?"
