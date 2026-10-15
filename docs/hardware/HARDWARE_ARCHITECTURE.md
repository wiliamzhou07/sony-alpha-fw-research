# Sony α1 / α1 II 硬件架构（固件实证）

> 数据来源：两台相机 Ver.4.00 固件完整解密树。设备树 `cxd90057.dtb` 两台 **MD5 逐字节一致**，故硬件描述对两台通用；差异单独标注。
> 核心结论：**两台相机是同一套硬件平台**（同主 SoC、同协处理器、同内存架构、同外设布局），α1 II 的差异只在软件/固件版本与个别芯片（网卡）。

---

## 0. 总体架构（一张图）

```
┌─────────────────────────────────────────────────────────────┐
│  CXD90057  主 SoC（应用处理器）                                │
│  ├─ 4× ARM Cortex-A35 (armv8)  ← 跑 Linux 4.9 / Android 应用  │
│  ├─ 8GB DRAM @ 物理 0x400000000                               │
│  ├─ GIC-400 中断控制器 / PMU / armv8-timer(2MHz)               │
│  ├─ 外设: 5×SPI, 5×UART, 2×I2C, USB3(DWC3), eMMC, FEC(网卡MAC)│
│  ├─ 5×PCIe 控制器(含 endpoint)                                 │
│  └─ 加密: spacc(安全加速) + elpspacc                           │
└──────────────┬──────────────────────────────────────────────┘
               │ PCIe (pci_ep_cp.ko / icdt.ko)
               │  ├─ pcie_i: 4 lanes（高带宽→成像）
               │  ├─ pcie_m0/m1: 各 2 lanes
               │  └─ pcie_c/n: 各 1 lane
┌──────────────┴──────────────────────────────────────────────┐
│  CXD90058  协处理器（CP，成像/AF 引擎）                        │
│  ├─ NPU（神经网络加速）← AF 主体识别/姿态估计                  │
│  ├─ 独立 RAM（tomco.txt 划分，α1 II 多划 192MB 给 AI）         │
│  ├─ 从 SPI (loader_spi.bin) 启动，跑 cpapp-b.bin             │
│  └─ 读取 /usr/sabin/*.bin 字典 + /usr/data/ai_dict/*.nab     │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  存储: 内部 NVMe NAND（nflasha1-30 分区）+ SD/CFexpress 卡     │
│  NOR flash: bootloader（loader_nor.bin，独立芯片）            │
└─────────────────────────────────────────────────────────────┘
```

## 1. 主 SoC：CXD90057（应用处理器）

设备树 `cxd,cxd90057`，两台完全一致。

### CPU
- **4× ARM Cortex-A35**（armv8，spin-table 启动，共享 L2 cache）
- GIC-400 中断控制器、armv8-pmuv3 PMU、armv8-timer（2MHz）
- 控制台：serial0 @ 460800 baud（与协处理器 tomco.txt 的 uart_baudrate 一致）

### 内存
- **8GB DRAM**（dtb `memory@400000000`，reg size=0x200000000）@ 物理地址 0x400000000
- IO 映射：
  - `iomem@0xf0000000`：224MB 外设寄存器区（所有 0xF1xxxxxx 设备）
  - `esram@0xfe000000`：16MB 嵌入式 SRAM
  - `iomem2@0xf0000000`：16MB（phys 0xff000000）

### 外设（地址 → 功能）
| 地址 | 设备 | 说明 |
|---|---|---|
| F1017000–F101B000 | 5× SPI (arm,pl022) | 接协处理器/EEPROM/外设 |
| F1000000–F1004000 | 5× UART (arm,pl011) | 串口（serial0=控制台） |
| F1012000/F1013000 | 2× I2C (designware) | 传感器/电源管理 |
| F10C0000 | USB3 (snps,dwc3) | USB 设备/主机 |
| F7000000/F6800000/F6C00000/F7400000/F6400000 | 5× PCIe (snps,dw-pcie + cxd900xx-pcie-ep) | **芯片间互联**（见 §3） |
| F10DA000 | **FEC** (dev,fec) | **片上以太网 MAC** |
| F1056000/F1057000 | 2× MDMA (arm,pl330) | DMA |
| F7FC0000 | **spacc** | **安全/加密加速器** |
| F1388000 | SCU (cxd900xx,scu) | 时钟控制器 + 复位 |
| F1080000 | usbs | USB 相关 |

