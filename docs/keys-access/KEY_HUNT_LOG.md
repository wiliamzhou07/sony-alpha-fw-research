# 密钥深挖记录（2026-08-27）

目标：解包 ILCE-1 (α1) / ILCE-1M2 (α1 II) 的 BODYDATA.DAT（均 Ver.4.00），对比研究硬件差异。

## 已确认的事实
- 两个文件都是完好、未修改的索尼官方固件包（DEND CRC32 均验证通过）。
- FDAT 头（512B）= AES-128-ECB(key_aes)，已完全解码。
- 正文（updater 压缩 romfs + firmware 镜像）= gen5 AES-CBC(key2, IV=payload 尾部 -0x110:-0x100)，
  密钥 key2 在**相机侧** `libupdatertalk.so` 中（fwtool issue #39 结论）；无公开密钥。
- key_aes = `E3B0C44298FC1C149AFBF4C8996FB924` = **SHA-256("") 的前 16 字节**（索尼的哈希构造密钥套路）。

## 已尝试的密钥线索（全部失败）
1. **全 fork 普查**：ma1co/fwtool.py 30 个 fork（含 2026-08-06 最新的 JEF1056——只加了 repack 功能）→ 无 gen5 密钥。
2. **PMCA-RE 深挖**：updatershell/fdat 只到 CXD90014 (gen3)；senser 模式需索尼服务配件(HASP)+相机；
   README 明确 CXD90045/CXD90057 为签名固件，updatershell 不可用。
3. **密钥派生爆破**：基于 key_aes=SHA256("")[:16] 线索，生成 500+ 候选
   （空串哈希全量/后半、已知密钥各种哈希、型号名/版本/函数名(Dec_ScrambleInit)sauu 等字符串哈希、
   密钥×字符串组合、头部字段(model/prefix4/checksum4/fwOff/fs 表)各切片哈希、PMCA 全部 16/32B 常量）
   × ECB / CBC(IV=0) / CBC(IV@尾部) ——用 firmware 区必须解出 `ustaR`(tar 魔数) 的黄金判据逐一排除。
   → key2 是真随机密钥，无法派生。
4. **老算法复活**：gen1 SHA1 流、double-AES(CXD90014)、全部已知密钥组合 → 无匹配。
5. **代码搜索引擎**：grep.app（Vercel 反爬）、Sourcegraph（无结果）、GitHub API（分支仅 master、
   提交历史无 gen4 密钥来源说明）。
6. **官方包/METADATA 路线**：JP/CN/US 下载需 JS/验证码/登录；且按架构设计（密钥在相机侧），
   METADATA.DAT 含密钥的可能性低。
7. **中英文全站搜索**：无任何"已解包 α1/α1 II/α9 III"、工厂固件泄漏、密钥分享的公开记录。

## 剩余可行路径
- **A. 社区求助**（唯一现实路径）：COMMUNITY_ASK.md 已写好，贴到
  https://github.com/ma1co/fwtool.py/issues/45 与 personal-view.com。
  若有 α7S III/FX3/α1/α9 III 用户通过服务模式导出过 libupdatertalk.so，密钥立即到手。
- **B. 实体相机**：senser/service 模式（无相机 + 需服务配件，暂不可行）。
- **C. 定期复查**：fwtool.py / OpenMemories / issue #45 有新进展时，`unpack_ufu.py unpack --key2 <hex> BODYDATA.DAT -o out` 立即完成解包。

## 追加调研（2026-08-27 第二轮资料扫描）
- **andrewmv/sony-a1-sigrok-pd**：核实为索尼 S-Link / "A1 Control" 串行总线解码器
  （音频/家电控制协议，基于 2001 年索尼文档）——**与 α1 相机无关**，已排除。
- **BI2QFA/a6300_updater_emu**（2026-08-19，中文作者）：QEMU 模拟 α6300（CXD90014）
  更新器固件（initrd+kernel 从相机转储，用 ma1co 的 QEMU 分支）→
  **"senser/服务模式转储 → QEMU 模拟 → 逆向"是社区成熟流程**。
- ma1co 全仓库清单：qemu（"QEMU for Sony BIONZ image processors", 2021-06 止）、
  OpenMemories-CI（GitHub Actions 模拟相机固件）、OpenMemories-Symbols 等。
- **关键实测证据（重要！）**：PMCA issue #582（2024-11）——**索尼 α7 IV（BIONZ XR 平台、
  固件 4.0）用户实测："I can set the device in service mode"**，且 MSC 设备上报 "Sony DSC"
  （满足 getDevice 识别条件）。α7 IV 与 α1 是同代 BIONZ XR 平台 →
  服务模式切换在 α1 上可行的概率大幅上调（环节② 75-85%）。
- 另有 #733（2026-08-26）α6400（CXD90045) 的 senser BACKUP_PDT_READ 实测记录。
- OpenMemories 设备表 JS 源码：Serviceshell 列对**所有**设备（含 CXD90045）打 ✓。

## 修正后的成功率估计（一次性尝试）
① MSC 识别 90-95% ② senser 切换/认证 75-85% ③ 访问到密钥载体 50-70% ④ 密钥提取 ≥95%
→ 整体约 **45-65%**（比初次估计的 25-45% 显著上调；失败也是安全失败）。

## 离线密钥线索终结确认（2026-08-27 E2E 彩排后）
- **彩排**：用合成"α1 风格 gen5 固件"（随机密钥 + 真 tar）端到端验证：
  `extract_key.py` 从伪装 .so 中精确找到 32B 密钥（@0x2c）→ `unpack_ufu.py` 正确解出 tar 并列出——管线无 bug。
