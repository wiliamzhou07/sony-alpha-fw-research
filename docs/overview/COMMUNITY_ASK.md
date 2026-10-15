# 社区求密钥求助帖草稿（可直接粘贴到 https://github.com/ma1co/fwtool.py/issues/45 或 personal-view.com）

（英文版，GitHub 适用；中文版见下）

---
**Subject: Need the gen5 AES key for ILCE-1 (Ver.4.00) and ILCE-1M2 (Ver.4.00) BODYDATA.DAT**

Hi folks,

I am trying to unpack two official Sony firmware packages and would like to study/diff the
internal images (hardware-related partitions):

- `BODYDATA.DAT`      — ILCE-1M2 (α1 II), FDAT model 0x40030023, Ver. 4.00, ~1.14 GiB
- `BODYDATA (1).DAT`  — ILCE-1  (α1),   FDAT model 0x91030085, Ver. 4.00, ~758 MiB

What I could already decode without a key (header only, AES-128-ECB with `key_aes`, same as
issue #39 described):

- FDAT header: UDTRFIRM / 0100 / mode U / LUW N / model / region / firmwareOffset /
  firmwareSize / 2 filesystem entries (updater fs at 0x200, ~1.2 MiB; prod fs empty).
- USB descriptor tables: α1 package = 6 normal PIDs (0448, 047d, 0d15, 0d16, 0d19, 0d1a)
  + updater PID 03e2; α1 II package = 18 normal PIDs + the same updater PID.
- DEND CRC32 of both files verifies against the full content (files are intact, unmodified).

The body (updater "compressed romfs" + the ~1 GiB firmware image) is AES-CBC with an unknown
gen5 key. Per issue #39, the key is embedded in the camera-side `libupdatertalk.so`.

Is there any publicly known gen5 key (or a procedure to extract it without a physical camera)?
If any α7S III / FX3 / α1 / α9 III / α1 II owner could dump `libupdatertalk.so` (e.g., via
sensershell / service mode) and share the AES key, that would be a huge help — happy to share
my unpack pipeline and the full extracted payloads with the community afterwards.

Thanks!
---

（中文版：如果需要发到中文社区）

**标题：求索尼 α1 / α1 II Ver.4.00 固件（BODYDATA.DAT）的 gen5 解密密钥**

大家好，我在尝试解包两份索尼官方固件做内部镜像对比（研究硬件差异）：

- ILCE-1M2（α1 II）Ver.4.00，FDAT model 0x40030023，约 1.14 GiB（未解密）
- ILCE-1（α1）Ver.4.00，FDAT model 0x91030085，约 758 MiB

目前无密钥可解出的部分（AES-128-ECB + key_aes 头）：FDAT 头（UDTRFIRM/0100/模式 U/
model/固件偏移/两个文件系统表项：update fs @0x200 约 1.2 MiB、prod fs 为空）、USB 描述符
表（α1 包 6 个普通 PID + 更新 PID 03E2；α1 II 包 18 个普通 PID）、以及 DEND CRC32 校验
（两个文件都通过，确认是官方原始文件）。

正文（updater 压缩 romfs + 约 1 GiB 固件镜像）是 AES-CBC 的 gen5 加密，密钥在相机侧
`libupdatertalk.so` 里（参考 fwtool.py issue #39）。

请问有没有公开的 gen5 密钥，或无需实体相机就能拿到密钥的方法？如果哪位有 α7S III /
FX3 / α1 / α9 III / α1 II 机器，能通过 sensershell/服务模式导出 `libupdatertalk.so` 并
分享密钥，感激不尽——解包出来的东西我也愿意回馈社区。

---

**附：给未来拿到密钥那一刻的准备（已完成）**
- `unpack_ufu.py` 已写好并验证：`python3 unpack_ufu.py unpack --key2 <hex> <BODYDATA.DAT> -o out`
  一条命令完成 头解密(ECB key_aes) + 正文 CBC(key2, IV@-0x110) + 提取 updater 镜像与
  firmware.tar 并列出内容。
- 已知 gen5 结构：头 512B = AES-128-ECB(key_aes)；正文 = AES-CBC(key2, IV=payload[-0x110:-0x100])。

---

## ⭐ 2026-08-28 更新：α1 服务模式已实测攻破——请社区接力最后一棒

**我们已经做到（真机实测，ILCE-1 fw 4.00, 序列 5173****, Backup region CH88501_CN2）：**
- ✅ 在真实 α1 上成功进入 senser 服务模式（StartSenser 0x37ff/0xd7aa + 老 senserKeys 认证，
  设备枚举 PID 0x0336 → SHA256 密钥路径仍有效）
- ✅ 认证后 `info` 可用（Model/Product code/Serial/Backup region 全部读出）
- ❌ **但 gen5 senser 子系统锁死**：文件控制(pull)→Error 128；终端(terminal)→USB 写 EP 无响应；
  内存转储→Error 128；备份(adjust)→Error 129。旧代"终端+文件+备份"三通道全部不可用。

**我们需要帮助的具体问题（任一即可解锁整个计划）：**
1. gen5（BIONZ XR）机型的 **libupdatertalk.so 在 senser/MSC 下如何读取**？
   是否有已知的 **MSC 扩展命令（0x7A 通道）写读命令表**能访问系统分区/内存？
2. 已知 **gen5 密钥与算法**吗？我们验证体系完备（FDAT 头已全解、成品密钥可一键提取、解包管线已彩排），
   拿到 libupdatertalk.so 或密钥即完成全部解包并回馈社区（含 FDAT gen5 完整解密工具）。
3. 或：α1 进入 **updater 模式（PID 0x03e2）后**有没有可用的只读通道？

**我们可交换**：完整的 gen5 senser 切换+认证+info 流程复现脚本、FDAT 头解码、以及解包后的
α1/α1 II 分区/固件对比成果（对社区逆向价值巨大）。
