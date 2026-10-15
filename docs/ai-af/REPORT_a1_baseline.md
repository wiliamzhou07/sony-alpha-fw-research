# REPORT_a1_baseline.md — α1（ILCE-1）侧基线/落点面 ★Block C·a1 直接分析第一批★（2026-10-12）

> 背景：移植路线 = CP 侧换 α1 II 的 cpapp-b.bin，AP 侧留守 α1 的 appFw/avcam/kmod。
> 本报告回答"落点侧"问题：α1 现有 AP 栈的结构、它与 α1 II 的差异面、消息契约兼容性。
> 数据源：re_assets/a1（kmod 123 个/appFw.so/av-cam/cpapp-b.bin）、a1_appfw.c（172190 函数，
> 400k 上限重导 2026-10-12 完成）、a1_avcam.c、a1_cpapp.c（46MB）。

## 一、kmod 层共享图景（MD5 + .text 双级普查）

**MD5 层**：两台 kmod a1=123 / a1m2=122，相同 102、不同 19、独有 a1={nfc.ko, r8168.ko}、
独有 a1m2={r8125.ko}（全是已知硬件差异：α1 II 砍 NFC、网卡 1G→2.5G）。

**.text 层**（19 个 MD5 不同的 kmod 逐一抽 .text 比对）：

| 结论 | kmod |
|---|---|
| **代码逐字节一致（12）** | backup, cachecontrol, codec_drv, **icdt**, indctr, ioexp, **mcmn_drv**, **osal_uipc**, **osal_ulogio**, udate, usb_buspwr, usb_portMonitor |
| 代码有变（7） | **pcie-if**（+968B，API 重构：a1=pcieif_dma_execute/_multi → a1m2=pcieif_dma_set_lli+pcieif_start_dma）、**upm**（-14224B 大砍）、usb_beets(+920B)、dmm(+104B)、input(+144B)、kikilog(+8B)、wlanIrq(2B) |

★结论修正/强化（B7）★：芯片间传输核心四件（icdt/mcmn_drv/osal_uipc/osal_ulogio）
**代码级逐字节一致**（MD5 差异纯 build-id/vermagic 元数据）——"传输层两台同版"从用户态桩
升级为**内核态代码级实证**。真正变的集中在 PCIe DMA 驱动路径（pcie-if，且是 α1 II 重构）、
DMM、USB 电源管理——对"换 cpapp"路线无直接威胁（cpapp 走 UIPC 邮箱语义，不触碰 pcie-if API）。

## 二、appFw 属性注册表差分 ★移植风险面主发现★

提取方式同 C-2（`FUN(&DAT, id, "PID_SET_*"/"NID_*")` 注册调用全量）：
- a1：**547 条**（PID 342 + NID 205），注册函数族 FUN_02fde280-02fe18cc（36 个）
- a1m2：**585 条**（PID 370 + NID 215）——与 C-2 复核一致
- 产物：`a1_appfw_pid_nid_registry.tsv`（548 行）、`a1_a1m2_pid_nid_diff.tsv`（67 行）

### 2.1 差分三事实

1. **仅 a1（7 条）**：0x4152-0x4158 PRESET_FOCUS_ZOOM_POS/PRESET_FOCUS_ZOOM/REMOTE_ZOOM/
   REMOTE_FOCUS/FLASH_SHUT_SPEED/ENABLE|DISABLE_SEND_KEY_INFRA_REMOTE——α1 II cpapp 不会
   发送（其同名功能已改用 0x414e/0x416d/0x416e 等**新号**），低风险。
2. **仅 a1m2（45 条）**：TIMESHIFT 四通知、EFRAMING、BREATHING_CORRECTION、
   DEFOCUS_CONTROL_POSITION(0x4161)、BACKGROUND_DEFOCUS_CUSTOMIZE、FOLLOW_FOCUS 族、
   DETECTION_SETTING(0x415f)、GET_DISPLAY_POSITION(0x4160)、BOOST_SHOOTING、
   PRELIGHTING、ANAMO_DESQUEEZE、MOVIE_LETTER_BOX、ISCN_LOCK、EXPOSURE_POINT 等——
   **α1 appFw 无此注册：α1 II cpapp 发出即被丢弃/未知**。其中 AI 对焦相关：
   SET_DETECTION_SETTING（主体检测设置！）、GET_DISPLAY_POSITION、FOLLOW_FOCUS 族
   为移植必须补齐的 AP 侧消费点。