## 2. 协处理器：CXD90058（CP，AF/成像引擎）

- **形态**：独立芯片，不在主 SoC 的 dtb 里；由主 SoC 通过 PCIe 互联
- **启动**：从 CP Data 分区（nflasha8）经 **SPI（loader_spi.bin）** 加载，跑 **cpapp-b.bin**
- **证据两台同款**：两台 `loader_spi.bin` MD5 逐字节一致（芯片强相关）
- **NPU**：cpapp-b.bin 内含大量 NPU 代码（α1 也有，265 处引用）——**α1 现有的主体识别就跑在这颗 NPU 上**
- **内存（tomco.txt 划分，属软件配置）**：
  - α1：用到 ~3GB（memcfg 最大 0x40000000@0x80000000）
  - α1 II：多划一块 `0xC000000@0xD4000000:du`（192MB，AI 专用），用到 ~3.5GB
- **读取的字典**（存在主 SoC 的 /usr/sabin、/usr/data 里，经 PCIe 读取）：
  - α1：aed/bed/dcv_psf 等（现有主体识别）
  - α1 II：+ `ai_dict/default/default.nab`（40MB 姿态模型）+ `scd_dic1/2/3.bin`（新主体）

## 3. 芯片间互联（主 ↔ 协处理器）

- **物理层**：PCIe。5 个 PCIe 控制器，每个带 `cxd900xx-pcie-ep`（endpoint）：
  - `pcie_i`：**4 lanes**（高带宽 → 成像/协处理器数据）
  - `pcie_m0`/`pcie_m1`：各 2 lanes
  - `pcie_c`/`pcie_n`：各 1 lane
- **驱动**：`pci_ep_cp.ko`（主↔CP 链路，`udif_pci_ep_cp`）、`pcie-if.ko`、`pcieatu.ko`、`icdt.ko`（Inter-Chip Data Transfer）、`mcmn_drv.ko`
- **CP 的 PCIe PHY 固件**：CP Data 分区里的 `pcie_phy_fw.bin`（两台一致）
- 应用层库：`libInfraInterchipDatatrans.so`（两台 MD5 一致 → 传输协议相同）

## 4. 存储结构（内部 NVMe NAND）

- **内部存储 = NVMe SSD**（`nvme.ko`，走 PCIe），设备节点 `/dev/pnflasha`（物理）、`/dev/cnflasha`、`/dev/nflasha`（符号链接）
- 30 个分区（nflasha1–30），挂载与角色（partinf.conf + mount.conf）：

