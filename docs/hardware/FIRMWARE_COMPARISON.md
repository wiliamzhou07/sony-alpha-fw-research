# Sony α1 vs α1 II 固件对比报告

> 数据来源：两份官方固件（均 Ver.4.00）用 gen5 密钥完整解密后的文件树。
> - α1：`BODYDATA (1).DAT`（model `0x91030085`，798,702,984 B）
> - α1 II：`BODYDATA.DAT`（model `0x40030023`，1,194,332,648 B）
> - 解密密钥：`CXD90057+CXD90058 gen2`（AesCbcCrypter，key_aes ECB 头 + gen5 密钥 CBC 体）
> - 解密工具：`./fwtool-gen5/`（基于 ma1co/fwtool.py + q19032 的 gen5 密钥）

## 0. 内部代号

| | α1 | α1 II |
|---|---|---|
| 市场型号 | ILCE-1 | ILCE-1M2 |
| FDAT model | `0x91030085` | `0x40030023` |
| 内部 chassis 代号 | **CX88500 / CX88501** | **CX89900 / CX89901** |
| 项目目的地代号 | **TK**（另有 TK_HIBIKI2 变体） | **HC** |
| 平台代号 | SYSIPSX-DSLR | SYSIPSX-DSLR（同平台） |

## 1. SoC / 硬件平台

**两台相机 SoC 层面完全相同：**
- `cxd90057.dtb` 设备树 **MD5 一致**（16841 B）→ 同一颗 CXD90057（Bionz XR），内存映射、SPI/I2C 外设布局完全一致
- 编解码器固件 `codec/vcd_firmware_imola2.bin`（10.9MB，代号 imola2）**MD5 一致** → 视频编解码硬件相同
- 内核启动参数 kemco.txt 几乎相同，α1 II 仅多 `pcie.noaer1=1 pcie.noaer2=1`

## 2. 确凿的硬件差异（来自内核驱动 kmod/）

| 硬件 | α1 | α1 II | 证据 |
|---|---|---|---|
| **有线网卡** | Realtek RTL8168（**1GbE**） | Realtek RTL8125（**2.5GbE**） | `kmod/r8168.ko` → `kmod/r8125.ko` |
| **NFC** | **有** | **无（砍掉）** | α1 有 `kmod/nfc.ko` + `libInfraNfc.so`，α1 II 均无 |
| **蓝牙** | BLE | **增加 Bluetooth Classic + MFi** | α1 II 新增 `libInfraBluetoothClassic.so`、`libInfraMFi.so` |
| **AI 处理** | 无独立 AI 字典 | **AI 单元 + 40MB 神经网模型** | α1 II 新增 `data/ai_dict/default/default.nab`（40,047,760 B）+ `lib/libAiDictionary.so` |

其余 120 个内核模块两台完全一致。

## 3. 主体识别（AF）字典差异（sabin/）

- α1 II 新增 **scd_dic1/2/3.bin**（3 个新的主体分类字典）——对应"AI 主体识别"新主体类型
- α1 字典日期 2020-12-03；α1 II 为 **2025-07-02**（全系列更新）
- 更新的字典：`sa_sabin_cp_cam_post.bin`、`sa_sabin_cp_zima_post.bin`、`sa_sabin_mp_cam_post.bin`、`sa_sabin_mp_zima_post.bin`、`sa_zoom_nr.bin`

## 4. 新增软件功能（α1 II 独有）

| 功能 | 证据 |
|---|---|
| **RTMP 直播推流** | `libInfraRtmpLiveStreaming*.so`、`libPluginRtmpLiveStream.so`、`librtmp.so.0` |
| **SRT 直播推流** | `libInfraSrtLiveStreaming.so`、`libPluginSrtLiveStream.so`、`libsrt.so.1.4` |
| **完整 GStreamer 栈** | `libgstreamer-1.0.so.0` + audio/base/video/tag/pbutils/mpegts 全套 + gstplugin/ |
| **网络射频测试** | `libInfraNetRfTest.so` |
| **新固件升级程序** | `ud_leaf_firmup.elf`、`us_dualspi_firmup.sh`、`us_leaf_firmup.sh` 等 5 个新升级脚本 |
| 移除 | `libInfraError.so`（α1 独有） |

