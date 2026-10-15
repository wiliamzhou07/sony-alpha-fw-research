# Sony α1 (ILCE-1) / α1 II (ILCE-1M2) 固件完整逆向报告

> 生成：2026-10-10。数据源：两台相机 Ver.4.00 官方升级包的完整解密树（/tmp/a1_v400、/tmp/a1m2_v400）。
> 本报告是项目全部逆向工作的汇总主文档；细节论证见同目录各专题文档（AI_AF_PORTING_FEASIBILITY、HARDWARE_ARCHITECTURE、MINI_LDR_ADAM_RESEARCH 等）。
> ⚠️ 解密树在 /tmp（重启即失），可随时用 gen5_pack.py 从工作目录的 BODYDATA.DAT 重解；本目录（firmware_reverse/）的语料和表格是持久化产物。

---

## 1. 结论摘要（TL;DR）

1. **平台**：α1 = CXD90057（主 SoC，4×Cortex-A35, 8GB, Linux 4.9.337-scel）+ CXD90058（协处理器，AArch32 TOMCO RTOS，AF/识别引擎）；α1 II 同平台**再加一颗 AI 处理器 ADAM（外部情报型号 CXD90065）**。
2. **AI 对焦归属**：α1 II 的姿态估计 AI 完整栈（T-Kernel + Vivante VIP8000 驱动 vipcore/vipuser/viplite + 40MB 模型 default.nab）只存在于 ADAM；α1 II 的 CP 固件仅把 .nab 当载荷推给 ADAM（AdamDriver），连 AED 都路由给 ADAM。
3. **α1 的 57/58 无法承接该栈**（硬件+格式双重缺席）：CP 的识别引擎是索尼自研 DDL_MINNA/SaIpDriver（私有字典格式，字典最大 568KB vs 姿态模型 40MB），全固件 0 处 Vivante 痕迹。移植路线判定硬件不可行，与签名墙无关。
4. **两台 silicon 重合度 ~98%**（123 个硬件接口中 121 个相同）；全量清单：α1 1226 文件 / α1 II 1294 文件，其中 SAME=776、DIFF=414、仅 α1=37、仅 α1 II=105。
5. **刷改固件不可行**：FDAT 尾部 RSA-2048 签名由 boot ROM 强制验签（实测错误码 0x56），gen5 AES 密钥虽已破解，签名墙独立存在。
6. 官方服务手册 BOM：两台均为单主板（SY-1109 → SY-1137），α1 II 无独立 AI 板——ADAM 是主板上的芯片。

## 2. 方法与工具链

| 环节 | 工具/产物 |
|---|---|
| 解密 | GitHub q19032/Sony-firmware-unpacker 的 gen5 AES 密钥 + `gen5_pack.py`（工作目录；结构：UFU 容器 → FDAT: 512B 头(key_aes ECB) + 1024B 分块 CBC + IV@尾部-0x110 + 尾 256B RSA 签名） |
| 解包 | `fwtool-gen5/`（修改版 fwtool）→ firmware.tar → 0700_part_image → 各分区 |
| 语料生成 | `firmware_reverse/gen_corpus.py`（本目录）：全量 md5 清单、版本指纹、vermagic、ELF 审计、交叉差异、关键二进制 strings（gzip） |
| 二进制分析 | capstone 5（ARM32/ARM64 反汇编）、strings、LLVM 工具；无 Ghidra/r2（磁盘 99% 满未装） |
| 官方资料 | Encompass Right-to-Repair 服务手册（ILCE-1 194页 / ILCE-1M2 237页，OCR 于 /tmp/sm_pages） |

## 3. 固件容器结构