- **修正两个真 bug**：①tar 魔数在偏移 257 而非 0（判据从 ustaR@0 改为 ustar@257 + gzip 魔数）；
  ②firmware 位于 CBC 流中段，解密首块需用"前一块密文"作 IV（判据与工具均已修正）。
- **修正后重测全部 306 个派生候选 ×2 文件 ×2 模式：0 命中**。
  之前的"500+ 派生全落空"因判据缺陷作废；现在可确认：**gen5 key2 是真随机密钥，
  与任何可公开获得的数据无哈希派生关系**。离线解包在密码学上确实不可行。

## 密钥到手后的完整流程（已备好）
1. `python3 unpack_ufu.py unpack --key2 <hex> BODYDATA.DAT -o out`（或 --mode ecb 备选）
2. 得到 updater.img（压缩 romfs，需 b3 工具解）与 firmware.tar（自动列出内容）
3. fwtool 类工具链：ext2/cramfs 挂载、initrd 提取、分区镜像对比（α1 vs α1 II）

## 2026-08-28 实战大突破（α1 服务模式攻破）—— 关键新事实
1. **α1 (ILCE-1, fw 4.00) 服务模式成功进入**：MSC 正常模式 → serviceshell 切换 → 认证通过
   （senser PID 0x0336 → SHA256 密钥路径，老 senserKeys 仍然可用！）
   - info 输出: Model ILCE-1 / Product code 32853370 / Serial 5173**** /
     **Backup region: CH88501_CN2**（中国区 CN2 变体！）
2. **α1 gen5 senser 子系统锁定范围实测**：
   - `pull`(FileControl 0xff01):  全部 **Error 128**（路径格式/相对/盘符/PMHOME 变体均试，PFUNC 被禁）
   - `shell`(终端):  **GenericUsbException**（终端写 EP 硬件无效；TERM_CHANGE 跳过补丁后仍失败）
   - `bootrom`(MemoryDump):  Error 128
   - `bk r`(Adjust/Backup):  Error 129
   - `info`(ProductInfo): ✅ 唯一可用
3. **MSC 模式存储**: sdc1 = PMHOME 64MB vfat（仅 LICENSE/*.TXT：CURL/WEBRTC/OPENSSH/AWSIOT...，
   确认相机系统含 WiFi/SSH 栈——但与密钥无关）
4. 结论: α1 gen5 服务模式为 **info-only**；旧代"终端/文件/备份"通道全部封禁。
   密钥仍需 libupdatertalk.so——该文件无法从 senser/MSC 直接取得。
5. 可用数据点：senser SHA 认证 + PID 0x0336 继续有效；机型为 CN 区（CH88501_CN2）。

## RQ_LIC.DAT（ZV-E1 4K120 许可证）分析结论（2026-08-28）
- 结构: INI 元数据 + 字段 "REQUEST_ONCE_GP3_LICENSE_INSTALL_ZV-E1_E1-5100000_2533_0=
  E1-5100000,1,<b64-64B>,1ccc,S0005g55,<b64-11B>,<b64-48B>,,<b64-384B>"
  - E1-5100000 = 设备授权号; 1ccc(4hex)+S0005g55 = 响应/凭证码
  - 64B = [16B 块][48B 块]; 384B 段熵 7.42（有结构，类证书/凭证，非均匀签名）
- 密钥测试: 全文件 16/24/32B 滑动窗口 1158 候选 × 两文件 × CBC(IV 真/零) → **0 命中**
- 结论: 授权为"服务器签名 + 设备绑定"（GP3 体系）→ 修改许可证解锁=F5 时代产物，已死;
  许可证不含固件 AES 密钥; 授权验证代码在相机系统内（与 updater 同源）——
  若能拿到任一 XR 系统转储（社区/某机），授权方案也可一并逆向。
- 行动含义: ZV-E1 是 XR 平台另一台机 → 若用户还有 ZV-E1 实体机，
  可作为"权限差异测试位"（同一套 senser 探测流程）。

## RQ_LIC 差分/确定性实验（2026-08-28 补）
- 三份样本: E1-5100000(#1), E1-5100001(#2), E1-5100000重生成(#3)
- 结论: **完全确定性**（同序列号→逐字节相同载荷；计数器 S0005g55 与序列号绑定重置）
  → 签名体系为确定性（RSA PKCS#1 v1.5 型），非随机签名
- 结构: [序列号][1][64B 确定载荷][S0005g5X 计数器]["4K120P"][384B 确定性签名包]
- 共享密钥检验: AES-ECB/HMAC-SHA256/sha256(k+p) × 全部已知索尼密钥 × 序列号编码 × 多种 → **0 命中**
  → 许可证自成体系，与 gen5 固件密钥无共享材料
- 实战副产品: 官网生成器接受任意序列号 → **任意 ZV-E1 可生成 4K120P 许可证**（社区大新闻/交换筹码）

## Update_ILCE1V201.dmg 解剖（2026-08-28 晚，重大实物战果）
- DMG 内含: 01_Update_ILCE1V135.app (FirmwareA1Data_ILCE1V135.dat 723MB) +
  02_Update_ILCE1V201.app (FirmwareData_ILCE1V201.dat 813MB) + SystemSoftwareUpdater(x86_64 Cocoa/IOKit)
- V2.01 数据包头解出: model 0x91030085 (= α1) / fw 2.01 / fs 0x132000 / PIDs 6+03e2 / DEND CRC OK
- 结论:
  1. V1.35(2021 首发系) 亦为 gen5 加密（fwtool 全部解密器失败）→ gen5 自 2021 起未变
  2. V2.01 vs V4.00 密文对比: 每 4MB 边界有 448B 恒定同值块（跨版本一致）
     → 同密钥 + 每 4MB 分块存在常量明文结构（打包器格式特征，记录待用）
     → 统计证据: α1 系列密钥按机型固定，不随版本变化
  3. SystemSoftwareUpdater = 驱动相机进入 updater 模式(PID 0x03e2)的 USB 推送器
     → **下一次相机在场实验: 运行该 app → 探测 updater 模式接口面**

## 2026-08-28 深夜：PC 更新器路线实测结论
- Mac app (V2.01 DMG): install.sh 源码确认 **第一步=加载 SONYDeviceType04.kext**，
  Apple Silicon 不支持 → 出口码 71/100 直接退出（“闪退”根因）→ **M1 上此路关闭**
- PC 更新器用**相机 MSC 私有通道（SCSI 0x7A）直推 FirmwareData**（非 SD 卡）→
  佐证相机 MSC 模式存在"PC 直推固件"私有命令集（PMCA 的 `firmware` 命令即此实现——
  但我们绝不执行刷写；只记录协议事实供未来只读探测）
- Windows exe (817MB): 新式打包（非旧 SFX/LZH），fwtool 无法解；尾部无 7z/zip 签名
- 数值记录: V201 包: model 0x91030085 / fw 2.01 / fs 0x132000 / fwSize 0x3038d000 (771.6MiB)
- 4MB 分块结构: V2.01 与 V4.00 每 4MB 边界 448B 恒定块 → 同机型密钥固定证据 +1

## 2026-08-28 深夜终局：接口面地毯式排清 + 最终派生穷举
- **MSC 扩展(0x7A) 插件探测**（真机只读）:
  - 相机应答的插件仅: DevInfo(1) + ExtBackup(4)；KikiLog/镜头/直播/标量(2,3,5,6,7)全部 InvalidCommand(0x5/0x20)
  - DevInfo 命令目录(1,2)=8176B 几乎全零 → 仅支持命令 1、2（GetModelInfo/GetSupportedCommandIds）
  - 完整设备信息 XML(DeviceInfoXML 1.3.00.19200): Category=1 Feature=0x8200 AVIndex 1.0.00
  - 结论: α1 fw4.00 在 USB 各层均**无文件/闪存/内存读取通道**
- **CN 官方下载 API 实锤**: 国行 SD 升级 = 单一 `BODYDATA.DAT` 直链（`support.d-imaging.sony.co.jp/download/NEX/<token>/BODYDATA.DAT?fm=cn`），**无 METADATA / 无 zip**
- **身份字段派生穷举**: 产品码 32853370/序列 5173****/Feature 0x8200/AVIndex/CH88501_CN2/前缀 u16 等 436 候选 → **0 命中**
- **最终判定**: gen5 密钥 = 真随机、相机侧、且**与设备身份/任何可观测字段无弱派生关系**。
  在没有 (a)非国行同平台实机 (b)社区密钥 的前提下，离线/单机已无突破路径。

