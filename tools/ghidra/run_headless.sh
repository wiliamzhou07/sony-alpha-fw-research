#!/bin/bash
# usage: run_headless.sh <binary> <processor> <baseaddr> <out.c> [maxfuncs]
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
set -e
AH=/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless
PROJ=/tmp/ghidra_proj
mkdir -p "$PROJ"
"$AH" "$PROJ" fwproj -import "$1" -overwrite \
  -processor "$2" -loader BinaryLoader -baseaddr "$3" \
  -scriptPath "<workspace>/firmware_reverse/ghidra_scripts" \
  -postScript DumpDecomp.java "$4" "${5:-100000}" 2>&1 | tail -4