```
BODYDATA.DAT (UFU: DATV/PROV/UDID/FDAT/DEND)
└─ firmware.fdat → firmware.tar
   ├─ 0100_config/        mount.conf, big_backup.conf
   ├─ 0110_backup/        区域码备份数据（α1: CX885xx [TK/TK_HIBIKI2], α1 II: CX899xx [HC]）
   ├─ 0300_partconf/      partinf.conf（分区几何：起始/大小/类型）
   ├─ 0640_darwin/        darwin_core.bin（Darwin ISP 固件）
   ├─ 0650_prfile/PMBP/   开源许可证（α1 II 新增 Vivante MIT 等 8 份）
   ├─ 0700_part_image/dev/
   │   ├─ nflasha3 (75MB, SYSTEM Main)  = vmlinux.bin + initrd.img + av-cam.bin + adam_app.bin(仅II) + bonobo/wole/btfw + sabin
   │   ├─ nflasha5 (300/350MB, Warm Boot Image, RAM 快照)
   │   ├─ nflasha7 (16MB, rootfs)       = busybox + init/init2/initrc + kmod + version.txt
   │   ├─ nflasha8 (64MB, CP Data, FAT12) = loader_spi.bin + mini_ldr.bin(仅II) + cpapp-b.bin + cpImg.dat + pcie_phy_fw.bin + MIS/DGU/DmmCfg/SysSound/OldAmtCL + tomco.txt
   │   └─ nflasha15 (500/808MB, /usr)   = bin/(appFw 相关) + lib/(全部 .so) + kmod/(131/130 个驱动) + sabin/ + data/ai_dict(仅II) + codec/ + scenario/ + share/
   ├─ 0750_nor_loader/    loader_nor.bin + LdrBkupList.txt（NOR 恢复通道）
   ├─ 0800_appli/         lens/ setting/ tmp/（镜头补偿、设置模板）
   └─ 1050_i2c/           Cypress USB-C MCU 固件 (cyacd)
重要事实：升级包只携带 nflasha3/5/7/8/15 五个分区；nflasha1(updater)/2(setting)/其余为出厂写入，不随升级变化。
```

## 4. 启动链（含本次新发现）

```
① Boot ROM (CXD90057, InfSec 验签, 不可变)
② loader_nor.bin（独立 NOR 芯片，Force Update 恢复模式）— "SPI Loader Ver.00.16 (2020-05-21)" 同款代码库
③ vmlinux.bin + initrd (Linux 4.9.337-scel) → insmod pci_ep_cp.ko 等
④ 主 SoC 经 SPI 把 loader_spi.bin 推给 CXD90058 → CP 初始化
⑤ [仅 α1 II] mini_ldr.bin = "MINI Loader Ver.00.02 (2022-02-10)"：EL3 级裸机，PCIe EP 初始化
   （BAR/LTSSM/PERST/PHY 固件上传 + ADC；字面量池自引用显示其运行于 **0xfe0a4000 附近的 CP ESRAM**，与主 SoC esram@0xfe000000 的地址风格一致；全固件无按名引用，属特殊模式加载器）
⑥ cpapp-b.bin（AArch32 TOMCO 应用，加载地址 0x00108000）= AF/识别主引擎
⑦ [仅 α1 II] cpapp 经 GPIO 上电 ADAM → 主 SoC 侧文件服务供给 /system/adam_app.bin →
   ADAM 跑 SMP T-Kernel 1.00.01 + Vivante VIP8000 栈（vipcore/vipuser/viplite）→ 执行 default.nab 姿态网络
```

## 5. 处理器与 AI 栈对照