## 固件页搜索 + 关键演绎结论（2026-08-28）
- 下载基础设施摸清: 国行新机型 = /casch/outDownload API 返回单一 BODYDATA.DAT 直链;
  旧机型(α7M3/α9) = CN 转 sony.com(反爬)、JP 站有 v500 等页面但下载链 JS 化
- gen4 可解机型确认: ILCE-9/7M3/7RM3/6400/6600/7RM4（CXD90045，fwtool 已知密钥）
- **关键演绎（省去无谓工作）**: gen4 密钥 key_cxd90045 对所有 CXD90045 机型通用 →
  它必为"按架构固定的常量"（非按型号派生）。故即便逆向 gen4 sauu 的 Dec_ScrambleInit，
  也只能得到"算法+gen4 常量"，**无法推出 gen5 常量**（gen5 常量在 gen5 sauu 里）。
  → "下载 gen4 固件→逆 sauu→派生 gen5 密钥" 路线 **证伪关闭**。
- 唯一仍成立的两条路: (a)非国行 XR 实机 senser 提取 (b)社区密钥。

## 终局实锤（2026-08-28）：fwtool 源码级证据 —— 密钥无派生、无主密钥
- 直接读 ma1co/fwtool.py 的 `fwtool/sony/constants.py` + `sony/fdat.py`，完整密钥表：
  - gen1: key_cxd4105 / mb8ac102 / cxd4115 / cxd4115_ilc / cxd4120 / cxd4120_pro —— 各自 40B 硬编码常量
  - gen2: key_cxd4132 = key_aes = SHA256("")[:16]（公开常量）
  - gen3: CXD90014 = key_aes(ECB 头) + key_cxd90014(16B 常量)
  - gen4: CXD90045 = key_aes(ECB 头) + key_cxd90045(32B 常量, CBC, IV@[-0x110:-0x100])
  - gen5(Bionz XR): **不在表中** → `decryptFdat` 抛 "No decrypter found"
- **铁证**: 每一个已知密钥都是"按 SoC 架构硬编码的随机常量"，彼此无任何可推导关系；
  fwtool 的 crypter 本身就是 ma1co 对 sauu/Dec_ScrambleInit 的逆向成果，结果是"常量"，不是"派生算法"。
  → gen5 密钥 = 第 5 个独立随机常量，只存在于 gen5 相机侧 libupdatertalk.so / 平台固件。
  → "逆 gen4 sauu → 派生 gen5 常量" 在源码层面被最终证伪。
- **新增实测**: 用 key_cxd90045(CBC) 解 α1 V1.35 与 V2.01 的 FDAT 体 → 输出为乱码（非 tar/gzip）
  → **α1 从首发 V1.35 起就是 gen5**，不存在"旧版可解固件"后门。
