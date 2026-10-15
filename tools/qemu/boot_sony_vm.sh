#!/bin/bash
# boot_sony_vm.sh — 在 QEMU 里启动 Sony α1 固件的 Linux 系统
#
# 用法:
#   ./boot_sony_vm.sh          # 启动并进入交互 shell（Ctrl-A X 退出 QEMU）
#
# 原理:
#   Sony 固件是 ARM64 Linux（内核 4.9.337-scel / glibc 2.25 / BusyBox 1.34.1）。
#   相机专用内核在 QEMU 上起不来（内存基址 0x400000000 + 专用 UART），
#   所以用 Ubuntu arm64 通用内核(6.8) + Sony initrd rootfs 的组合启动。
#   相机程序（busybox、glibc 工具）在用户态正常运行。
#
# 依赖: brew install qemu
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
KERNEL="$DIR/generic-arm64-kernel"
INITRD="$DIR/sony-a1-initramfs.cpio"

exec qemu-system-aarch64 \
  -M virt -cpu max -m 1024 \
  -kernel "$KERNEL" \
  -initrd "$INITRD" \
  -append "console=ttyAMA0" \
  -nographic -serial mon:stdio