| | α1 | α1 II |
|---|---|---|
| 主 SoC | CXD90057, 4×A35, 8GB | 同左（dtb 逐字节一致） |
| CP 引擎 | CXD90058: cpapp (16.7MB, AArch32) | 同芯片: cpapp (19.2MB) |
| CP 识别框架 | DDL_MINNA（索尼 SaIpDriver：FdnDrv/PdnDrv/DrtDrv/RotateDrv） | 同左 + ddl_minna_scd/keypoint/rotate 扩展 |
| CP 字典 | aed/bed/aed2/fdn/pdn（sabin 私有格式，74KB–568KB） | 同左（逐字节相同） |
| AI 处理器 | **无** | ADAM (CXD90065?): adam_app.bin 539KB, SMP T-Kernel + Vivante VIP 栈 |
| 姿态模型 | 无 | default.nab 40MB（Vivante ACuity 图，`com.vivantecorp.extension.evis.*` 算子）+ 10×.rsc + scd_dic1/2/3 |
| cpapp→ADAM 引用 | **0 处** | 1268 处（AdamCmd/AdamTransParam/adam_fr_manager；.nab 仅作为 AdamDriver 载荷出现 2 处） |
| mini_ldr.bin | 无 | 有（PCIe EP mini loader） |
| tomco.txt 内存区 | 第三个 uc 区 0x4A800000@0x35800000 | 扩为 0x4D000000@0x33000000 + 新增 192MB "du"@0xD4000000 |

**判定**：α1 的 57（无 NPU/GPU）+ 58（MINNA 私有引擎，私有格式，小网规模）上不存在能执行 Vivante 编译模型的硬件；"改协议移植"不可行（详见 MINI_LDR_ADAM_RESEARCH.md §6）。

### 5.1 内存架构（"双 Bionz XR = 双 8GB" 的对账）

营销口径的"双 Bionz XR 处理器 / 整机 16GB"与固件证据的对账：

| 内存 | 容量 | 证据强度 |
|---|---|---|
| 主 SoC（CXD90057）DRAM | **8GB @ 物理地址 0x400000000** | 铁证：设备树唯一内存节点 `memory@400000000`，两台逐字节一致 |
| CP 侧（CXD90058 + α1 II 的 ADAM）DRAM | 独立地址空间（低位 0x03200000–0xD4000000），**tomco 配置窗口合计 α1=2.53GB / α1 II=2.75GB（含 ADAM 的 192MB "du" 区），物理容量 ≥ 此数、上限固件不可见** | memcfg 只是使用声明，非物理容量 |
| 物理总 DRAM | 拆机情报"整机 16GB"= 2×8GB：一块挂主 SoC（已被 dtb 证实），另一块服务 CP 侧 | 与 CP 独立地址空间完全不重叠于主 SoC 8GB 的事实自洽；第二块的确切容量需拆机读 DRAM 颗粒丝印 |

要点：两颗处理 Die 各挂独立 DRAM（非共享）；"双 Bionz XR"即 57+58 两颗处理 Die；"双 8GB"中主 SoC 那 8GB 是固件铁证，CP 侧的 8GB 是拆机情报且与固件无矛盾（tomco 只声明用 2.5~2.75GB，物理可以更大）。

## 6. 全量清单与差异统计（firmware_reverse/ 语料）

| 指标 | α1 | α1 II |
|---|---|---|
| 清单文件数（含分区镜像） | 1,226 | 1,294 |
| ELF 文件 | 629（全部 AArch64） | 659（全部 AArch64） |
| 内核驱动 .ko | 131 | 130 |
| rootfs 构建 | 39185_14.2025110501 | 34023_06.2025100701（不同代码库） |
| 交叉 diff | SAME=776, DIFF=414 | ONLY_A1=37, ONLY_A1M2=105 |

**仅 α1 II 有（105）**：ai_dict/default.nab + 10×AAAAAA*.rsc、r8125.ko(2.5GbE)、gstplugin 全家（libPluginRtmpLiveStream/libPluginSrtLiveStream/libgstaxcmux/libgstcoreelements）、ud_leaf_firmup/us_leaf_*（叶子设备升级通道）、CX899xx 区域备份、Vivante/MIT 等 8 份新许可证、adam_app.bin、mini_ldr.bin 等。
**仅 α1 有（37）**：CX885xx 区域备份、nfc.ko + libInfraNfc.so、r8168.ko(1GbE)、libInfraError.so、IPSX.uxc 影像包 6 份、logo.bin 等。

