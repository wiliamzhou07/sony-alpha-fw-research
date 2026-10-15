# mini_ldr.bin 研究报告 + 重大架构发现：ADAM / VIP8000

> 2026-10-09。基于 /tmp/a1_v400 与 /tmp/a1m2_v400 两棵 V4.00 完整解密树。

## 一、mini_ldr.bin 身份（直接回答）

- **"MINI Loader Ver.00.02 (Feb 10 2022 22:54:31)"**——CXD90058 协处理器侧的裸机 ARM64 二阶段加载器，与 `loader_spi.bin`（"SPI Loader Ver.00.16, May 21 2020"，两台逐字节相同）同一代码库编译（指令序言一致，字面量池不同）。
- 反汇编确认：EL3 级启动代码——设 VBAR_EL1/2/3、SCR_EL3、开 FP/NEON（CPACR）、三组 SCTLR 清零、建 EL3 页表（TTBR0_EL3/MAIR_EL3/TCR_EL3）、清 512KB BSS，然后做 **PCIe Endpoint 初始化**（`PCIe_EP_Config_BAR / LTSSM_Enable_Disable / PERST_Switch / GetPhyStatus / Pre/PostInit`、PHY 固件 DWORD 上传）+ ADC 采样 + 全套 ARMv8 异常处理打印。MMIO 基址 0x32000000 = CXD90058 外设空间（主 SoC 是 0xF1xxxxxx）。
- **仅存在于 α1 II** 的 nflasha8（FAT12 文件系统，8.3 名 MINI_LDR.BIN，目录项证实；α1 无此目录项）。
- **全固件树无任何按名引用**（ASCII/UTF-16/8.3 全查过：cpapp、loader_nor、updater、/usr、initrd 都没有）→ 加载它的是按偏移/流程约定，或用于本包内不可见的特殊模式。候选：CP 固件更新/恢复模式（PCIe 推送通道）、暖启动路径（α1 II 的 nflasha5 WBI 300→350MB）、工厂校准（ADC 字符串）。**未解之谜，但身份已明确：CP 侧 PCIe EP 专用 mini 启动器。**

## 二、连带重大发现（比 mini_ldr 本身重要）

### ADAM 处理器 = α1 II 的 AI 处理单元 = Vivante VIP8000 NPU 的宿主

1. **`adam_app.bin`（539KB，位于 nflasha3 /system，α1 独有→α1 II 独有，α1 无此文件）**：
   - `SMP T-Kernel Version 1.00.01`（RTOS），ARM32（向量表 0xea… 分支），shell 提示符 `ADAM>`，`Adam boot/shutdown/wake up/power down`（独立电源域，CP 经 GPIO 控制其上下电）
   - **完整 Vivante VIP（VIP8000 系）三层软件栈**：
     - `vipcore`（内核驱动，字符串 "fail to ioctl device vipcore"、"lib version mismatch, vipcore.ko"）
     - `vipuser.so`、`viplite.so`（用户态驱动/轻量运行时）
     - 完整 `gcvip_*` API（create_network_from_file/memory、generate_command、commit_network、finish_network、**change_ppu_shape**←PPU 是 Vivante VIP 硬件的后处理单元）+ `gckvip_os_*`（Galcore VIP OS 层）
2. **α1 II 的 cpapp-b.bin 有 1268 处 "adam" 引用**（α1 = 0）：`/system/adam_app.bin`、`adam_na.bin`、`adam_fr_manager.cpp`、`AdamCmd_0/1`、`AdamTransParam/Result`、`>>> [AED] StartAdamSetInitialRegion`——**连传统眼部识别 AED 都路由到 ADAM**。
3. `default.nab` 姿态模型里的 `com.vivantecorp.extension.evis.*` 算子 = 为这颗 VIP NPU 编译的模型。
4. cpapp 两台都无 gcvip/vipcore（0/0）→ VIP 栈只在 ADAM 固件里；CP 通过 Adam* 命令接口调用 ADAM。

### 启动/调用链（α1 II）
```
主SoC CXD90057 (Linux) ─PCIe→ CP CXD90058 (cpapp-b: TOMCO RTOS, AF引擎)
                                 └─GPIO 电源控制→ ADAM 处理器 (α1 II only)
                                     ├─ adam_app.bin = SMP T-Kernel + vipcore/vipuser/viplite (Vivante VIP8000 栈)
                                     └─ 执行 default.nab 姿态网络 + AED 区域管线
mini_ldr.bin = CP 侧 PCIe EP mini 启动器（特殊模式/更新路径）
```

## 三、对移植项目的结论修正（推翻旧论据）

| 旧论据（AI_AF_PORTING_FEASIBILITY.md） | 现状 |
|---|---|
| "α1 cpapp 有 265 处 npu 引用 → 同颗 NPU" | ❌ **作废**。"npu" 是 "Input" 子串误匹配。真 NPU 专名（npu_reid_param）仅 α1 II |
| "α1 也有同颗 NPU 硬件" | ❌ **无固件证据支持**。α1：0 处 adam、0 处 gcvip/vipcore、无 adam_app.bin、全树无 Vivante 痕迹 |
| α1 II 的 AI 差异 = "/usr 多几个文件" | ❌ 差异在**第三颗处理器**：adam_app.bin (nflasha3) + mini_ldr.bin (nflasha8) + cpapp 新增 adam 客户端 1268 处 |

**新的移植前提**：α1 II 的 AI 对焦依赖 ADAM 处理器硬件 + VIP8000。移植是否可行取决于 **α1 板上是否物理存在 ADAM 芯片（哪怕是死硅片）**——固件无法回答，需要：
1. 对比 α1 / α1 II 拆机主板照片（Kolari 拆解有 α1 II 高清图），找多出来的封装；
2. 或在 α1 上实测（PCIe 枚举 / GPIO 路径），但 senser 已锁死，实施受限。