主程序框架 `lib/appFw.so`：α1 = 87.7MB → α1 II = **94.7MB**（+7MB，主要是 AI + 直播功能）。

## 5. 闪存分区布局差异（partinf.conf / mount.conf）

| 分区 | 用途 | α1 | α1 II |
|---|---|---|---|
| nflasha4 | MPR Flash Backup | 12MB | **0（裁掉）** |
| nflasha5 | Warm Boot Image | 300MB | **350MB** |
| nflasha11 | /log | 500MB | **250MB** |
| nflasha15 | /usr（主系统） | 500MB | **808MB** |
| nflasha16 | （raw） | 0 | **25MB（新增）** |
| nflasha22 | （User） | 0 | **45MB（新增）** |

其余分区（Updater 24MB、Setting 20MB、Main 75MB、Jiritsu 25MB、Rootfs 16MB、CP Data 64MB、tmp 12MB、cert 40MB、lens 20MB、Customer 64MB 等）完全相同。

## 6. 区域（销售地）配置文件

两边都提供全部 12 个销售地区变体（J1 日本 / UC2 美国 / E38 欧洲 / KR2 韩国 / **CN2 中国** / AP2 亚太 / CEC / AF1 / IN5 / JE3 / ALLLANG）：
- α1：`SYSIPSX-DSLR/TK/CX8850x_*.bin` + `TK_HIBIKI2/CH8850x_*.bin`（双目录，24 个文件）
- α1 II：`SYSIPSX-DSLR/HC/CX8990x_*.bin`（单目录，12 个文件）

α1 独有的 **TK_HIBIKI2** 变体在 α1 II 中消失（HIBIKI = 音频子系统代号，α1 II 可能整合了该变体）。

## 7. Bootloader

`0750_nor_loader/loader_nor.bin` 两台**不同**（NOR 启动加载器不同版本），pformat 配置相同。

## 8. 结论

1. **同一平台**：CXD90057 SoC + 相同编解码器 + 相同设备树 → α1 II 不是新平台，是同平台深挖。
2. **可确认的硬件升级**：2.5GbE 网卡（RTL8168→RTL8125）、蓝牙 Classic+MFi、独立 AI 处理单元（40MB 模型上机）。
3. **硬件降级**：NFC 被移除。
4. **软件新增**：RTMP/SRT 原生直播、完整 GStreamer 栈。
5. **α1 II 固件更大**的主因：/usr 分区 +308MB（AI 模型 40MB + GStreamer 栈 + 直播功能 + 更新的 AF 字典）。

## 9. 附：gen5 密钥（已实测验证）

索尼在 α1 的 V1.35 → V2.01 之间**更换过一次 gen5 密钥**，因此有两把：

| 密钥 | 值 | 实测可解 |
|---|---|---|
| `key_CXD90057CXD90058`（gen5 初代） | `376A61D907035CF18300F2ADD6503E649FCCF0C0191DCC38C3B05895150A7FB6` | α1 **V1.35** |
| `key_CXD90057CXD90058gen2` | `434589432D319010F1132727353286CE4D7EDE8B9C4F7217A0E0226E0F0EDC69` | α1 **V2.01 / V4.00**、α1 II **V4.00** |

加密结构：1024B 分块，每块 4B 块头（2B 校验和 + 2B 大小/结束标志）；首块前 512B 用 `key_aes` ECB（FDAT 头），其后全部用 gen5 密钥 CBC 连续链，IV 在 FDAT payload 尾部 `[-0x110:-0x100]`。