## 7. 官方服务手册 BOM 结论（Encompass RTR 手册，扫描版已 OCR）

- 主板：α1 = **SY-1109**、α1 II = **SY-1137**（均 Not Supplied 不单卖）；周围排线全换代（HD-1008→HD-1017、SW-1033→SW-1045 等），FP-2438 共用。
- α1 II 新增 **PD-1076 BOARD**（功能未知，靠近面板/转轴，疑与翻转屏相关）。
- 两台手册均无独立 AI 板、无任何 "AI/ADAM" 命名部件 → ADAM 若在，即主板上的芯片（与固件结论互洽）。

## 8. 死路清单（实测，勿重复尝试）

1. **刷改固件**：RSA-2048 签名（FDAT 尾 256B），boot ROM InfSec 强制验签，改动即拒（0x56=慢闪5快闪6）。gen5 AES 解密重打包管线正确但过不了签名。
2. **senser 服务模式**：国行 CN2 锁死（libsencore.so terminal_change_function_is_disabled），V1.35 即有，降级无用。
3. **MSC-ext (SCSI 0x7A)**：只读。
4. **MSC 模式 updater 命令**：不响应（需更新模式）。
5. **AI 对焦移植到 α1**：硬件不可行（§5），与签名独立。
6. α7C II 的 senser root 方法、Wonder-Lantern 尼康方法：不可照搬（见 PROJECT_STATE.md）。

## 9. 遗留问题

1. mini_ldr.bin 的加载者与触发场景（按偏移？更新模式？暖启动？）。
2. ADAM 物理形态：主板芯片（手册 BOM 倾向）还是同封装第二 die。
3. PD-1076 板的职能。
4. α1 的 IPSX.uxc 影像包为何在 α1 II 消失（被 ai_dict 体系取代？）。
5. CXD90065 型号仅为外部情报，固件字符串无印证。
6. ADAM 芯片在 α1 板上的物理存在性（固件/手册均已无法回答；且对移植结论已无影响）。

## 10. 补充逆向（第二轮，2026-10-10）

| 项目 | 结论 |
|---|---|
| **内核符号表** | vmlinux.bin 为标准 arm64 Image；kallsyms 完整提取（`kernel_symbols/`）：α1=40,944、α1 II=40,941 个符号，**逐符号 diff 仅个位数编译产物差异 → 两台内核完全同构**（同 4.9.337-scel 同配置） |
| **av-cam.bin** | "ORIL" 容器，**预链接在 0xffffffc001000000 的 AArch64 内核态镜像**（arm64 模块地址空间）→ AV/成像管线主体跑在主 SoC 的内核空间，13.3/13.5MB，两台同格式 |
| **nflasha5** | "WBI2" 容器（暖启动内存快照），头部含段表；非文件系统 |
| **ELF 符号** | 629/659 个 ELF 中 196 个未 strip（主要是 initrd 的 busybox 工具链）；大件（.so/appFw）均 stripped，依赖 strings 语料 |
| **mini_ldr 修正** | 此前"MMIO 0x32000000"为浮点噪声误判；字面量池自引用证实运行于 **0xfe0a4000 附近 ESRAM**，CNTFRQ≈2MHz 与主 SoC 定时器一致 |
| **Ghidra 反编译** | Ghidra 12.1.4 + JDK21 headless 管线建立（`ghidra_scripts/`）。**全部完成**：两台 cpapp + adam_app + mini_ldr + wole + av-cam 共 **107,449 个函数**反编译为可读 C（`decompiled/`，合计 ~113MB） |

### 两台 cpapp 全文反编译终对比（函数级）

| 指标 | α1 cpapp | α1 II cpapp |
|---|---|---|
| 反编译函数总数 | 44,372（44MB C） | 48,506（47MB C）——**净增 4,134 个函数** |
| Adam / AdamDriver 引用 | **0** | 465 |
| OSPI（CP↔ADAM 链路） | **0** | 72 |
| AUTORECOG 命名空间（Adam 命令层） | **0** | 88 |
| scd（新主体分类） | **0** | 11 |
| MINNA / SaIp（私有识别引擎，两台皆有） | 22 / 700 | 42 / 1,053（scd/keypoint/rotate 扩展） |