若 α1 板上有 ADAM：需要搬运的物料清单更新为 `adam_app.bin + mini_ldr.bin + α1 II cpapp-b.bin + default.nab + scd_dic + /usr 侧 AI 库`（签名问题依旧是不变的前置死结）。
若没有：AI 对焦移植 = 硬件不可行，项目终点。

## 四、遗留问题
1. 谁在什么时机加载 mini_ldr？（按偏移？哪个特殊模式？）
2. ADAM 与 CXD90058 的物理关系：同封装第二 die 还是板上独立芯片？
3. `adam_na.bin`（/log 路径引用，本包未见）与 `subcpu.bin`、`bonobo.bin`、`wole_app.bin`（两台都有、版本不同）各自角色。
4. nflasha3 里 α1 II 多出的其它差异文件未穷尽（adam_app.bin 是本次确认的一个）。

## 六、三步计划·步骤①结论（2026-10-10）：57/58 无法承载 α1 II 的 AI 栈——硬件与模型格式双重缺席

方法：cpapp-b.bin（ARM32 裸机镜像，加载地址 0x00108000，两台相同）字符串/符号/字典全面分析。

**1. CXD90058 的 AI 引擎 = DDL_MINNA（索尼自研，非 Vivante）**
- cpapp 是 AArch32 TOMCO 应用；其神经网络套件（AED/BED/FDN/PDN/关键点/Staple 跟踪/SCD 分类）全部跑在索尼 `Camera::Minna` 命名空间的 **SaIpDriver** 框架上（`N6Camera5Minna15SaIpDriver_baseI...FdnDrv/PdnDrv/DrtDrv/RotateDrv...`）——"SA-IP" 即索尼私有 AI IP 块。
- 无任何 Vivante 痕迹（gcvip/vipcore/evis 在两台 cpapp 均为 0）。
- **模型格式不兼容**：sabin 字典（aed_dic1 头部为裸权重数据 `3aec d009...`，无 magic）是索尼私有格式；default.nab 是 Vivante ACuity 图（magic `NA\0\0N` + `com.vivantecorp.extension.evis.*` 算子）。两套运行时互不相通。
- **规模差距 ~70 倍**：sabin 最大字典 568KB（aed2_dic2），姿态模型 40MB。MINNA 是为小型检测网设计的。
- α1 II 对 MINNA 的态度佐证：新主体分类 scd 仍下放给 MINNA（ddl_minna_scd.cpp），而姿态模型连碰都不在 CP 上碰——连 α1 II 的 cpapp 引用 default.nab 的仅有的 2 处都在 `AdamDriver`（"Failed to load(adam_..." / "interchip buf"），即 cpapp 只把 .nab 当**推给 ADAM 的载荷**，执行 100% 在 ADAM 侧；AED 区域设定也路由给 ADAM（adam_fr_manager、MEM_UNIT_TYPE_FC_HUMAN_ADAM_WORK）。

**2. 对"改协议移植"的最终判定**
- 协议层（AdamCmd_0/1、AdamTransParam/Result、interchip buf）确实可以模拟——但这不是瓶颈。
- 致命点：α1 的 57（4×A35，无 NPU/GPU）+ 58（MINNA 私有引擎，私有格式，小网规模）上**不存在任何能执行 Vivante 编译模型的硬件**。没有索尼内部的 MINNA 模型编译器（固件中不存在），.nab 无法落在任何一块 α1 硅片上。
- 结论：**"把 α1 II 多出的部分通过改协议写到 57/58"不可行**——无论签名墙是否突破。α1 II 的 AI 对焦增量在物理上绑定 CXD90065/ADAM；α1 的对应硬件路径是"没有"。
- 若 α1 板上真有 CXD90065（存在性仍未验证，也不再有验证的必要）：α1 固件对它 0 引用、无固件、无模型运行时，移植仍需 α1 II 的 adam_app + cpapp + 签名突破，回到原死路。

**3. 原三步计划的处置**
- 步骤① 完成（本节）；步骤②（QEMU 验证 .nab）失去前提——没有可承接的目标硬件，无需再做；步骤③ 依旧被签名墙封死。
- 项目层面：AI 对焦移植路线判定为硬件不可行，本笔记及此前各文档的结论链以此为准。

## 五、后续补充（2026-10-09 晚）
- **官方服务手册已到手**（Encompass Right-to-Repair 直链 `research.encompass.com/SON/rr/<型号>.pdf`）：ILCE-1（194页, Ver.1.0 2024.1）+ ILCE-1M2（237页），存 /tmp/sm_ILCE1.pdf、/tmp/sm_ILCE1M2.pdf，OCR 文本在 /tmp/sm_pages/。扫描版无文字层、图为线稿，芯片级信息为零。
- **BOM 级结论**：两台均为单主板设计（α1: SY-1109 / α1 II: SY-1137，均 Not Supplied 不单卖）；α1 II 无独立 AI 板组件；α1 II 新增 PD-1076 板（功能未知，靠近面板/转轴）。若 ADAM 存在于 α1 II，则是主板上的芯片。
- **CXD90065 型号**（外部情报称 α1 II 的 AI 引擎跑在其上）：与 ADAM 发现吻合，但两台固件字符串中均无 "90065"（命中均为二进制噪声），固件侧无法印证。
- Kolari 三机种拆解照片批量下载已中止（用户叫停）。芯片级判定仍未完成，需实拍主板对比或 FCC internal photos。
