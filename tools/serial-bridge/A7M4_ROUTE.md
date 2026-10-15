# A7M4 路线 → α1 移植指南

> 依据: [DavidBuchanan314/ILCE-7M4-RE](https://github.com/DavidBuchanan314/ILCE-7M4-RE)
> （已镜像入库: `../ILCE-7M4-RE/`）。本文件回答：**这对 α1 意味着什么、要什么、按什么顺序做、风险在哪。**

## 一句话结论

A7M4 的"串口桥"不是 senser 终端桥，而是 **bootrom 秘密串口启动模式**的利用链：
Multi 口 RX 脚位敲特定格式 → bootrom 下载器 → 任意内存写 + 改栈绕过解锁检查 →
裸机载荷（fastboot）→ **eMMC 分区读写在 boot 层完成，AES-XTS 可解、无签名校验**。
Mira=CXD90057、Cetus=CXD90058 **正是 α1 的两颗芯片**——这条路线在 α1 上绕开
你们撞墙的全部三层防护（senser 锁、updater RSA 验签、CN2 区域锁），因为它们
都是固件层的锁，而这条路在 boot ROM 层、固件加载之前。

## 为什么判断直接适用于 α1（证据）

| 证据 | A7M4-RE | α1 (本项目) |
|---|---|---|
| 主 SoC | CXD90057 "Mira" | CXD90057（HARDWARE_ARCHITECTURE.md） |
| 协处理器 | CXD90058 "Cetus"（SPI monitor 可读写执行） | CXD90058（PCIe 互联） |
| UART 基址 | 5×PL011 @ F1000000–F1004000 | 完全一致（cxd90057_decompiled.dts） |
| 内核基址 | System RAM @ 0x400000000 | α1 内核绑定 0x400000000（QEMU 起不来原因） |
| 平台驱动 | drivers/udif/mach-**cxd900xx**/platform.c | 同 UDIF 平台族 |

- 仓库直接附带 `bootrom/CXD90057_Mira_0xFFFF0000.bin`（48KB）与
  `bootrom/CXD90058_Cetus_0xFFFF0000.bin` —— **你们一直"不可见不可改"的验签层
  现在是桌面上的静态分析对象**。KEY_HUNT_LOG 里"找 boot ROM 验签漏洞"路线不再
  依赖 QEMU 完整运行固件。
- `emmc_boot/emmc_boot0.bin`（明文 EXBL 头，A7M4 v2.00 原始 eMMC boot0 dump）+
  解密后的 eSRAM 加载器 —— boot 链样本齐全。
  （注意：/tmp/q19 的 α7M5 BOOT1/2 从第 0 字节起就是密文，不是这种原始格式，别再绕那条路。）

## 技术原理（复述要点，详见原仓库）

1. **入口**：复位后短时间内，bootrom 在 Multi 连接器 RX 脚上监听。rp2040 用 PIO
   以 48kbps 位敲自定义帧（1 起始 + 8 数据 LSB + 奇校验 + 1 停止 + 特定填充），
   先发"载波"再发"记录"，记录间隔不得超过 1.2s（`STARVE_MS`）。
2. **记录格式**：`<len:u32><type:u16><value:u32><payload><crc32:u32>`，类型：
   `0x0001 MEM_WRITE`（任意地址写）、`0xffff SET_ENTRY`、`0x0000 SET_UNLOCK`、
   `0x0123 END_MARKER`（会话以重发首记录结束）。
3. **解锁绕过**：解锁码的期望值存在栈上（A7IV: `0xfe02f398`），用 MEM_WRITE 直接
   把期望值改写成自选值 → 不知道真解锁码也能过（已知真码 A7IV=0x2CF25621）。
4. **载荷**：写入 eSRAM 0xFE020000 后跳转。现成 fastboot 载荷提供：
   `peek/poke/exec`、`partition dump`（eMMC 分区转储，AES-XTS 透明解密）、
   `dumpbrom`（转储 bootrom 本体）、以及 **cetus 系列命令**（复位 CP 进 SPI
   monitor，CP 内存/NOR 读写，CP bootrom 转储）。
5. **eMMC 加密**：AES-XTS 每 512B 扇区，tweak=扇区号（LE 16B）。密钥从 bootrom
   内"扰码表"(0xffffb800) 经偏移表派生（boot0 阶段表在 brom+0x6984，分区阶段表在
   eSRAM 加载器 +0x239b0）——**片上派生、非每台随机**，脚本
   `scripts/parse_emmc_boot0.py` / `parse_emmc_partitions.py` 可直接复算。

## 硬件清单

- Raspberry Pi Pico / RP2040-Zero ×1（PIO 位敲是关键，普通 USB-TTL 线替代不了）
- Sony Multi Terminal 转接/焊接方案 ×2（见 `../ILCE-7M4-RE/images/multi_pinout.png`）：
  - 一根接 rp2040：相机 RX/TX + RST + GND（rp2040 端 GPIO28=→相机RX, GPIO29=←相机TX, GPIO27=→RST）
  - 一根接 USB（GND/D+/D-/5V）：给 fastboot 载荷的 USB 2.0 设备用
- aarch64 交叉工具链（fastboot 载荷编译）：`brew install aarch64-elf-gcc` 或 linux `aarch64-linux-gnu-gcc`

### 接线规范（带保护电阻的稳妥版）

| 线路 | 从 | 串联 | 到 |
|---|---|---|---|
| TX（bootrom 命令） | RP2040 GPIO28 | **470Ω** | 相机 Multi RX |
| RX（载荷控制台） | 相机 Multi TX | **470Ω** | RP2040 GPIO29 |
| RST（复位脉冲 10µs） | RP2040 GPIO27 | **470Ω** | 相机 Multi RST |
| GND | 转接板 | 直连 | RP2040 GND（必须共地） |

- 三根信号线在**转接板一侧**各接一个 **10kΩ 上拉到 RP2040 的 3V3**（开漏模式回高；RST 平时保持高）
- 470Ω = 保护电阻（开漏模式下与相机侧驱动冲突时限流 ~7mA）；10kΩ 可用 4.7k–22k；470Ω 可用 330–560Ω
- USB 转接一路（GND/D+/D-/5V）纯直连无电阻——可直接买 VMC-MD3 兼容成品线替代
- 若编译 push-pull 版（不带 `-DOPEN_DRAIN`）上拉可省，470Ω 保留
- **上电前三查**：相邻针脚无短路 / 信号线对 GND 无短路 / 信号线对 3V3 万用表读出 ~10k（不是 0）
- 针脚认定锚点法：先焊 USB 转接插到相机，用通断档标定转接板上 GND/5V/D+/D- 的实际针位，
  再按 pinout 图数出串口三根针；交叉参考
  [Studio1 Productions 索尼 Multiport 引脚表](https://www.studio1productions.com/sony-pinout)

## 构建与 α1 实施顺序

```bash
cd ../ILCE-7M4-RE

# ① rp2040 桥固件（arduino-cli + earlephilhower rp2040 core）
cd tools/uart_boot && make setup && make && make flash PORT=/dev/ttyACM0

# ② 首次验证：PoC 点灯载荷（不碰任何存储，只调 bootrom 的 LED 函数）
cd ../uart_boot_poc && make   # payload.bin
python3 ../../serial-bridge/a1_uart_boot.py payload.bin -p /dev/ttyACM0 --no-bridge
#    相机 LED 亮 = 串口引导在 α1 上成立，栈绕过偏移可用

# ③ 转储 α1 自己的 bootrom，核对与 A7M4 版本的偏移差异
#    （fastboot 载荷: aarch64-gcc 编译, push 时 --expect '[mira] fastboot ready'）
fastboot oem dumpbrom && fastboot get_staged a1_bootrom.bin
#    与 bootrom/CXD90057_Mira_0xFFFF0000.bin diff：
#    - 一致 → A7IV 的栈偏移/密钥表偏移直接沿用
#    - 有差 → 在 α1 bootrom 里重定位 unlock 期望值栈地址与 0x6984 偏移表

# ④ 只读转储：全部 eMMC 分区（对应你们已知的 nflasha1..nflasha30 命名）
fastboot oem partition                    # 对照 SDM2 分区表
fastboot oem partition dump nflasha5      # WBI 区（CP 固件/暖启动路径）
fastboot oem partition dump nflasha8      # FAT12: MINI_LDR.BIN 所在
fastboot oem partition dump nflasha1      # ...逐个转储，先做两份完整备份

# ⑤ CP (Cetus/CXD90058) 一并拿下
fastboot oem cetus dumpbrom && fastboot get_staged cp_bootrom.bin
fastboot oem cetus dumpnor                # CP NOR（cpapp-b/subcpu 启动链）
```

本目录的 `a1_uart_boot.py` 是原版 `scripts/push_payload.py` 的 α1 适配：推送逻辑
相同，载荷控制台不再只是 stdout echo，而是接上与 senser 桥相同的
PTY(screen) + TCP(nc) + 时间戳日志（TerminalBridge），`--expect` 可等
`[mira] fastboot ready` 再进桥。

## α1 特有的未知点（诚实清单）

1. **bootrom 修订版差异**：α1(2021 初) 与 A7M4(2021 末) 的 CXD90057 掩膜 ROM
   可能是不同修订——解锁栈地址 `0xfe02f398` 与密钥偏移表位置都可能漂移。
   步骤③ 的 dumpbrom 就是为此设计的第一步。
2. **Multi 口引脚定义**：A7M4 与 α1 同为 Sony Multi Terminal（micro-USB 式 10 针），
   引脚图基于 A7M4 实拍；α1 上先万用表核对 RST/线序再上电。
3. **eMMC 密钥**：派生方法已确认——扰码垫(FFFFB800) + 偏移表(brom+0x6984) 选字节，
   A7M4 的 64B 密钥已复算（见 `../KEY_DERIVATION.md`）。只剩"α1 bootrom 是否同修订版"
   一个问题，dumpbrom diff 后即知；异版就重新扫表重算，脚本逻辑不变。
4. **USB 载荷端口**：fastboot 枚举在 Multi 口的 USB 2.0 上——α1 的 Multi 口线序
   需要按引脚图确认（α1 另有独立 Type-C USB3 口，别接错）。

## 写入路径（用户情报，2026-10-10）

社区已知方法（KEY_DERIVATION.md 有完整分析）：

- 更新包（FDAT）路径确实死路——**但改机根本不走这条路**。
- 实际写入路径 = **工程线刷入**（bootrom 级块写入，本路线的 fastboot `oem partition
  dump/flash` 就是它的开源等价物）；机身对写入内容只有 **CRC 校验**，没有签名。
- **A7C2 破解的本质**：解密 eMMC → 改文件 → 再加密 → 写回。密钥由 bootrom 常量表
  按公式/偏移表派生（eMMC 层的派生法已确认并复算，见 KEY_DERIVATION.md）。
- 因此 α1 移植的完整链 = 本路线拿 eMMC 读写 → 按 KEY_DERIVATION.md 的密钥解密
  nflasha* → 移植 α1 II 的 AI 文件 → 重算 CRC → 加密写回。
- ⚠️ 写回纪律不变：两份完整备份 + CRC 校验点全部定位之前，不执行任何写操作。

## 纪律（与 BRICK_SAFETY.md 一致）

- **只读优先**：dump/peek/dumpbrom/cetus peek 随便做；`flash`/`poke`/`exec` 在
  完成两份独立完整 eMMC 备份并校验哈希之前，视为禁手。
- RST 脚的复位脉冲是硬件级操作，外设接线错误可能影响相机供电轨——第一次上电
  前逐根核对。
- 本路线所有产出（bootrom 反汇编、分区 dump）只用于本项目研究目的。

## 对项目全局的影响

- **"三层防护闭合、软件路径穷尽"的结论不变，但不再是终点**：bootrom 串口引导
  在所有固件层防护之前。
- **验签分析可直接开工**：CXD90057 bootrom 已在手（静态逆向 InfSec 验签逻辑，
  找 eMMC 层与 updater 层校验的差异——原仓库已确认 eMMC 层无签名校验，机身 CRC
  级校验的点位清单见 `../KEY_DERIVATION.md` 待验证项）。
- **fastboot 载荷 = 完整的底层读取通道**：比 senser root shell 更底层（固件都没跑），
  且天然绕开 CN2 锁。senser 串口桥降级为辅助通道。
- **密钥体系已定性**：eMMC 层密钥派生法确认且已复算，改机交付机制走 eMMC 写入
  （工程线等价物 = 本路线），FDAT/RSA 死锁不再构成阻塞。详见 `../KEY_DERIVATION.md`。