→ 函数级证实：α1 II 对 α1 的 CP 增量 = "Adam 客户端全家桶 + MINNA 扩展"，其中 Adam 相关部分完全依赖 α1 不存在的 ADAM 处理器；MINNA 扩展部分虽在 α1 的引擎家族内，但其输入（scd 字典+姿态模型）绑定 ADAM 侧执行。结论与 §5 一致且现在有了函数级证据。

### 10.1 ADAM 管线数据量与"CP 模拟"可行性（量化分析，2026-10-10）

**经过 ADAM 管线的数据（静态可证部分）：**

| 数据 | 大小 | 通道 |
|---|---|---|
| default.nab 姿态模型 | 40.0MB | OSPI 批量写命令（`OSPI_CMD_Write_cetus_`）→ CP 侧 192MB "du" 区 |
| .rsc 资源清单 ×10 | 共 3.9KB | 同上 |
| adam_app.bin 固件 | 539KB | ADAM 启动装载 |
| 运行时输入 | 每帧人体 ROI 裁剪图 + 参数（imgID/async_cnt 异步流水）+ AED 初始区域等小结构 | OSPI 寄存器读写协议 |
| 运行时输出 | 姿态关键点/置信度（字节级小结构） | 同上 |

OSPI 协议命令集（反编译实证）：`Adam_ReadRegister` / `Adam_WriteRegister` / `Adam_SoftReset` / `CSPI_SetConfig` / `OSPI_CMD_Write_cetus_`。像素级运行流量取决于 ROI 尺寸（静态不可知），量级为每帧几百 KB～几 MB——**数据量本身不是瓶颈**。对比参照：MINNA 全部 sabin 字典（aed/bed/fdn/pdn/scd）合计 6.9MB，姿态模型为其一文件的 5.8 倍。

**"在 CP 上模拟 ADAM"的算力对账（结论：不可行）：**

1. 单次推理需求：40MB int8 权重 → ≥40M MAC；卷积网实际计算量通常为参数量的 10–50 倍 → **单次推理约 0.4–2 GMAC**。VIP8000 级 NPU 耗时数毫秒。
2. CP 算力上限：4× ARMv8 AArch32（A35 级**无 int8 点积指令** SDOT/UDOT），NEON 宽化乘加每核每周期 4–8 MAC → 约 1.1GHz × 4 核 × 6 MAC × 35% 现实效率 ≈ **9–11 GMAC/s 持续，且需 100% 吃光全部四核**。
3. 对账：对焦节奏 30–60Hz × 1–4 目标 → 需求 **15–100 GMAC/s**（CP 全部算力的 2–10 倍）；CP 满负荷单次推理 40–200ms，对焦控制环要求 **8–33ms** 内出结果（超预算 3–25 倍）；机会成本上 AF 引擎/传感器时序/镜头伺服/MINNA 同在这四个核上。
4. SA-IP 加速器无法分担：寄存器包（0xfeda720–0xfedae34）与字典格式为 ≤568KB 检测小网的固定功能引擎，不能执行 ACuity 图。
5. 结论：**瓶颈不是数据量，而是确定性低延迟的 NPU 级乘加算力；CP 的"冗余"是通用核空闲时间，与 ADAM 管线的算力需求不同量纲。** 若模型压至 ≤5MB、单次 ≤50M MAC、更新率 ≤10Hz 则理论上可跑——但那等效于 α1 现有 MINNA 功能的水平，即"α1 II 姿态对焦"这一增量本身无法通过 CP 模拟获得。
| **cpapp 全文反编译（α1 II）** | **48,506 个函数全部反编译为 C**（a1m2_cpapp.c，48.6MB）。关键发现见下两行 |
| **CP↔ADAM 物理链路** | **OSPI（Octal SPI）总线**（AdamDriver 中 72 处 OSPI 引用 + "OSPI transfer error"），事件标志/邮箱同步——不是 PCIe |
| **AdamCmd 协议** | 命令表结构：每条目 0xBC 字节，`AUTORECOG_GetAdamCmdID` 分发（seq/命令 ID/错误码 0xc、0x2c），带边界检查与日志开关；模型经 interchip buf 以 OSPI 传输 |
| **SA-IP/MINNA 寄存器映射定位** | 加速器寄存器组 **0xfeda720–0xfedae34**（访问最密集）+ **0xfec8880**（疑 DMA/中断）；0xfe0a23x 为引导 RAM 区 IPC 邮箱（与 mini_ldr 运行区 0xfe0a4000 同页）——回答了步骤①遗留的 MMIO 问题 |