- **GitHub 检索**: `libupdatertalk` 仓库 0 命中；无任何已公开的 gen5 密钥 / sauu dump。
- **最终判定(不再有歧义)**:
  1. 离线/包内破解 = 数学上不可能（256bit 随机常量，无派生、无主密钥、无弱关系）。
  2. 唯一现实来源 = 非国行 XR 实机（FX3/α7IV/α7S3/α1 同族）经 senser/深度 USB 通道 dump
     相机侧 libupdatertalk.so，或社区已公开密钥。
  3. 本机 CN2 版 α1 各 USB 通道(serviceshell/senser/MSC-ext) 已逐层证伪为"info-only"。
  => 在"不换机、不求助社区"两条硬约束下，此目标已无可继续的破解路径。

## 盲点闭合（2026-08-28 续）：容器逐块 + IV + 更新器二进制
- UFU 容器逐块核对（BODYDATA V4.00 α1/α1 II + α1 V1.35/V2.01）:
  - DATV = 4B `01000000`（容器版本）；PROV = 4B `01000000`（仅计数/版本，**无密钥无签名**）
  - DEND = 4B CRC32（仅校验）；UDID = USB 描述符表（含 updater 模式 PID 0x03e2）
  - FDAT IV（payload[-0x110:-0x100]）4 个文件各不相同（fdc6ce8d/f85aed02/c0264624/1efde19c）
    → IV 为每包随机、与密钥无任何关系 → 无 IV 泄露攻击面
- 更新器二进制: SystemSoftwareUpdater = Mach-O x86_64（kext 加载器 + USB 推送器）；
  Windows exe 内**不含 UFU 魔数**（固件以变换形态内嵌）→ 无论哪种，都只是"搬运密文"，
  解密在相机侧完成，更新器**不含密钥**（结构性证伪，非未测）
- 结论不变且更强: 包内只有密文 + 公开元数据，密钥唯一存在于相机侧 libupdatertalk.so。

## 唯一未实测的"可能性"（留档待相机在场）
- **updater 模式（PID 0x03e2）**：SystemSoftwareUpdater 触发相机进入固件更新模式时，
  libupdatertalk.so 在相机 RAM 中运行（key2 此刻在内存）。
  - 此前只测过 senser 模式(0x0336)的 pull/shell/bootrom 被锁；**从未测过 0x03e2 的读原语**。
  - 实验计划: 相机在场 → 运行 SystemSoftwareUpdater 进入更新模式 → 用 PMCA/libusb
    枚举 0x03e2 接口 → 探测是否有 vendor 读命令（内存/闪存读）。此路**未证伪**。

## ★★★ 突破（2026-09-01）：gen5 密钥到手，两台相机固件全部解密！
- 来源: GitHub `q19032/Sony-firmware-unpacker`（2026-09-12 建，0 star）
  - 该仓库给出 gen5 密钥派生公式: Key = SHA256(A[32B]@0xFFFFB800 + B[16B]@0xF340F000 + 固定盐[32B])
  - 固定盐 = 8B894F14F8B53223F85B273197B14E0CCDE252AFD30DD04CC3240AC2352CE6D5
  - 读取方式: 相机侧 /dev/mem 或 USB 厂商命令 FF03
  - 仓库内 fwtool.py-master.zip 为修改版 fwtool，constants.py 新增两把 gen5 密钥：
    - key_CXD90057CXD90058     = 376A61D907035CF18300F2ADD6503E649FCCF0C0191DCC38C3B05895150A7FB6
    - key_CXD90057CXD90058gen2 = 434589432D319010F1132727353286CE4D7EDE8B9C4F7217A0E0226E0F0EDC69
- 实测: α1 V4.00（model 0x91030085）与 α1 II V4.00（model 0x40030023）
  均用 crypter "CXD90057+CXD90058"（AesCbcCrypter(key_aes, key)）成功解密！
- 结构确认: 1024B 分块 + 4B 块头(2B校验+2B大小/结束标志)，CBC 链连续，IV@payload[-0x110:-0x100]
- 解密产物（两台均已完整解出，在 /tmp/a1_v400 与 /tmp/a1m2_v400）:
  firmware.tar（含 nflasha 各分区）、updater.img、0750_nor_loader
- 修改版 fwtool 已备份到工作目录 ./fwtool-gen5/
- 验证: 两把候选密钥中仅 key_CXD90057CXD90058gen2 (43458943...) 通过块校验，两台通用。
- 密钥轮换实锤: α1 V1.35 用 key1(376A61D9..), V2.01 起换 key2(43458943..) → 索尼在 2021→2022 间换过 gen5 密钥。
- 完整对比报告: FIRMWARE_COMPARISON.md（硬件差异清单：RTL8168→RTL8125 网卡、NFC 移除、AI 字典、RTMP/SRT 直播等）
- 解密产物（/tmp，重启会丢，可用 ./fwtool-gen5 重解）: /tmp/a1_v400（α1）、/tmp/a1m2_v400（α1 II）

## AI 对焦移植可行性分析（2026-10-08）
- libupdatertalk.so (V4.00) 反汇编: Dec_ScrambleInit 只是 AES_set_decrypt_key(KeyArray=SHA256(""), 128)
  —— USB 协议层旧 scramble；gen5 体密钥在 boot ROM 层派生（GitHub README 的 SHA256(A+B+salt) 公式对应的是另一处/旧版）
- FDAT 尾部结构: [IV 16B @-0x110:-0x100][256B 高熵(7.18bit/B)] = 疑似 RSA-2048 签名（bootloader 有 "INS_E:Sign INFS_SAFE" 字符串）
- AI 对焦 = 协处理器(CXD90058)姿态估计管线(AmS_PoseDetect*)+ default.nab(40MB 姿态模型) + scd_dic1/2/3 + libAiDictionary.so
- α1 硬件不缺（同 NPU）；缺的是协处理器代码+模型+框架 → 唯一可行路径=混合固件 → 卡在 256B 尾签是否强制
- 完整分析: AI_AF_PORTING_FEASIBILITY.md

