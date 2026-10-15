#!/bin/bash
# boot_sony_a7m4_fw.sh — 启动 Sony a7 IV (ILCE-7M4) 固件完整用户态
# rootfs 来源: A7M4 EMMC SY1122 转储 → AES-XTS 解密 nflasha7(rootfs) + nflasha15(/usr)
# 原生 ext2 自带正确执行位与符号链接; 已验证: busybox / OpenSSL 1.1.1a / appFw.so(57MB)
# 解密工具: decrypt_a7m4_emmc.py (重解: python3 decrypt_a7m4_emmc.py /tmp/a7m4_parts nflasha7 nflasha15)
# 依赖: brew install qemu    退出: Ctrl-A X
DIR="$(cd "$(dirname "$0")" && pwd)"
exec qemu-system-aarch64 -M virt -cpu max -m 4096 \
  -kernel "$DIR/generic-arm64-kernel" \
  -initrd "$DIR/sony-a7m4-fullroot.cpio.gz" \
  -append "console=ttyAMA0" -nographic -serial mon:stdio