## 11. 语料文件索引（本目录）

| 文件 | 内容 |
|---|---|
| `a1_inventory.tsv` / `a1m2_inventory.tsv` | 全量清单：相对路径、大小、md5、magic（ELF 标记） |
| `cross_diff.tsv` | 两台逐文件差异总表（SAME/DIFF/ONLY_A1/ONLY_A1M2） |
| `a1_versions.tsv` / `a1m2_versions.tsv` | 各文件内的版本号/构建日期指纹 |
| `a1_kmod_vermagic.tsv` / `a1m2_kmod_vermagic.tsv` | 每个内核驱动的 vermagic |
| `a1_elf_audit.tsv` / `a1m2_elf_audit.tsv` | ELF 审计：架构、入口、符号表数量、是否 stripped |
| `strings_corpus/*.strings.txt.gz` | 关键二进制全文 strings（cpapp、adam_app、mini_ldr、loader_spi/nor、av-cam、bonobo、wole、darwin_core、vmlinux、pcie_phy_fw） |
| `a1_meta/` `a1m2_meta/` | 原样保存的元数据（config.yaml、partinf.conf、mount.conf、tomco.txt、big_backup.conf） |
| `gen_corpus.py` | 语料生成脚本（可重跑，改 CAMS 路径即可） |
| `kernel_symbols/` | 两台内核的 kallsyms 符号表 + 重建的 vmlinux ELF（vmlinux-to-elf） |
| `decompiled/` | Ghidra 反编译产物（.c 文件，函数级）：adam_app、mini_ldr 已完成；cpapp/wole/av-cam 由 `ghidra_scripts/queue_all.sh` 后台生成 |
| `ghidra_scripts/` | DumpDecomp.java（反编译导出脚本）+ run_headless.sh + queue_all.sh（需 Ghidra 12 + JDK21，`JAVA_HOME` 指向 openjdk@21） |

## 12. 复现指南

```bash
# 1) 从 BODYDATA.DAT 重新解密解包（工作目录的 gen5_pack.py / fwtool-gen5）
# 2) 重新生成语料（需 /tmp 下有解密树；pyelftools、capstone）
python3 "<workspace>/firmware_reverse/gen_corpus.py"
# 3) 服务手册直链（Encompass Right-to-Repair）
#    α1:   https://research.encompass.com/SON/rr/ILCE1.pdf   (79MB)
#    α1II: https://research.encompass.com/SON/rr/ILCE1M2.pdf (123MB)
```

⚠️ 磁盘余量仅 ~4GB（99% 满）：/tmp 的两棵解密树合计 6.6GB，如需长期保留请先清理空间再迁移；否则依赖本目录语料 + 重解管线即可恢复一切。

## 13. 第三台参照机：α9 II（ILCE-9M2）Ver.3.20（2026-10-10）

> 用户命题：α9 II 是"纯算法时代"的对焦王者（无 NPU），其 AF 算法或可提升 α1。下载→解密→解包→评估全流程如下。