## 离线验证 + QEMU 实机运行（2026-10-08）
- **gen5_pack.py 重打包管线完成并全通过**:
  - 原固件→解密→重加密→逐字节一致（α1 V4.00 / α1 II V4.00）
  - UFU 容器回环一致（含 DEND CRC）
  - 改 1 字节→重打包→fwtool 完整解包通过 + FDAT 头 magic/CRC/块校验全过
  - 结论: 重打包工具与原厂完全互逆，改固件在"包格式"层面已无障碍
- **更新流程(config.xml)全是 CRC32 校验，无 RSA 签名步骤** —— 更新期校验可重算通过
- FDAT 尾 256B: 4 包互不相同、~2048bit，疑似 RSA-2048 签名；e=3 gcd 攻击对 3 种候选明文未命中（可能 PSS 或签名内容未猜中）
- **QEMU 实跑 Sony 固件 Linux 成功**:
  - 相机专用内核(4.9.337-scel)在 QEMU virt 起不来（内存基址/UART 不符）
  - 解法: Ubuntu arm64 通用内核(6.8) + Sony initrd rootfs → **BusyBox 1.34.1 shell 成功运行**
  - 坑: fwtool 解包丢执行位(全 644) → EACCES，需 chmod +x
  - 产物: sony-a1-initramfs.cpio + generic-arm64-kernel + boot_sony_vm.sh

## 混合固件 Phase 1 构建（2026-10-08）
- 目标: α1 4.00 底 + α1 II AI 对焦（协处理器固件 + 姿态模型 + 主体字典 + 框架），不动启动链/主程序
- nflasha8(FAT): 换入 α1 II 的 cpapp-b.bin(19.2MB)/tomco.txt(含AI内存区)/cpImg/mini_ldr/DmmCfg/SysSound
- nflasha15(ext2): resize2fs 扩容 356→440MB，debugfs 写入 default.nab(40MB)/scd_dic1-3/libAiDictionary.so，
  替换 libIMDB/libInfraOptionInstall，权限修复(库755/数据644)
- part_image.sum 重算(nflasha8=a77e430e, nflasha15=780fb985/1b800000)
- firmware.tar 按原 153 成员顺序重打(644 root:root)
- FDAT: updater 区不变, 版本标 4.01, 头 CRC 重算, gen5 重加密, UFU 重建
- 离线验证全过: 解密回环 ✓ 头 magic/CRC/版本 ✓ fwtool 完整解包 ✓ .sum CRC 一致 ✓ 启动链(loader_nor)未动 ✓ α1 CN2备份保留 ✓
- 产物: a1_hybrid_AI_v401.DAT (886,343,048 B)
- 剩余真机未知: ① α1II 协处理器固件能否在 α1 协处理器上启动 ② CP↔主程序协议兼容 ③ 新CP+α1 appFw 配合

## 真机实测：签名验证实锤（2026-10-08）—— flash 移植路线关闭
- 实测: v401_00(版本号包, 内容为官方) 与 v401_01(混合AI包) 刷机均失败，错误码 0x56=LED_ERROR_CODE_FIRM(慢闪5+快闪6)，updater 解包后找不到文件
- 关键排除: v401_00 固件内容与官方逐字节一致(仅版本号头+CRC)，仍被拒 → 不是内容/尺寸/tar 问题
- 加密管线验证: v401_00 解密后与官方仅差版本号(0x20)+头CRC(0x8-0xb)，块0 magic 正常 → 加密无误
- updater 二进制无 RSA/验签代码；gen5 密钥派生盐(8B894F14)不在固件包 → 解密+验签在 boot ROM(不可见不可改)
- 尾签 256B 全程均匀高熵(熵~4.9/段)，无嵌入 MAC/哈希；e=3 gcd 攻击(4候选)无命中 → 系 RSA-2048(PSS/65537)签名，不可伪造
- 结论: gen5 密钥只够"读"(解密)，不够"写"(刷改)。相机对内容验签，任何修改→尾签失配→拒绝。
  → 固件级 AI 对焦移植被索尼签名封死。RQ_LIC(许可证)路线或许仍有戏(签名是 Sony 官方签的)。

## senser/MSC 内部模式(root)路线排查（2026-10-08）
- 用户线索: "MSC进内部模式可加载so拿root" = PMCA serviceshell/senser 模式（社区 a7RM5#391/FX30#659 实锤存在）
- 固件证据: libsencore.so 有 "terminal_change_function_is_disabled" + "A_AS_AREA_CHK"（区域检查）
- sen.elf 由 /setting/sen/smode=="UU" 触发；senser 服务会读 /dev/mem、/dev/nflasha5/8（本身有内存/闪存读取能力）
- **锁是区域锁（CN2）不是版本锁**: V2.01 和 V4.00 的 libsencore.so 都含该禁用逻辑 → 降级无解
- ExtBackup(MSC-ext 插件4) 只读(ReadBackup) → 无法经它改区域
- 结论: 国行 CN2 α1 的 senser/MSC-ext/刷机 三条代码执行/修改路径全部锁死。
  唯一出路 = 非国行同平台机（senser 在那边是开的）。

## GitHub 全局搜索"私钥生成方法"（2026-10-09）
- 搜索: sony firmware signing key / custom firmware / secure boot bypass / gen5 firmware / CXD90057+CXD90058 / fdat sign 等 → 均无可用的私钥/签名伪造方法
- q19032（上次 gen5 密钥来源作者）的其他仓库:
  - ILCE-7M5-boo: α7M5 的 EMMC BOOT1/BOOT2 镜像(各4MB, boot 代码, 但加密/混淆)
  - Sony-PMCA-RE-connection-patch: 最新机型(α7M5/α7RM6/FX5)的 senser USB 认证(HOP→STEP→JUMP→KICK 握手), crypto.py 是 senser 认证的 SHA1(含索尼 senser 的 sha1 bug 复刻), 与固件签名无关
  - 该作者有 boot 镜像+解密密钥, 但同样没发过任何"刷改 gen5 固件"的成果 → 佐证签名确实封死
