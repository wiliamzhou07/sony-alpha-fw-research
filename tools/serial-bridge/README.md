# serial-bridge — Sony 相机串口桥

把相机的 **senser 服务通道**（a7C II senser root shell 同一条通道）桥接到本机，
实现系统底层数据的读取：终端控制台、文件系统、内存转储，全程落盘日志。
协议栈复用本机已有的 [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)
实现（`~/pmca-a1/src/Sony-PMCA-RE-master`），本目录只加"桥"这一层。

> ⭐ **2026-10-09 路线升级**：引入 [DavidBuchanan314/ILCE-7M4-RE](https://github.com/DavidBuchanan314/ILCE-7M4-RE)
> 的 **bootrom 串口引导路线**（Mira=CXD90057 / Cetus=CXD90058 正是 α1 的芯片）——
> 比 senser 更底层、绕开全部固件锁，bootrom 二进制已入库 `../ILCE-7M4-RE/`。
> 详见 **[A7M4_ROUTE.md](A7M4_ROUTE.md)**，工具为 `a1_uart_boot.py`。

## 与 a7C II 破解方法的对应关系

KEY_HUNT_LOG 2026-10-09 调研结论：a7C II 的破解 = **senser root shell**：

| a7C II 破解步骤 | 本工具实现 |
|---|---|
| StartSenser 厂商请求 `(1, 0x37ff, 0xd7aa)` | `ensure_senser()` 自动切换（相机先设 MSC 模式） |
| senserKeys SHA256 三轮挑战-应答认证 | 复用 `SonySenserAuthDevice.authenticate()`（α1 实测可通过） |
| `readTerminal`/`writeTerminal`（终端/root shell） | `bridge` 子命令 → PTY + TCP + 日志 |
| `readFile`（读系统文件） | `readfile` 子命令 |
| `readMemory`（内存转储） | `readmem` 子命令 |
| ~~`writeFile`/`writeMemory`/`deleteFile`~~ | **刻意不实现**（只读设计，见下） |

## 快速开始

```bash
# 0) 相机：菜单 USB连接设为 MSC(大容量存储)，USB 线接 Mac
B=~/pmca-a1/venv/bin/python
cd "<workspace>/serial-bridge"

# 1) 看相机在什么模式
$B senser_bridge.py list

# 2) 建立串口桥（自动: MSC → StartSenser → 认证 → 终端桥）
$B senser_bridge.py bridge
#    输出类似:
#      PTY  : screen /dev/ttys007     ← 用 screen 连上即相机终端
#      TCP  : nc 127.0.0.1 4599       ← 或用 nc
#      日志 : .../serial-bridge/logs/console_XXXX.log

# 3) 底层数据直读（不开终端时）
$B senser_bridge.py readfile /proc/version
$B senser_bridge.py readmem 0xF1000000 0x100

# 4) 用完退出 senser 模式（或直接重启相机）
$B senser_bridge.py exit
```

## 子命令

| 命令 | 作用 |
|---|---|
| `list` | 列出索尼 USB 设备及当前模式（普通/MSC/senser/updater） |
| `bridge` | 串口桥主体：终端通道 ↔ PTY(`screen`) + TCP(`nc`) + 时间戳日志 |
| `capture --seconds N` | 单向捕获终端输出（抓启动日志用） |
| `readfile PATH [OUT]` | senser 文件通道读文件 |
| `readmem BASE SIZE [OUT]` | senser 内存转储（0x 前缀，单次上限 256MB） |
| `info` | 读描述符 + readHasp |
| `exit` | StopSenser，退出服务模式 |

通用选项：`--driver libusb`、`--pmca-home <目录>`、`--debug`（栈回溯）。

## α1（国行 CN2）现状 —— 先读这里

真机实测（KEY_HUNT_LOG 2026-08-28 / 10-08）：

- ✅ StartSenser 切换 + 认证 + readHasp：**通**（PID 0x0336，老 senserKeys SHA256 路径）
- ❌ gen5 固件把三条读通道全部锁死：`readfile`/`readmem` → **Error 128**，
  终端写 EP 无响应，备份 → Error 129（`libsencore.so` 的
  `terminal_change_function_is_disabled` + `A_AS_AREA_CHK`，V1.35 起就有）

因此本桥在 α1 上今天能做的是：**建立桥、认证、日志通道全链路待命**；
一旦有开放 senser 的同平台机器（a7C II / 海外版等）接上来，同一套命令立即变为
完整 root shell 读取。工具对锁定的错误码做了翻译提示，不会误判为工具故障。

## 物理 UART 备选路线（uart-bridge.py）

固件分析确认 CXD90057 控制台为 **PL011 @ 0xF1000000，serial0 460800 8N1**
（`HARDWARE_ARCHITECTURE.md`、`cxd90057_decompiled.dts`）。若拆机在主板找到
UART 焊点，接 3.3V TTL USB 串口线后：

```bash
$B uart-bridge.py --list
$B uart-bridge.py --port /dev/tty.usbserial-XXXX --baud 460800
```

同样得到 PTY + TCP + 日志。⚠️ 相机板是 3.3V TTL：**绝对不要接 RS-232 电平**；
先只接 GND+TX（只读）；波特率不对就扫 9600/115200/230400/460800/921600。
（相机 MultiPort 口另有 9600bps 遥控串口协议，参见
[whc2001/SonyMultiPortRemoteControl](https://github.com/whc2001/SonyMultiPortRemoteControl)、
[gyroflow/flowshutter 引脚文档](https://github.com/gyroflow/flowshutter/blob/master/doc/sony-multi-terminal.md)，
那是遥控协议不是控制台。）

## 只读设计

本工具**不暴露** writeFile/writeMemory/deleteFile（PMCA-RE 里有，但桥不转发）。
理由：α1 刷改固件被 boot ROM RSA-2048 验签封死（错误码 0x56），任何写通道在当前
认知下都可能造成变砖且无收益——详见 `../BRICK_SAFETY.md`。要开写通道需显式改代码，
那是另一个有独立决策的步骤。

## 离线测试（无需相机）

```bash
$B test_bridge_offline.py    # 9 项：PTY/TCP 双向、0x40 分片、日志、退出
```

## 文件

- `senser_bridge.py` — senser 串口桥（主工具，a7C II 方法）
- `a1_uart_boot.py` — **bootrom 串口引导桥**（A7M4 路线 α1 适配：推送载荷 + 载荷控制台接 PTY/TCP/日志）
- `A7M4_ROUTE.md` — A7M4→α1 移植指南（原理/硬件/步骤/未知点/纪律）
- `uart-bridge.py` — 物理 UART 桥（pyserial，备选路线）
- `test_bridge_offline.py` — senser 桥假相机回环测试（9 项）
- `test_uart_boot_offline.py` — uart_boot 记录格式与桥接测试（15 项）
- `logs/` — 桥会话日志（时间戳，双向记录，二进制转义）