### 13.1 获取与解密（全程无障碍）
- 来源：Sony Asia 官方 Mac 升级器 `Update_ILCE9M2V320.dmg`（344MB，直链 `support.d-imaging.sony.co.jp/download/NEX/Diviuozmgp/`，与国行 BODYDATA 同一 NEX 令牌路径体系）
- 固件本体：`FirmwareData_ILCE9M2V320.dat`（344MB，**UDTRFIRM 老世代容器**，fw 3.20，model 0x91030014，CRC 校验通过）
- 解密：**gen4 已知公开密钥 key_cxd90045 直解**（CBC, IV@尾部）——α9 II 是三台机器中唯一端到端全透明的；fwtool 的 dat/fdat 链一层层剥开（注意：firmware.bin 需整体交给 fwtool 解，先手工剥壳会得到 568B 私有头 + 非标 tar 而走弯路）
- 产物：/tmp/a9m2_fw/（1.2GB 完整解密树，结构与 α1 同源：0700_part_image/nflasha3+7+15、0640_darwin、0800_appli + α9 II 特有 1030_genlock/0601_gps/9000_loader）

### 13.2 架构对照

| | α9 II (CXD90045, gen4) | α1 (CXD90057+58, gen5) |
|---|---|---|
| 平台 | 单主 SoC，ARMv7 32 位 | 双芯：主 SoC（4×A35, AArch64 Linux）+ CP（TOMCO, AArch32） |
| AF 管线载体 | av-cam.bin 17.3MB（ORIL 容器，ARM32 内核态 @0x635c6000） | cpapp 16.7MB（TOMCO）+ av-cam 13.3MB（ORIL AArch64 内核态） |
| 识别字典（sabin） | 4 个共 **356KB**（idt_cam 176KB、sa_dfdet 156KB、ssboot×2） | 8+ 个共 **6.9MB**（aed/bed/aed2/fdn/pdn/dcv，单最大 568KB） |
| AF 功能接口 | EYE_AF/FACE_AF_MODE/FOCUS_AF_AREA/MOVIE_AF_DRIVE_SPEED 等 | 同族功能 + 昆虫/车/飞机主体识别（V4.00 已下放） |

### 13.3 评估结论：对 α1 无"关键性提升"空间

1. **功能是子集**：α9 II 的实时跟踪/眼部 AF 功能集 α1 全部具备且更强——α1 的识别字典体积是 α9 II 的 19 倍，且 V4.00 已下放 α9 II 没有的新主体类型。不存在"α9 II 有而 α1 没有"的对焦功能。
2. **架构不可移植**：α9 II 的 AF 代码在 CXD90045 内核态 ORIL 镜像（ARMv7 + gen4 专有框架）里，α1 的对焦在 CXD90058 TOMCO（DLL_MINNA/SaIp）——两者没有共同运行时，"移植"等于按可读源码在 α1 上重写，且签名墙依旧。
3. **真正的价值**：α9 II 是 gen4 密钥直解的**全透明参照机**，其 av-cam 反编译产物（后台生成中）可作为索尼 AF 工程的算法研究教材（跟踪状态机、AF 驱动速度策略等启发式），属于"读懂设计思想"层面的参考——这正是用户命题中"纯算法时代对焦"唯一可提取的东西。
4. 对焦代际链完整图景：**α9 II（纯算法）→ α1（算法+更大字典）→ α9 III/α1 II（算法+AI 处理单元）**——每一代的增量都绑定新一代硬件；α1 已是"无 AI 硬件条件下"的上限。

### 13.1 附：四件套互换性终判（"α1 换 α1 II 管线"命题，2026-10-10）