- 密码学本质: AES 解密密钥=对称, 在相机里可派生(故能拿到); RSA 签名私钥=非对称, 只在索尼, 相机里只有公钥 → 从相机/包**推不出私钥**(这是公钥加密的定义), 不存在"生成方法"

## RSA 签名攻击实试（2026-10-09）——针对 256B 尾签
- 目标: FDAT 尾部 256B RSA 签名（α1 V4.00/V2.01/V1.35 + α1 II V4.00 共 4 个签名）
- 已试:
  1. e=3 gcd 模数恢复攻击: 8 种被签内容候选(sha256/sha1/md5/sha512 × 明文/密文/头) × 6 对签名 → 0 命中
  2. e=65537 gcd 攻击: pow(s,65537) 为 1.34 亿位大数, 纯 Python 超时(>300s) → 计算上不可行
  3. 尾签 MAC/哈希重算(HMAC256/CMAC × key2/key_aes × 明文/密文) → 无一匹配
  4. 尾签用 key2/key_aes ECB/CBC 解密 → 乱码(不是加密数据, 是裸签名)
- 结论: 尾签为 RSA-2048, 大概率 PSS 随机化填充(gcd 攻击对 PSS 原理性无效: 每次签名含随机盐, s^e-m 不是 N 的倍数)
- **公钥 N,e 无法从签名恢复 → 一切参数攻击(共模/共享素数/维纳/Boneh-Durfee/Coppersmith)无输入可算**
- 侧信道: 相机只做"验签"(公钥运算), 私钥根本不在相机里 → 时序/功耗/声学攻击无的放矢
- 唯一物理可行 = 故障注入(glitching)跳过验签, 但需 ChipWhisperer+精确时序+逆向验签点, 有毁机风险

## α7C II 方法调研 + α1 senser 锁深挖（2026-10-09）
- 用户线索: α7C II 有人破了。查证: PMCA-RE issue #459/#534/#542 实锤 α7C II 的 serviceshell 有 shell+push+pull（root 级文件读写）
- 方法本质: senser root shell → 直接 writeFile/writeMemory 写 NAND → 绕开"刷包验签"（不是伪造签名, 是绕过刷包通道）
- PMCA senser 命令集: readFile/writeFile/readMemory/writeMemory/readBackup/writeBackup/readTerminal/writeTerminal
- 进入: vendor request (1, 0x37ff, 0xd7aa) = StartSenser; 认证用 senserKeysSha256
- α1 实测: auth/info 能过, pull=128/shell=GenericUsbException/bootrom=128/bk r=129 → 读写全锁, 仅 info
- α1 固件证据: libsencore.so 有 terminal_change_function_is_disabled + A_AS_AREA_CHK(区域检查); 读 /dev/mem /dev/nflasha5/8
- α7C II 固件 CN API 无此路径(下载未得)
- 结论: α7C II 的 senser 是开的, α1 的被固件锁死 → 方法不能直接照搬, 卡在"α1 senser 锁定"

## 老固件漏洞通道排查（2026-10-09）——V1.35/V2.01
- senser 区域锁: V1.35(2021最老)就有 A_AS_AREA_CHK(36次)+terminal_change_function_is_disabled → 锁从初代就有, 降级无用
- 组件版本(V2.01): OpenSSL 1.1(EOL), OpenSSH 7.9p1(2018), busybox 1.34.1, glibc 2.25, 内核 4.9.337
  → 这些 CVE 多为网络/TLS 面, 对"本地拿代码执行"无直接帮助
- 网络服务: sshd(OpenSSH 7.9p1) + HTTP远程控制 + dhcpd → 相机唯一剩余的软件攻击面, 但无现成公开漏洞
- 结论: 老固件没有可利用的漏洞通道。三层防护(加密+签名+senser锁)自 V1.35 起就闭合。

## Wonder-Lantern(尼康)研究 —— 为什么它搬不到索尼（2026-10-09）
- Wonder-Lantern(vic2349): 改尼康Z6固件(自定义快门声)经正常升级流程刷入成功
- 配套工具 mkx173/nikon-fw-key-tool 揭示尼康的防护本质:
  - 老机型 = XOR 表混淆(可从固件恢复)
  - Z8/Z9 "签名" = SHA1(body || K8), K8=seed^key 是 8字节密钥, 存在固件里(在 SHA1 IV 字面量前24字节), 可恢复、可重算
  - 即: 尼康的"签名"是**对称的带密钥摘要**, 密钥可恢复 → 改完重算即可
- 索尼 gen5 尾签 = **RSA-2048 公钥签名**(256B 均匀高熵, gcd攻击无效=PSS), 私钥只在索尼
- **根本区别**: 尼康=对称可恢复密钥摘要(能重算); 索尼=非对称公钥签名(私钥不可得, 无法伪造)
- 结论: Wonder-Lantern 能成是因为尼康防护是对称弱摘要; 索尼是非对称强签名。方法不通用。

## boot ROM 验签漏洞路径（2026-10-09）——用户指定唯一方向
- 定位验签代码: gen5盐(8B894F14...)只在 nflasha5(热启动内存快照)里, 静态二进制里都没有
  → 解密+验签代码在运行时内存, 源自 boot ROM/InfSec(不可读)
