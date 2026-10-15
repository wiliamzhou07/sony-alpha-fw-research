[English](README.md) | **简体中文**

# sony-alpha-fw-research

Sony α1 (ILCE-1) / α1 II (ILCE-1M2) 固件逆向工程与 AI 对焦移植研究 —— 分析文档、工具与数据表。

> **重要声明**：本仓库**不包含、不分发任何 Sony 固件、模型或二进制文件**。
> 全部内容为：(1) 对自行解密的官方固件做分析所得的研究文档；(2) 原创工具脚本；
> (3) 从固件中提取的事实性数据表（注册表 / 函数索引 / 差分结果）。
> 使用本仓库工具需自备合法获得的固件升级包。

## 项目概况

研究目标：理清 α1 II 新增「AI 对焦」（人体姿态估计 + 新主体识别）的完整实现，
评估向同平台前代旗舰 α1 移植的可行性。

两代相机均为 CXD90057（主 SoC，4×Cortex-A35，Linux）+ CXD90058（协处理器，带 NPU）
双芯片平台，α1 II 的差异集中在软件层 —— 这一结论由两代固件完整解密树的逐文件对比得出。

### 主要成果

- **gen5 固件解密链路完全打通**：UFU 容器 → FDAT（AES 头 + CBC 体）解密/重打包逐字节回环一致（`tools/firmware/gen5_pack.py`）
- **两代硬件架构完整解析**：设备树、123 个内核驱动逐个 diff、15 个芯片固件 blob 对比（`docs/hardware/`）
- **AI 对焦全链路逆向**：CP 侧 cpapp 中识别→关键点→AF 决策的主体结构；Adam 调度器、STAPLE/ReID/人脸 ID、人眼选择、优先级判定、跨人遮挡判定、PDAF/散焦链、AE/AWB 归属（`docs/ai-af/` 16 篇）
- **a1 ↔ a1m2 appFw 函数级差分**：多级匹配引擎链（字符串锚 → 调用图传播 → LIS 地标链 → 贪心最优对）达到 **88% 覆盖率 / ~95% 配对精度**；45 条 α1 缺失 PID 的移植风险 A/B/C/D 分级（`data/diff/`、`data/registries/`）
- **A7M4 eMMC 转储解密**：SDM2 分区表 + AES-XTS 分区密钥推导，rootfs/usr 分区已解出并在 QEMU 实测运行（`tools/firmware/decrypt_a7m4_emmc.py`）
- **QEMU 运行索尼固件 Linux**：通用 ARM64 内核 + 官方 rootfs → busybox shell（`tools/qemu/`）
- **串口访问路线**：senser 服务通道桥（PTY+TCP+日志，只读设计）与 bootrom 串口引导桥（`tools/serial-bridge/`）
- **default.nab 姿态模型格式主体破译**：权重块=NPU SRAM 镜像的结论与解析过程（`docs/ai-af/NOTES_NAB_REVERSE.md`）

> 注：深入分析文档（`docs/`）绝大部分以中文撰写；工具注释与数据表为中英混合。

## 仓库结构

```
docs/
  overview/      项目总报告与状态档案（从 FIRMWARE_REVERSE_REPORT.md 开始读）
  hardware/      硬件架构、驱动映射、固件分区地图、两代对比、设备树
  ai-af/         AI 对焦逆向主文档（AF_LOGIC.md）+ 12 篇专题报告 + 枚举笔记
  porting/       移植可行性分析、刷机防砖分析
  keys-access/   密钥体系、密钥挖掘日志、senser 服务模式、访问路线
tools/
  firmware/      固件解包/解密/重打包（自备官方升级包）
  qemu/          QEMU 启动脚本
  analysis/      Ghidra 反编译产物分析：差分引擎链、反汇编扫描器、函数提取、nab 解析
  ghidra/        Ghidra headless 批处理脚本
  serial-bridge/ 相机串口桥工具（GPL-3.0，见该目录 LICENSE）
data/
  registries/    PID/NID 属性注册表（CP 侧 + appFw 侧 + 两代差分分级）
  fun-index/     函数→字符串引用索引（cpapp / appFw / avcam，a1 与 a1m2）
  diff/          a1↔a1m2 appFw 函数差分最终结果（appfw_diff_summary_v9.tsv）
  nab/           default.nab 解析产物（块表 / 权重表结构）
  inventory/     固件树清单、ELF 审计、kmod vermagic、跨代对比
vendor/fwtool-gen5/  fwtool.py 的 gen5 增强分支（MIT，见 vendor 内 LICENSE.txt）
```

## 快速上手（复现解密）

```bash
# 1) 自备官方固件升级包（BODYDATA.DAT，从索尼官网下载页按机型获取）
# 2) 用 fwtool-gen5 解出 FDAT，再用 gen5 密钥解密
python3 vendor/fwtool-gen5/fwtool.py unpack -f 你的升级包.exe -o outDir
python3 tools/firmware/gen5_pack.py --help   # 解密 / 重打包

# 3) 密钥与格式说明见 docs/keys-access/KEY_DERIVATION.md
#    （gen5 AES 密钥由 q19032/Sony-firmware-unpacker 首先公开，本项目仅做工程化封装）
```

## 文档阅读顺序建议

1. `docs/overview/FIRMWARE_REVERSE_REPORT.md` —— 全项目汇总
2. `docs/hardware/HARDWARE_ARCHITECTURE.md` —— 双芯片平台结论
3. `docs/ai-af/AF_LOGIC.md` —— AI 对焦决策层主文档
4. `docs/ai-af/REPORT_a1_a1m2_appfw_diff.md` —— 两代差分方法与结论
5. `docs/porting/AI_AF_PORTING_FEASIBILITY.md` —— 移植可行性（含死路清单）

## 已确认的死路（免得重复踩坑）

- FDAT 尾部 256 字节 RSA-2048 签名由 boot ROM 验证，**刷改固件此路不通**（错误码 0x56）
- 国行 α1 的 senser 服务模式三条读通道被 `libsencore.so` 锁死（V1.35 起即有）
- MSC-ext 仅只读；updater 命令在 MSC 模式不响应
- 相机专用内核在 QEMU virt 机型起不来（内存基址/UART 不符），需用通用内核 + 官方 rootfs

详见 `docs/porting/BRICK_SAFETY.md` 与各文档"死路"章节。

## 许可证

- 主仓库：**MIT**（`LICENSE`）
- `tools/serial-bridge/`：**GPL-3.0**（运行时复用 [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) 的协议实现，见该目录 `LICENSE`）
- `vendor/fwtool-gen5/`：保留上游 [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py) 的 MIT 许可证

## 致谢

- [q19032/Sony-firmware-unpacker](https://github.com/q19032/Sony-firmware-unpacker) —— gen5 AES 密钥
- [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py) —— 固件解包基础
- [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) —— senser/PMCA 协议实现
- [DavidBuchanan314/ILCE-7M4-RE](https://github.com/DavidBuchanan314/ILCE-7M4-RE) —— A7M4 bootrom 串口引导路线（本项目的 A7M4_ROUTE 即基于此）
- [whc2001/SonyMultiPortRemoteControl](https://github.com/whc2001/SonyMultiPortRemoteControl) —— Multi 口遥控协议参考

## 免责声明

本项目仅供**安全研究、互操作性研究与个人学习**使用。仓库不含任何 Sony 版权材料；
文中与工具内出现的加密密钥均为社区已公开信息。对相机固件的一切写入操作（刷机）
存在变砖风险，本文档中的相关分析不构成操作建议，使用者自行承担全部风险。
与 Sony Corporation 无任何关联。
