# Sony α1 固件逐块功能地图

> 来源：α1 V4.00 固件完整解密树。逐块标注每个区域/分区/模块的**功能**。
> 本文档回答"固件里每一块是干什么的、和硬件什么关系"。

---

## 第一部分：固件包的物理结构（从外到内）

```
BODYDATA.DAT (798MB)
└─ UFU 容器
   ├─ DATV   : 容器版本 (4B, =1)
   ├─ PROV   : 配置/计数 (4B, =1)
   ├─ UDID   : USB 描述符表（告诉电脑这是哪台相机、支持哪些 USB 模式）
   ├─ FDAT   : 加密的固件本体（最大的一块）
   │   ├─ [512B 明文头]  ← key_aes(AES-128-ECB) 解密，含机型/版本/偏移
   │   ├─ [加密主体]     ← gen5 密钥(AES-256-CBC) 解密
   │   │   ├─ updater.img  : 更新系统（squashfs）
   │   │   └─ firmware.tar : 真正的固件（各分区镜像）
   │   └─ [IV 16B + 256B RSA 尾签]
   └─ DEND   : 全文件 CRC32 (4B)
```

**加密分层**：头用公开密钥 `key_aes`（谁都能解，读元数据）；主体用 gen5 密钥（相机侧派生）；256B 尾签是 RSA-2048 签名（验真伪，写不进去的墙）。

---

## 第二部分：firmware.tar 的功能分区（region）

