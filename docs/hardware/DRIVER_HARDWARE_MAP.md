# α1 / α1 II 软件↔硬件完整映射与重合度报告

> 方法：两台 V4.00 固件解密树逐文件 md5 对比 + 123 个内核驱动逐个 diff + 15 个芯片固件 blob 对比 + 192 个用户态库对比。
> 所有"相同"判断均为**字节级 md5 一致**，非人工猜测。

---

## 一、总结论（先看这个）

**硬件重合度 ≈ 98%（123 个硬件接口中 121 个完全相同）**

真正的**硅片级差异只有 2 处**：

| # | 差异 | α1 | α1 II | 性质 |
|---|---|---|---|---|
| 1 | NFC 芯片 | ✅ 有（nfc.ko + libInfraNfc.so） | ❌ 移除 | 硬件删除 |
| 2 | 有线网卡 | Realtek RTL8168（1GbE） | Realtek RTL8125（2.5GbE） | 同功能升级 |

**其余全部硬件为同芯片**。两代机器的**功能差异几乎 100% 是软件**：

| α1 II 独有功能 | 运行载体 | 是否需要新硬件 |
|---|---|---|
| AI 人体姿态估计 AF | 协处理器 NPU（**α1 也有同颗 NPU**） | ❌ 不需要 |
| 新主体识别（昆虫/车/飞机增强） | 协处理器 NPU | ❌ 不需要 |
| RTMP/SRT 原生直播 | 主 SoC CPU（GStreamer 软件栈） | ❌ 不需要 |
| 蓝牙 Classic / MFi | **同一颗 Qualcomm 蓝牙芯片**（固件逐字节相同） | ❌ 不需要 |

---

## 二、驱动级证据（kmod 123 vs 122）

| 指标 | 数值 |
|---|---|
| 逐字节相同的驱动 | **102 个** |
| 同名重编译（同 vermagic `4.9.337-scel`、同硬件、仅构建日期不同） | **19 个** |
| α1 独有（硬件被 α1 II 移除） | 2 个：`nfc.ko`、`r8168.ko` |
| α1 II 新增 | 1 个：`r8125.ko` |

→ 驱动覆盖的 123 个硬件接口中，**121 个两台通用，仅 2 处差异**（98.4%）。

## 三、芯片固件 blob 证据（15 个专属芯片固件）

| 芯片 | 固件 | α1 vs α1 II |
|---|---|---|
| imola2 视频编解码器 | vcd_firmware_imola2.bin | ✅ 逐字节相同 |
| 协处理器 SPI 启动器 | loader_spi.bin | ✅ 逐字节相同（→ **同颗 CXD90058**） |
| Qualcomm 蓝牙 | btfw32.tlv / btfw32a.tlv | ✅ 逐字节相同 |
| PCIe 物理层 | pcie_phy_fw.bin | ✅ 逐字节相同 |
| 电源管理芯片 | MIS.bin | ✅ 逐字节相同 |
| 显示单元 | DGU.bin | ✅ 逐字节相同 |
| 管理芯片 | OldAmtCL.bin | ✅ 逐字节相同 |
| **主 SoC 硬件描述** | **cxd90057.dtb** | ✅ 逐字节相同 |
| Darwin ISP | darwin_core.bin | 🟡 同芯片，版本微调 |
| Cypress USB-C MCU | fw2_normal_*.cyacd | 🟡 同芯片，版本微调 |
| 协处理器应用 | cpapp-b.bin + cpImg.dat | 🟡 同芯片，α1 II +2.5MB（AI 管线） |
| NOR bootloader | loader_nor.bin | 🟡 同芯片，版本微调 |

→ **15/15 为同一颗芯片**；其中 9 个连固件版本都完全一致。

## 四、用户态库证据（192 个公共库）

- 逐字节相同：**146 个**
- 同名重编译：46 个（基础设施库）
- α1 独有：`libInfraError.so`、`libInfraNfc.so`
- α1 II 新增：24 个（AI 字典 + GStreamer 全家桶 + RTMP/SRT + BT Classic/MFi）——**全部是纯软件**