| 分区 | 大小(α1/α1 II) | 挂载 | 角色 |
|---|---|---|---|
| nflasha1 | 24MB | — | **SYSTEM (Updater)** 更新系统 |
| nflasha2 | 20MB | /setting | 设置（含 Backup.bin） |
| nflasha3 | 75MB | /system | **SYSTEM (Main)**：vmlinux+initrd+av-cam |
| nflasha4 | 12MB/**0** | raw | MPR Flash Backup（α1 II 裁掉） |
| nflasha5 | 300/**350MB** | /wbi | Warm Boot Image |
| nflasha6 | 25MB | — | Jiritsu |
| nflasha7 | 16MB | /rootfs | Rootfs |
| nflasha8 | 64MB | /cp | **CP Data（协处理器固件/数据）** |
| nflasha10 | 12MB | /tmp | tmp |
| nflasha11 | 500/**250MB** | /log | 日志 |
| nflasha12 | 40MB | /cert | 证书 |
| nflasha15 | 500/**808MB** | /usr | **主应用区（appFw.so/AI 模型/字典/库）** |
| nflasha16 | 0/**25MB** | raw | α1 II 新增 |
| nflasha18 | 20MB | /lens | 镜头数据 |
| nflasha22 | 0/**45MB** | User | α1 II 新增 |
| nflasha23 | 64MB | Customer | 用户区 |
| nflasha30 | 22MB | User | 用户区 |

- 外部存储：SD / CFexpress Type A（mmc_drv.ko / ms_drv.ko，即 MSC 模式暴露的卡）

## 5. 启动链（防砖关键）

```
① Boot ROM（CXD90057 内，不可变）
② loader_nor.bin（NOR flash，独立芯片，0750_nor_loader）
      └─ Init InfSec → 签名校验(INS:Sign) → 决定启动模式（含 Force Update 恢复模式）
③ vmlinux.bin + initrd.img（nflasha3 SYSTEM Main）
      └─ Linux 4.9.337-scel 内核
④ /sbin/init（initrd）→ insmod_drv 加载驱动 → setup_nflash 挂载分区 → setup_rootfs
⑤ /sbin/init2 → 读启动模式（/setting/mode/dmode、upm_bootmode）→ 正常/更新/senser
⑥ 主系统：nflasha15(/usr) 的 appFw.so + 各服务
   协处理器：SPI 加载 cpapp-b.bin（nflasha8 CP Data）
```

- **防砖要点**：② NOR loader 在独立芯片，含 Force Update 恢复模式；刷机不动它即可保住恢复通道
- **更新期校验**：config.xml 全是 CRC32（us_crc32sum），无 RSA 签名步骤

## 6. 外设清单（kmod = 硬件）

| 类别 | 驱动 | 对应硬件 |
|---|---|---|
| 成像编解码 | codec_drv.ko | **imola2 编解码器**（vcd_firmware_imola2.bin，两台一致） |
| 网络 | dev_fec/drv_fec | 片上以太网 MAC |
| 网络(外置) | **r8168.ko**(α1) / **r8125.ko**(α1 II) | **Realtek 1GbE / 2.5GbE 网卡** |
| WiFi | wlan.ko, wlanIrq.ko | 无线网卡 |
| 蓝牙 | btfw32.tlv（固件，两台一致） | 蓝牙芯片（α1 II 增 BT Classic+MFi） |
| NFC | **nfc.ko**(仅 α1) | NFC（α1 II 砍掉） |
| 内部存储 | nvme.ko | NVMe NAND |
| 卡存储 | mmc_drv, ms_drv | SD/CFexpress/MemoryStick |
| 主↔CP | pci_ep_cp, icdt, mcmn_drv | PCIe 互联 |
| 加密 | ccm, crypto_kapi, elpspacc, spacc | 安全加速器 |
| USB gadget | g_mass_storage, g_webcam, usb_f_uvc/uac2, **usbg_sen**(senser!), usbg_stillimage/iap | USB 设备功能（MSC/UVC/senser 服务通道） |
| 音频 | snd-* (ALSA) | 音频编解码 |
| 视频 | v4l2, videodev, videobuf2 | V4L2 视频管线 |
| 流媒体 | stream.ko, stream2.ko | 媒体流（α1 II 增 GStreamer/RTMP/SRT 库） |
| IO | input, ioexp, indctr, liro, compass | 按键/IO 扩展/指南针 |
| 系统服务 | backup, dmm, kikilog, udate, upm, osal_* | Sony 备份/日志/更新/电源 |

## 7. 与固件分区的对应总结

| 硬件 | 对应固件位置 |
|---|---|
| 主 SoC 内核/驱动 | nflasha3 (vmlinux.bin, initrd.img, kmod/) |
| 主 SoC 应用/框架 | nflasha15 (/usr: appFw.so, lib*.so, sabin/, data/ai_dict/) |
| 协处理器固件 | nflasha8 (cpapp-b.bin, loader_spi.bin, tomco.txt) |
| 协处理器 ISP 核 | 0640_darwin (darwin_core.bin) |
| Bootloader | 0750_nor_loader (loader_nor.bin) + NOR flash |
| 编解码器固件 | nflasha15/codec (vcd_firmware_imola2.bin) |
| 更新系统 | nflasha1 (updater.img) |
| 区域/校准/设置 | 0110_backup (CX885xx/CH885xx .bin) + nflasha2(/setting) |
| 蓝牙固件 | nflasha3 (btfw32.tlv, btnv32.bin) |

## 8. 对 AI 对焦移植的直接含义

1. **主 SoC 完全相同**（dtb/CPU/内存/外设一致）→ /usr 应用层、AI 框架、模型文件在主 SoC 上**无硬件障碍**
2. **协处理器同款**（loader_spi.bin 一致）→ α1 II 的 cpapp-b.bin **理论上能在 α1 的协处理器上跑**
3. **唯一硬件级不确定**：协处理器**物理内存是否同大**（α1 II 固件多划 192MB AI 区；固件里查不到物理 RAM 大小）——只能实测
4. **传输协议相同**（libInfraInterchipDatatrans.so 一致）→ 主程序与协处理器指令兼容概率高
5. **存储约束**：α1 II /usr 808MB > α1 500MB 分区，整套换 /usr 需重新分区（改 partinf.conf + us_mkfs）