| region | 内容 | 功能 |
|---|---|---|
| `0100_config` | mount.conf, big_backup.conf | 分区挂载表（哪个分区挂到哪） |
| `0110_backup` | CX88500/CX88501_*.bin (12地区) + TK_HIBIKI2 变体 | **每地区的设置/校准数据**（国行 CN2 就在这） |
| `0300_partconf` | partinf.conf | **分区表**（nflasha1-30 的地址/大小/类型） |
| `0640_darwin` | darwin_core.bin (235KB) | **Darwin = ISP 图像信号处理器固件** |
| `0650_prfile` | PMBP/LICENSE/* | 开源组件许可证（jemalloc/libevent/curl/webrtc/wpa 等——暴露用了哪些开源库） |
| `0700_part_image` | nflasha 分区镜像 | **固件主体**（见第三部分） |
| `0750_nor_loader` | loader_nor.bin | **NOR 启动器**（独立 NOR 芯片，含 Force Update 救砖） |
| `0800_appli` | setting/(dtb, kemco.txt), lens/, tmp/(系统配置) | 应用层配置 + 镜头数据 + Linux 系统配置 |
| `1050_i2c` | fw2_normal_app/cfg.cyacd | **Cypress 子芯片固件**（USB-C PD/外设 MCU） |

空 region（0600_gps / 0630_ca / 1030_genlock）：α1 无 GPS、无 CA(蜂窝)、无 genlock，这些槽位为空。

---

## 第三部分：nflasha 分区 ↔ 功能（内部 NVMe NAND）

| 分区 | 挂载点 | 功能 |
|---|---|---|
| nflasha1 | — | **Updater 更新系统**（updater.img，刷机时用它） |
| nflasha2 | /setting | **设置 + Backup.bin**（你的设置、校准、区域码） |
| nflasha3 | /system | **主系统**：vmlinux.bin(内核) + initrd + kmod(驱动) + av-cam/bonobo/wole 子系统固件 |
| nflasha5 | /wbi | **热启动镜像**（休眠/唤醒的内存快照，含运行时密钥派生代码） |
| nflasha7 | /rootfs | 根文件系统 |
| nflasha8 | /cp | **CP Data：协处理器（CXD90058）固件** cpapp-b.bin + loader_spi + tomco.txt |
| nflasha15 | /usr | **主应用区**：appFw.so(84MB 主程序) + 全部 lib + AI 模型/字典 + scenario |
| nflasha11 | /log | 日志 |
| nflasha12 | /cert | 证书 |
| nflasha18 | /lens | 镜头数据 |
| nflasha23 | Customer | 用户区 |

---

## 第四部分：硬件块 ↔ 固件/驱动

| 硬件 | 功能 | 固件/驱动 |
|---|---|---|
| **CXD90057** 主 SoC | 4×Cortex-A35 跑 Linux，8GB DRAM | nflasha3(内核) + nflasha15(应用) |
| **CXD90058** 协处理器(CP) | AF/成像引擎，**含 NPU** | nflasha8(cpapp-b.bin) |
| **IMX610** 传感器 | 50MP 堆栈式 CMOS | 内核驱动 + CP 读取 |
| **Darwin** ISP | 图像信号处理 | 0640_darwin/darwin_core.bin |
| **imola2** 编解码器 | 视频编解码(8K) | nflasha15/codec/vcd_firmware_imola2.bin |
| **Realtek RTL8168** | 1GbE 以太网 | kmod/r8168.ko |
| **Qualcomm Rome** | 蓝牙 | nflasha3/btfw32.tlv |
| **NFC** | 近场 | kmod/nfc.ko |
| **Cypress** | USB-C PD/外设 | 1050_i2c/*.cyacd |
| **NVMe NAND** | 内部存储 | kmod/nvme.ko |

**主↔协处理器**：PCIe（pci_ep_cp.ko），CP 从 /usr/sabin 读 AF 字典在 NPU 上跑主体识别。

---

## 第五部分：启动链

```
Boot ROM(不可变, InfSec 验签在这)
  → loader_nor.bin (NOR芯片, 验签, Force Update 恢复模式在这)
  → vmlinux.bin + initrd (nflasha3)
  → /sbin/init → insmod_drv → setup_nflash → init2
  → 主系统 (nflasha15 appFw.so) + 协处理器 (nflasha8 cpapp-b.bin)
```

**启动模式**（init2 读 /setting/mode/dmode）：正常拍摄 / 更新(updater) / senser(服务)。

---

## 第六部分：关键软件模块（nflasha15 的 lib/）

| 模块 | 功能 |
|---|---|
| **appFw.so** (84MB) | 相机主程序（一切拍摄逻辑/UI） |
| libInfraSKD.so | 签名验证（AI 模型/许可证） |
| libInfraCryptCore.so | 加密核心 |
| libSysDef.so | 系统定义 |
| libmpr.so | MPR（媒体处理） |
| libObj.so | 对象/主体识别 |
| **libAiDictionary.so** | AI 字典管理（α1 II 才有，α1 缺） |
| libsencore.so + sen.elf | **senser 服务**（服务模式，国行锁） |
| libInfraExtCmdSvc.so | MSC-ext 外部命令服务 |
| libInfraRtmp/SrtLiveStreaming.so | RTMP/SRT 直播（α1 II 新增） |
| scenario/*.so (26个) | 拍摄场景（AVBB_SCN_START/STOP_AUDIO/HDMI/MIC/VIDEO/PANELEVF 等子系统启停） |

---

## 第七部分：安防架构（三层）

| 层 | 机制 | 我们的结果 |
|---|---|---|
| 加密 | gen5 AES-256-CBC（密钥=SHA256(/dev/mem读值+固定盐)） | ✅ 已破（能读） |
| 签名 | RSA-2048（256B尾签，boot ROM/InfSec 验） | ❌ 封死"写" |
| senser 锁 | 区域/机型级（terminal_change_function_is_disabled） | ❌ 封死"运行时" |

---

## 第八部分：还没完全摸透的（诚实清单）

1. **appFw.so 内部**（84MB 主程序的逐函数逻辑）——只挖了字符串层面
2. **cpapp-b.bin 内部**（协处理器 AF 引擎的具体算法）——只知道它跑 NPU 字典
3. **darwin_core.bin（ISP）** 的具体图像管线
4. **每个 scenario 的具体触发逻辑**
5. **NPU 的指令集/模型格式**（.nab/.bin 字典的内部结构）

这些是"功能细节"，不影响"结构/安防"的结论，但如果要继续深入研究（比如移植、逆向某个具体功能），从这里入手。