3. **ID 重编号冲突（13 条）★**：两代固件复用同号不同义——NID 0x20a4-0x20ae 全族错位
   （如 0x20a9：a1=PRESET_FOCUS_ZOOM_POSITION vs a1m2=EXPAND_FOCUS_CANCEL）+
   PID 0x414e（a1=MF_DRIVE_IN_MOVIE_AF vs a1m2=PRESET_FOCUS_ZOOM_POS）、0x4152-0x4155。
   **换 cpapp 时这些号必须做 ID 映射层，否则参数静默错位**。

## 三、avcam mcMsgIf 分派枢纽同构核对（C-3 的 a1 版）

a1 枢纽 = **FUN_ffffffc0010a01dc**（9233B/287 行，a1m2 版 FUN_ffffffc0010a1ef4 9488B/295 行）：

| 维度 | a1 | a1m2 | 结论 |
|---|---|---|---|
| 源地址集 | 0x61003c/0x9061003c/0x7302f0/0x80c2019f/0xc20219/0x8057026d/0x80570529/0x810b0768/0x818c04d5 | 同 + **0xd2fc0991**（a1 全二进制无此串） | 9/10 相同；α1 II 新增一个源端点 |
| 消息首字 | 0x1000 RPC / 0x2003 codec / 0x200d / 0x2103 六路广播 / 0x8003 系统 | 同 | **逐分支同构** |
| word1 子类型 | 0x1303/0x201/0x501 | 同 | 同 |
| 分支体 | ExecMsg 4 项范围表、错误发送 0xe/0xf、HW 版本握手 0x153 | 同（行号级对应） | 同一代码系的两次编译 |

→ **avcam 消息契约跨代稳定**（除一个新增源端点），AP 侧留守 avcam 可承接 α1 II cpapp
的 codec/显示族消息。

## 四、cpapp FW 层锚点核对

a1_cpapp.c（α1 V4.00 世代）中全部关键锚点在位：
- **LiroSeq 序列器**：22 处（ParamCheckErr+CheckSetZoomDrive@0x30b870 族；a1m2 同族在
  0x387378——同构不同址）
- **setMoveFcCmd**：6 处；**FC 队列 0x90060197**：7 处；**ALH 家族**（lensAttach/
  updImageZ/M/lensDetach）齐备
- FW 状态块基址不同（a1m2=0x1502ec8；a1 候选区 0x1501xxx，未逐字节标定，非阻塞）

→ **两代 CP 固件同构**（LiroSeq 电源/参数/AF 三序列 + ALH + FC 队列 + ParamCheck 机制全同），
α1 II cpapp 是 α1 cpapp 的同架构演进——支持"整体替换 cpapp-b.bin"的路线前提。

## 五、对移植路线的意义（汇总）

1. **传输层无障碍**：UDIF 核心 kmod 代码级一致，用户态桩逐字节同——跨芯片通信不用动。
2. **avcam 契约稳定**：分派枢纽逐分支同构，α1 II cpapp 的 codec/显示消息可被 α1 avcam 接住
   （α1 II 多出的一个源端点 0xd2fc0991 需确认发送方语义，若为新功能通知可容忍丢包）。
3. **appFw 属性面是主要适配工作**：45 个 α1m2 独有 PID/NID 已分级（见 §2.2）；
   **13 个 ID 冲突必须做映射表**（diff.tsv 已备）。

### 2.2 45 条 α1m2 独有 PID/NID 移植分级（2026-10-12 续批，已写回 diff.tsv level 列）

**关键修正**：45 条中 41 条在 a1m2_cpapp.c **零立即数引用**（唯一活跃：NID_TIMESHIFT 族
3-16 处）——立即数统计为下界（PID 描述符表是数据），但结合"appFw 注册 = appFw 侧功能"
判断：多数由 appFw 菜单/内部发起，**换 cpapp 后 α1 菜单无入口 → 天然休眠**。
45 条中 35 条在 CP 侧 358 注册表内（共享命名空间成员），10 条 NID 仅 AP 注册。