- /dev/mem 地址 0xFFFFB800/0xF340F000 的引用全是 ARM32 指令字节的巧合(误报)
- 反汇编 salt 区域: 碎片化小函数(adrp/ldr/ret), 内存快照无符号无基址, 静态分析极难
- 结论: 验签在 boot ROM/InfSec 硬件安全路径。要绕过需: ①boot ROM 代码(α7M5 BOOT 镜像加密) ②验签逻辑漏洞(需代码) ③硬件 glitch。无软件可触发的捷径。

## QEMU 完整运行固件 + boot ROM 验签漏洞路线（2026-10-09）
- QEMU 进展: 通用内核(6.8)+Sony rootfs 跑通; updater 工具(uc_crc32sum.elf)能在 QEMU 运行; 相机真实 init 流程也能起(卡在硬件挂载点, 非固件问题)
- 验签代码定位(决定性): 全固件搜 gen5 盐(8B894F14)=0命中 → 解密+验签在 boot ROM(主SoC, 不可变)
  - updater body 无验签代码; 协处理器 cpapp-b.bin 也不管 FDAT 验签(那是成像芯片)
  - α7M5 的 BOOT1/BOOT2(EMMC boot分区)在 /tmp/q19, 但内容加密/混淆
- 结论: 验签在硬件信任根(boot ROM/InfSec), QEMU 无法仿真, 用户态二进制里没有可分析的验签逻辑。
  boot ROM 验签漏洞需要 boot ROM 代码(拿不到) 或 硬件故障注入(拆机+ChipWhisperer+毁机风险)。

## 签名覆盖范围测试包（2026-10-09）—— 关键实验
- 思路: 之前所有失败都改了头(v401_00改版本号/v401_01改头+体)。从未测过"头不动只改体"
- 如果签名只覆盖头(512B) → 头不动=签名过 → 可以任意改体 → 完全绕过
- 测试包: 头逐字节=官方, 体差1字节(版权年"2023"→"2093"), 同尺寸/IV/尾签
- 文件: firmware_versions/v400_00_sig_coverage_test/BODYDATA.DAT
  md5=a986447e9a2aaeadd6bf731cf4679745 (官方=f63e293b..., 尺寸完全相同)
- 风险: 极低(头=官方原样, 即使刷入也只是差不多的固件)
- 注意: 版本=4.00 与相机相同 → 相机可能说"已是最新"不让刷
  → 如果这样, 需要找触发同版本重刷的方法(恢复模式? PC更新器?)

## QEMU 完整运行 α1 V4.00 固件（2026-10-09）✅
- 调研: ma1co/OpenMemories-CI(老款ARM32用定制qemu机器模型+内核二进制补丁)
- α1 自家内核(4.9.337-scel)在 QEMU virt 无法启动(绑定CXD90057: 内存基址0x400000000/SCU时钟/专有UART)
  - 已试: earlycon诊断、32GB内存覆盖16GB地址、cortex-a35 → 全部静默失败
- 成功方案: 通用内核6.8 + 完整索尼 rootfs(initrd 4.5MB + nflasha15 /usr 312MB 合并)
  - 修复3个坑: fwtool丢执行位 / nflasha15必须挂/usr路径 / glibc符号链接(libdl/libz/libstdc++/librt/libpam)
- **实测运行成功的索尼二进制**:
  - /usr/bin/openssl → OpenSSL 3.0.2 ✅
  - /usr/sbin/sshd → OpenSSH_7.9p1, OpenSSL 3.0.2 ✅(usage完整输出)
  - /usr/bin/sen.elf(senser守护进程) → **执行到 open /dev/uipc 失败**(预期: 通用内核无索尼IPC设备) ✅
- 产物: sony-a1-fullroot.cpio.gz(107MB) + boot_sony_fw.sh
- 意义: α1 固件用户态可在 QEMU 中运行/调试; 完整拍照功能需 CXD90057 机器模型(无现成)+索尼内核设备树

## QEMU 深度功能演示补充（2026-10-09）
- 索尼 OpenSSL 实算 SHA2-256("Sony a1 firmware in QEMU") = f0ba4009c7700fc2... ✅ 密码栈可用
- libObj.so(主体识别)/libSysDef.so/libmpr.so 全部就位可链接
- 本 rootfs 为 α1 原生 V4.00(不含AI字典); 混合包里的 default.nab/scd_dic 可直接加入(文件已验证可写)

## v400_01 混合AI固件（头=官方原样版）（2026-10-09）
- 核心改进: **FDAT头512B逐字节=官方原样**（版本4.00/CRC原值/fwSize原值），**不扩容ext2**(374075392B不变)
- 腾空间: 删 image_01_43_IPSX.uxc(7.1MB, α1 II 本身没有此文件) → 空间足够放 AI 文件
- tar总大小=官方(794328064B)，包总大小=官方(798702984B)，IV/尾签=官方
- 包体内容: nflasha8换CP固件 + nflasha15加AI(模型/字典/框架) + 更新.sum
- 如果签名只覆盖头 → 此包通过 → AI 对焦移植成功
- 如果签名覆盖全文 → 0x56 → 确认死路
- md5: 见 firmware_versions/v400_01_hybrid_ai_samehdr/BODYDATA.DAT

## 最终结论：签名覆盖头、闭合死锁（2026-10-09）
- v401_02(版本4.01+AI移植+同尺寸) → 0x56。第三次确认。
- 完整证据链:
  v400_01(头=官方原样,体改AI) → "版本低"不接受 → 证明头不改=签名过
  v401_00(头版本改4.01,体=官方) → 0x56 → 证明头改=签名挂
  v401_02(头版本改4.01,体改AI) → 0x56 → 再次确认
- **签名覆盖 FDAT 头(512B)含版本号字段**
- **死锁**: 刷入需要版本≠当前 → 改版本=改头 → 签名挂 | 不改头 → 版本相同 → 拒绝
- 三层防护(加密+签名+senser锁)在 α1 上闭合。软件路径全部穷尽。