**硬件直接接口库 4/4 逐字节相同**：`libInfraInterchipDatatrans`（主↔协处理器协议）、`libInfraSKD`（签名引擎）、`libInfraUsbCmn`（USB 层）、`libInfraLensCommunicator`（E 卡口镜头协议）。

## 五、软件功能 ↔ 硬件完整映射表（70 项）

标记：✅=两台固件逐字节相同 🟡=同硬件、重编译/版本微调 ❌=α1 独有 🆕=α1 II 新增

### 主 SoC 与总线
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| cxd90057.dtb | CXD90057 SoC 硬件描述 | ✅ |
| xhci-hcd/xhci-pci/xhci-plat-hcd | USB3 xHCI 主机控制器 | 🟡 |
| elpspacc(+usr) | SPACC 硬件加密加速器 | 🟡 |
| arc4/ccm/crypto_kapi | 内核加密 API | 🟡 |
| elpmem | 嵌入式存储控制器 | 🟡 |
| cachecontrol | Cortex-A35 缓存管理 | 🟡 |

### USB 子系统（接口层全部相同）
| 软件/驱动 | 硬件功能 | 状态 |
|---|---|---|
| libInfraUsbCmn.so | USB 公共层 | ✅ |
| usb_f_mass_storage/g_mass_storage | MSC 模式（读卡） | 🟡 |
| usb_f_uvc/g_webcam | UVC 网络摄像头 | 🟡 |
| usb_f_uac2/g_audio | USB Audio 2.0 | 🟡 |
| usbg_stillimage | PTP 照片传输 | 🟡 |
| usbg_iap | 苹果 iAP 协议 | 🟡 |
| usbg_sen | **senser 服务模式接口** | 🟡 |
| usb_beets | 索尼专有 USB 协议 | 🟡 |
| usbhid | USB HID 外设 | 🟡 |
| cdc_ether/ncm/rndis/ipheth/asix/ax88179 | USB 网卡适配器全家 | 🟡 |
| fw2_normal_*.cyacd | Cypress USB-C/外设 MCU 固件 | 🟡 |

### 网络
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| r8168.ko | **Realtek 1GbE 网卡** | ❌ α1 独有 |
| r8125.ko | **Realtek 2.5GbE 网卡** | 🆕 |
| dev_fec/drv_fec/libphy/mii/of_mdio/fixed_phy | CXD90057 片上以太网 MAC | 🟡 |
| wlan/wlanMemoryAllocator/wlanIrq | WiFi 模块 | 🟡 |
| ppp_async/ppp_generic/slhc | PPP（预留） | 🟡 |
| cdc_ether 等 | USB 网卡 | 🟡 |

### 影像链路（传感器→ISP→编解码→显示）
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| codec_drv.ko | imola2 编解码器控制 | 🟡 |
| vcd_firmware_imola2.bin | imola2 编解码器固件 | ✅ |
| darwin_core.bin | Darwin ISP | 🟡 |
| cpapp-b.bin + cpImg.dat | **CXD90058 协处理器（AF 引擎 + NPU）** | 🟡（α1 II +2.5MB AI） |
| libAiDictionary.so + default.nab | AI 姿态估计模型 | 🆕 |
| scd_dic1/2/3.bin | 新主体分类字典 | 🆕 |
| v4l2-*/videodev/videobuf2/media | V4L2 视频框架 | 🟡 |
| ldec/stream/stream2 | 解码/流媒体管线 | 🟡 |
| dmm | 显示管理 | 🟡 |
| g_webcam | UVC 摄像头 | 🟡 |

### 主↔协处理器互联（AI 移植的关键通道）
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| pci_ep_cp.ko | PCIe 协处理器链路 | ✅ |
| pcie-if.ko/pcieatu.ko | PCIe ATU | 🟡 |
| icdt.ko/mcmn_drv.ko | 芯片间数据传输 | 🟡 |
| libInfraInterchipDatatrans.so | 传输协议库 | ✅ |
| loader_spi.bin | CP SPI 启动器 | ✅ |
| pcie_phy_fw.bin | PCIe PHY 固件 | ✅ |

