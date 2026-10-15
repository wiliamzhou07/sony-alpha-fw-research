#!/bin/bash
# 启动 α1 V4.00 固件完整用户态（325MB：initrd + /usr 全部 192 个库 + appFw.so + AI 字典）
# 已验证可运行: Sony busybox / OpenSSL 3.0.2 / OpenSSH 7.9p1 / sen.elf(跑到 /dev/uipc 缺失)
# 依赖: brew install qemu
DIR="$(cd "$(dirname "$0")" && pwd)"
exec qemu-system-aarch64 -M virt -cpu max -m 4096 \
  -kernel "$DIR/generic-arm64-kernel" \
  -initrd "$DIR/sony-a1-fullroot.cpio.gz" \
  -append "console=ttyAMA0" -nographic -serial mon:stdio