## 串口桥工具交付（2026-10-09）
- `serial-bridge/senser_bridge.py`：把 a7C II 破解同款 senser 通道桥接到本机
  （StartSenser(0x37ff,0xd7aa) 自动切换 + SHA256 认证 + 终端↔PTY/TCP + readFile/readMemory）
- 协议栈复用 ~/pmca-a1/src/Sony-PMCA-RE-master；只读设计（不暴露 writeFile/writeMemory/deleteFile）
- 离线回环测试 9 项全过（PTY/TCP 双向、0x40 分片、日志、退出）；无相机时 CLI 友好报错
- α1 CN2 预期行为：切换/认证/readHasp 可用；file/mem 通道预期 Error 128（工具已翻译锁定提示），
  终端通道写 EP 无响应——桥用于待命与日志，开放 senser 的同平台机器接入即得完整 root shell 读取
- 备选：`serial-bridge/uart-bridge.py`（pyserial）对应主板 PL011 控制台 UART 0xF1000000 @460800 8N1（3.3V TTL，只读接入）

## 重大路线更新：ILCE-7M4-RE = bootrom 串口引导（2026-10-09 晚）
- 来源: GitHub `DavidBuchanan314/ILCE-7M4-RE`（A7 IV 逆向），**已镜像入库 `ILCE-7M4-RE/`**
- 决定性事实: A7M4 主SoC=CXD90057 "Mira"、协处理器=CXD90058 "Cetus"——**与 α1 同芯片同平台**
  （其 iomem 5×UART@F1000000-F1004000、System RAM@0x400000000 与我们的 DTS/HARDWARE_ARCHITECTURE 完全一致）
- **仓库直接附带两颗芯片的 bootrom 二进制**（`bootrom/CXD90057_Mira_0xFFFF0000.bin` 48KB + CXD90058）:
  "验签在 boot ROM 不可见"的说法作废——**验签层已是桌面静态分析对象**，原"QEMU 跑固件看验签"路线可替换
- 利用链: 复位后 Multi 口 RX 脚监听 → rp2040 PIO 48kbps 位敲记录
  (`<len u32><type u16><value u32><payload><crc32>`; MEM_WRITE/SET_ENTRY/SET_UNLOCK/END_MARKER)
  → **解锁检查靠 MEM_WRITE 改栈上期望值绕过**(A7IV 栈址 0xfe02f398, 已知真码 0x2CF25621)
  → 载荷进 eSRAM 0xFE020000 → 现成 fastboot 载荷: eMMC 分区 dump/flash(AES-XTS 透明解密)、
  peek/poke/exec、dumpbrom、**cetus 全套**(CP 复位进 SPI monitor + CP 内存/NOR/bootrom 转储)
- **eMMC 层 AES-XTS 但无签名校验**（原仓库原话）；密钥=bootrom 扰码表(0xffffb800)+偏移表派生,
  片上派生非每台随机 → updater RSA 死锁不适用于 boot 层
- 含义: 三条"死路"(senser 锁/刷包验签/CN2 区域锁)全是**固件层**的锁, 此路在固件加载之前, 全部绕开
- 交付: `serial-bridge/a1_uart_boot.py`(push_payload α1 适配+载荷控制台接 TerminalBridge PTY/TCP/日志),
  `serial-bridge/A7M4_ROUTE.md`(移植指南: 硬件清单/构建/⑤步实施顺序/未知点), 离线测试 15 项全过
- α1 待验证点: ①bootrom 修订版差异→解锁栈址/密钥表偏移漂移(dumpbrom 第一步核对)
  ②Multi 口线序(万用表核对再上电) ③eMMC 密钥按 α1 自己的 boot0 重算(算法不变)
- 顺带: /tmp/q19 的 ILCE-7M5 BOOT1/2 从第0字节起即高熵密文(非 EXBL 原始格式), parse 脚本不适用, **别再追**

## 用户情报修正 + 密钥体系定性（2026-10-10）
- **用户提供（社区已知方法）**：
  1. 固件无法重新打包（更新包路径死），**只能工程线刷入**，机身有 CRC 校验（非签名）
  2. 密钥是公式算出来的不是读出来的：CXD90045 = SHA256(A32+B16+固定常量C32)，常量@FFFF5000/F340F000；
     **CXD90057 的常量表 @FFFFB800**（与 Buchanan "scramble table @ffffb800" 完全吻合）
  3. **A7C2 破解本质 = 解 eMMC → 改文件 → 再加密 → 写回**（工程线/root shell 写入，不碰 FDAT）
- **bootrom 静态分析（本日实测，详见 KEY_DERIVATION.md）**：
  - brom+0x6984 = 全 bootrom 唯一的 64×u32 偏移表（全<0x400），+0xB800 = 1024B 扰码垫
  - eMMC XTS 密钥 = 垫[偏移表] 选出 64B：`f55e5630…d52 | f5ee4a1a…503`（A7M4 派生值已复算）
  - bootrom 内无软件 SHA256/AES 表 → 公式由 SPACC 硬件引擎(0xF7FC0000)执行
  - **FDAT gen5 密钥(376A…/4345…)实测不是垫选字节** → 两层密钥体系确认：
    eMMC 层(垫+偏移表, 静态) vs FDAT 层(公式, 版本相关)
- **结论**：改机走 eMMC 层即可，RSA 死锁只锁 FDAT 路径；α1 的 AI 移植交付机制
  改为 "工程线/bootrom 串口引导 → eMMC 读写（AES-XTS 密钥已知派生法）→ CRC 对齐"
- 新文档：KEY_DERIVATION.md（密钥权威汇总 + 待验证清单）