| 组件 | 互换性证据 | 换取收益 |
|---|---|---|
| av-cam（主 SoC 内核态成像） | **ORIL 头逐字节相同**（同基址 0xffffffc001000000）；函数 12,631 vs 13,003；α1 II 独有功能字符串≈0（仅 TransMainJpeg/wait_lock_comp）；两台均零 Adam/AI 引用 | **≈0**——主 SoC 成像管线两代几乎没变，α1 II 的提升不在这里 |
| cpapp（CP 对焦引擎） | 字符串 a1=78,678 / α1 II=92,479（α1 II 独有 31,757） | **真实增量所在**：`function_human_detection.cpp`、`function_zpd_whole_detection.cpp`（全画面检测）、`SET_DEFOCUS_CONTROL_POSITION`/`SET_REMOTE_FOCUS_COMMAND`（散焦/远程对焦控制）、`f_det_gen`/`dic_type` 动态字典切换跟踪状态机；其中 MINNA/scd 系跑在 CP 自己的 SA-IP 上，**a1 的同颗 CXD90058 硬件上具备运行条件** |
| 结论 | "四件套搞成一样" = 混合固件 = `v401_01_hybrid_ai_phase1` 已实现的方案；**打包可行（gen5 管线完备），入机必被拒（boot ROM RSA 验签实测 0x56，纯重打包 v401_00 同拒）**。av-cam 无可换之利，cpapp 有可换之利但与全包同签——一切变体收敛于签名墙。 |

## 14. 社区"改公钥+改验签代码"思路的验证（2026-10-10 深夜）

> 外部情报（改机群）：①索尼固件密钥=A+B+C 演变（C 可改文件实现换代）；②除 nflasha15 外各分区可 USB 写；③把 nflasha1(updater) 里的公钥改掉、改掉 verifykey 代码、烧回 NOR，即可 SD 卡自签包。

### 14.1 在 a1 固件上的逐条核查

| 主张 | a1 上的核查结果 |
|---|---|
| 密钥 A+B+C 演变 | 与 fwtool 源码级事实**部分吻合**：每个世代密钥=SHA256 派生+硬编码常量（"A B"固定），gen4 对所有 CXD90045 机型通用印证"按架构不变"；但 gen5 密钥派生盐不在任何固件文件中（KEY_HUNT_LOG 已穷举 436 身份字段派生=0 命中），"C 在可改文件里"在 gen5 无证据 |
| 1 分区可 USB 写 | **对 a1 不适用**：a1 的 nflasha1 在升级包里不存在（只带 3/5/7/8/15 五个分区），且 updater 是 boot 链条的第二级 |
| 改 updater 公钥+verifykey | **a1 上验签者不存在于任何可写分区**：①updater.img 全部脚本/ELF 只有 CRC32（us_crc32sum），无 RSA；②initrd/vmlinux/av-cam 全文 0 处 InfSec；③唯一含 InfSec 的是 92KB 的 loader_nor.bin（NOR 独立芯片），但其 `INS_E:Sign INFS_SAFE` 只是**读 0xfe040000 硬件安全块的状态寄存器**（FUN_0000dbcc→memcmp 状态字），验签执行体不在 loader 内、更不在任何可写分区——0xfe040000 区域在 NOR loader 里无任何写入代码，属 CXD90057 硬件安全内核（InfSec）的映射窗口 |

### 14.2 结论：该思路的适用边界

该思路在 **gen4 及更早世代**（CXD90045：α9 II 等）大概率成立——gen4 的验签层在系统内、密钥体系可演变，群主的实战（四代机、1 分区）与我们的 fwtool 源码认知一致。但 **a1（gen5）做了架构级封堵**：验签上移进 SoC 硬件安全内核（0xfe040000 InfSec 块），updater/NOR/initrd 全部可写层均无验签代码可改；实测三次（v401_00/01/02）0x56 拒收且错误码语义正是 `INS_E:Sign INFS_SAFE`。
**"烧回 NOR 改公钥"在 a1 上的真实等价物是"改写 CXD90057 的硬件安全内核"，不可行。** 唯一从本思路受益的场景：若未来获取 gen4 世代机器（如 α9 II）做实验，其验签链完全透明可改。
