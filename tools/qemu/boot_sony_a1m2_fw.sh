#!/bin/bash
# boot_sony_a1m2_fw.sh — 启动 α1 II (ILCE-1M2) V4.00 固件完整用户态
# rootfs: 固件 nflasha7(骨架) + nflasha15(/usr 全部库 + appFw.so 94MB + AI 字典 default.nab 40MB)
# 已验证: busybox shell / OpenSSL 3.0.2 / ls·uname 等 applet(/bb) 均可用
# 依赖: brew install qemu    退出: Ctrl-A X
DIR="$(cd "$(dirname "$0")" && pwd)"
exec qemu-system-aarch64 -M virt -cpu max -m 4096 \
  -kernel "$DIR/generic-arm64-kernel" \
  -initrd "$DIR/sony-a1m2-fullroot.cpio.gz" \
  -append "console=ttyAMA0" -nographic -serial mon:stdio
