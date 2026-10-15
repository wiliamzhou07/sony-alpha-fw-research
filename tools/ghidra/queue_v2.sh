#!/bin/bash
# queue_v2.sh — appFw 截断补量 + bonobo/darwin 基址重试
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export _JAVA_OPTIONS="-Xmx12g -Djava.awt.headless=true"
AH=/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless
SP="<workspace>/firmware_reverse/ghidra_scripts"
OD="<workspace>/firmware_reverse/decompiled"
RA="<workspace>/re_assets"
PROJ=/tmp/ghidra_proj
mkdir -p "$PROJ" "$OD"

# 1) a1 appFw: 复用工程内已分析程序,只重导(免数小时重分析)
echo "[$(date +%H:%M)] REDUMP a1 appfw (process)"
"$AH" "$PROJ" fwproj -process appFw.so -noanalysis -scriptPath "$SP" \
  -postScript DumpDecomp.java "$OD/a1_appfw.c" 400000 > /tmp/gh2_appfw_a1_redump.log 2>&1
echo "[$(date +%H:%M)] REDUMP a1 exit=$?"

# 2) a1m2 appFw: 换名重导入(避免覆盖工程内程序)+全量
cp "$RA/a1m2/lib/appFw.so" /tmp/appFw_a1m2.so
echo "[$(date +%H:%M)] IMPORT a1m2 appfw (fresh)"
"$AH" "$PROJ" fwproj -import /tmp/appFw_a1m2.so -overwrite -scriptPath "$SP" \
  -postScript DumpDecomp.java "$OD/a1m2_appfw.c" 400000 > /tmp/gh2_appfw_a1m2_v2.log 2>&1
echo "[$(date +%H:%M)] IMPORT a1m2 exit=$?"

# 3) bonobo: 用 av-cam 同款基址(AARCH64 @0xffffffc001000000)
echo "[$(date +%H:%M)] RETRY bonobo"
"$AH" "$PROJ" fwproj -import "$RA/a1m2/system/bonobo.bin" -overwrite \
  -processor AARCH64:LE:64:v8A -loader BinaryLoader -loader-baseaddr 0xffffffc001000000 \
  -scriptPath "$SP" -postScript DumpDecomp.java "$OD/a1m2_bonobo.c" 100000 > /tmp/gh2_bonobo_v2.log 2>&1
echo "[$(date +%H:%M)] RETRY bonobo exit=$?"

# 4) darwin: 先 ARM32 @0,不行换 AARCH64 @av-cam 基址
echo "[$(date +%H:%M)] RETRY darwin ARM32"
"$AH" "$PROJ" fwproj -import "$RA/a1m2/nor/darwin_core.bin" -overwrite \
  -processor ARM:LE:32:v8 -loader BinaryLoader -loader-baseaddr 0x0 \
  -scriptPath "$SP" -postScript DumpDecomp.java "$OD/a1m2_darwin.c" 100000 > /tmp/gh2_darwin_v2.log 2>&1
echo "[$(date +%H:%M)] RETRY darwin exit=$?"
grep -c "^// ====" "$OD/a1m2_darwin.c" || true
if [ "$(grep -c '^// ====' "$OD/a1m2_darwin.c")" -lt 50 ]; then
  echo "[$(date +%H:%M)] RETRY darwin AARCH64 @0xffffffc001000000"
  "$AH" "$PROJ" fwproj -import "$RA/a1m2/nor/darwin_core.bin" -overwrite \
    -processor AARCH64:LE:64:v8A -loader BinaryLoader -loader-baseaddr 0xffffffc001000000 \
    -scriptPath "$SP" -postScript DumpDecomp.java "$OD/a1m2_darwin.c" 100000 > /tmp/gh2_darwin_v3.log 2>&1
  echo "[$(date +%H:%M)] RETRY darwin v3 exit=$?"
fi
echo "[$(date +%H:%M)] QUEUE2 DONE"