| 级 | 数量 | 处置 |
|---|---|---|
| **A：AI 对焦/检测族** | **12** | 换 cpapp 时须在 α1 appFw 补注册或确认降级：SET_DETECTION_SETTING(0x415f)/SET_DETECTION_AUTO_TARGET(0x4180)/GET_DISPLAY_POSITION(0x4160,appfw 61 引用)/SET_DEFOCUS_CONTROL_POSITION(0x4161)/SET_BACKGROUND_DEFOCUS_CUSTOMIZE(0x4162)/FOLLOW_FOCUS(0x416b)/FOLLOW_ASSIST_LOCK(0x416c)/SET_AF_SPEED_SENSIBILITY(0x417b)/SET_MF_DRIVE_IN_STILL_AF(0x415b)/SET_BREATHING_CORRECTION(0x414c)/SET_ISCN_LOCK_MODE(0x4167)/NID_EFRAMING_FOLLOW_ASSIST_STATUS(0x20ad) |
| **B：镜头/对焦辅助** | 8 | 同上次之：GET_LENS_POS_INFO/PRESET_FOCUS_ZOOM(+3 NID)/REMOTE_ZOOM/REMOTE_FOCUS/LENS_2G_DIST_DATA |
| **C：α1 II 新拍摄功能** | 21 | 休眠低风险：BOOST×2/TIMESHIFT×6（CP 有活跃引用但 α1 菜单无入口）/TIMELAPSE/COMPUTATIONAL_RAW/SYNCHRO/PRELIGHTING/EXPOSURE_POINT/FLASH 族/SILENT_MODE/STEP_CROP 等 |
| **D：显示/视频族** | 4 | appFw 内部消费为主：ANAMO_DESQUEEZE(27 引用)/MOVIE_LETTER_BOX/EFRAMING/AUTO_CUSTOMIZE_EE |

**机制注记**：PID 属性调用跨芯片发起方向 = CP→AP 与 AP→CP 双向都有；换 cpapp 的真实
风险面 = **CP 主动发起的那些**。A 级 12 条中 GET_DISPLAY_POSITION 有 cpapp 侧
"FW: PID_GET_DISPLAY_POSITION" 日志实证（CP FW 层活跃），其余多数疑似 AP 菜单发起
（休眠）。逐条发起方验证留待换 cpapp 联调（静态只能到"CP 描述符存在"这一层）。
4. α1 appFw 完整导出（172190 函数）已就绪，函数级差分可随时跑（无需等 a1m2 重导）。

## 七、appFw 函数级差分·第一遍（2026-10-12 凌晨，a1m2 400k 重导完成后）

全量重导：a1=172190 函数导出（文件内 168538 个非空）/a1m2=**179292 函数/135.5MB**。
第一遍结构差（appfw_func_diff_pass1.txt）：

| 维度 | a1 | a1m2 | 差 |
|---|---|---|---|
| 函数数 | 168538 | 175481 | **+6943** |
| 字符串 | 10425 | 10974 | +549（a1m2 新 922 / a1 独 373） |
| cpp 源文件 | 872 | 909 | +49 a1m2 新 / 11 a1 独 |

**a1m2 新增 49 个 cpp 的构成**：
- **`infra_wrapper_aidictionary.cpp` ★** —— AP 侧 AI 词典封装（α1 appFw 完全没有）。
  adam_app 仅 a1m2 有（system/），AI 单元的 AP 侧接口面在新 appFw 里。
- 连接域重构 ~35 个：PC Remote 全家（pairing/wifi/usb/wired lan，`*_re_arch` 后缀=
  重构版）、Bluetooth Classic、MFI、云连接、流媒体状态 PTP 事件、FTP/RTMPS 证书、
  SDI1/SDI2/HDMI——CT_ID_* 串族（922 新串的主体）与此对应
- 创作者功能：clip flag 拆 4 变体、zebra、raw-only 录制、屏幕控制器 scr7078/7181/7258

**★对移植路线的结构性约束（本遍最大发现）★**：AI 功能的 AP 侧入口（aidictionary 封装+
新屏幕控制器）**只存在于 α1 II 的 appFw**。α1 appFw 既无此封装也无 AI 菜单 →
"AP 侧完全不动"的说法要修正为：**AI 对焦的开关/配置无法经 α1 原装 UI 下发**，
只能靠 (a) CP 侧默认值/自启逻辑，(b) α1 已有菜单项映射到新 PID（如 AF 主体检测
既有入口），或 (c) 调试通道（senser/文本调试台——但国行锁死）。A 级 12 条 PID 的
真实含义随之清晰：**其中 CP 主动 GET/SET 的必须保证 α1 appFw 应答不崩**（属性缺失
的容错行为要逆向确认），AP 菜单发起的部分天然不存在。

连接域重构与移植无关（α1 II 新网络硬件/功能），但解释了 +6943 函数的绝大部分——
**真正 AI 相关的 appFw 增量远小于表面数字**。

## 六、遗留

1. a1/a1m2 appFw 函数级差分（建议先跑同名函数签名/字符串差，再对 AI 相关子系统精对）。
2. 0xd2fc0991 源端点的发送方定位（a1m2 cpapp 内 grep）。
3. a1 FW 状态块基址标定 + a1 CP 侧 PID 注册表（358 条版的 a1 对应物）提取。
4. 45 条 a1m2 独有 PID 的逐条分级（哪些 AI 对焦必需 / 哪些可降级）。