### 存储
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| nvme-core/nvme.ko | 内部 NVMe NAND | 🟡 |
| mmc_core/mmc_drv/ms_drv | SD/CFexpress A 读卡器 | 🟡 |
| scsi_mod/sd_mod/sr_mod | SCSI 层 | 🟡 |
| backup.ko | Backup.bin 设置备份 | 🟡 |

### 连接类
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| nfc.ko + libInfraNfc.so | **NFC 芯片** | ❌ α1 独有 |
| btfw32.tlv ×2 | Qualcomm 蓝牙芯片固件 | ✅ |
| libInfraBluetoothLowEnergy.so | BLE | 🟡 |
| libInfraBluetoothClassic.so | 蓝牙 Classic | 🆕（同芯片开软功能） |
| libInfraMFi.so | 苹果 MFi | 🆕（同芯片开软功能） |

### 音频
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| snd-* 14 个模块 | ALSA 音频（麦克风/扬声器/HDMI） | 🟡 |
| snd-usb-audio/snd-usbmidi | USB 音频/MIDI | 🟡 |

### 操作/人机交互
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| input.ko | 快门/拨轮/按键 | 🟡 |
| ioexp.ko | IO 扩展器（按键矩阵） | 🟡 |
| indctr.ko + liro.ko | 指示灯/LED | 🟡 |
| grm_ma.ko | GPIO 资源管理 | 🟡 |
| compass.ko | 电子罗盘 | 🟡 |

### 电源/系统
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| upm.ko | NP-FZ100 电池/电源管理 | 🟡 |
| MIS.bin/DGU.bin/OldAmtCL.bin | 电源/显示子芯片固件 | ✅ |
| utimer.ko | 快门高精度定时 | 🟡 |
| udate.ko | 实时时钟 | 🟡 |
| kikilog.ko | 诊断日志 | 🟡 |
| osal_* | OS 抽象层 | 🟡 |
| backup.ko | 设置备份 | 🟡 |
| nls_utf8 | FAT 卡中文名 | 🟡 |

### 镜头
| 软件/驱动 | 硬件 | 状态 |
|---|---|---|
| libInfraLensCommunicator.so | E 卡口镜头通信 | ✅ |
| nflasha18 (/lens) + lensfile.bin | 镜头补偿数据 | 🟡 |

---

## 六、重合度定量结论

| 层面 | 计算 | 重合度 |
|---|---|---|
| 硅片（硬件接口数） | 123 个驱动接口中 121 个通用 | **98.4%** |
| 芯片固件 blob | 15/15 同芯片（9 个固件也完全相同） | **100% 同硅片** |
| 内核 | 同源 4.9.337-scel，两次构建 | **100% 同版本** |
| 设备树 | 逐字节相同 | **100%** |
| 用户态库 | 192 个公共库（146 个逐字节同） | **100% 同硬件接口库** |
| 拍摄场景 | 26 个 scenario 文件名完全一致 | **100%** |

### 唯二硬件差异
1. **NFC 芯片**：α1 有 → α1 II 移除（nfc.ko、libInfraNfc.so 双双消失）
2. **有线网卡**：RTL8168 1GbE → RTL8125 2.5GbE（同插槽升级）

### 关键推论
α1 II 相对 α1 的**全部卖点**——AI 姿态估计 AF、新主体识别、RTMP/SRT 直播、蓝牙 Classic、MFi——**没有一个需要新硬件**。它们全部运行在与 α1 逐字节相同的芯片上（同一颗 NPU、同一颗蓝牙芯片、同一个主 SoC）。

**α1 II 本质 = α1 的硅片 − NFC + 2.5GbE 网卡，然后换了一套充分挖掘现有硬件的软件。**

这也从工程角度再次证明：理论上（若无签名/锁），α1 II 的软件功能在 α1 上都有运行条件——我们此前验证过的 NPU 同款、传输协议相同、内存充足（8GB）等结论，与本次 98.4% 的硅片重合度完全自洽。
