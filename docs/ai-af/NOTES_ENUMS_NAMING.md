# NOTES_ENUMS_NAMING.md — 官方命名与次要枚举语义（收尾清单第 2 项，2026-10-11）

> 全部证据来自 α1 II V4.00 cpapp-b.bin 字符串/符号表与反编译交叉验证。X- 家族"X"字面展开在固件内
> 无字符串证据，本文只记录可证部分。

## 1. XED / XHD（Keypoint 后处理的双检测器家族）

**官方符号**（字符串表里的完整 C++ 签名）：
- `Camera::FC::Keypoint::KeypointXedResult` / `Camera::FC::Keypoint::KeypointXhdResult`
  （后者有 `getPrioFrame()` 等，见 REPORT_priority_judgment.md 断言串）
- `Camera::FC::AutoRecog::AutoRecogSameObjectJudger::XedXhdType`
- `Setting::ModePattern`、`Setting::XhdModePattern`（搜索模式枚举，AF_LOGIC.md §十五 的 ModePattern 0–25）
- `SearchPatternHelper::getModeInfo5SA(ModePattern, XhdModePattern, KeypointAdamExecInfo, SearchSettingEx&)`
- `SearchPatternResolver::getMasterPattern(ModePattern&, Extention&)`
- 驱动面：`Xed[nb:%d]Initialize/SetProcParamInit/SetCmdParam/GetResultInfo/GetResult`、
  `ERROR: XED CMD overflow(use=%d > max=%d)`（nb = NPU 块号，命令队列直发 Adam）

**职能分工（日志实证）**：
- **XED = 眼部检测**：`[XedResult] eye_L num:%d`；`xed_result[%d] el:%d,%d,er:%d,%d,s:%d`
  （左/右眼坐标+分数）；`XedResultSt[%d] class bg%d, mml:%d, brd:%d`
- **XHD = 人形头/躯干关键点检测**：`xhd_result[%d] t:%d,p:%d,f:%d %d %d %d,s:%d`；
  汇总行 `le:%d %d re:%d %d head:%d %d body:%d %d xed:%d xhd:%d high:…`（le/re/head/body 四组）；
  **XhdType ∈ 0..7**（`7 < type → "unkown xhd type(%d)"` 断言，FUN_002cd040）；人体部位子类
  0–4 = Eye/Head1/Head2/Body1/Body2（REPORT_priority_judgment.md §上表，animal_data.h 断言）
- 共同宿主目录 `process/post/xedxhd/`：error_eye_position_detector.cpp、recog_target_stabilizer.cpp、
  adam_callback_procedure.cpp、adam_result_maker.cpp、calculation_result_status.cpp、
  frame_selector.cpp、xed_result_invalidater.cpp
- 执行规格日志：`[ExecInfoCreator][Spec] ps:%d, adam_peak:%d, xed_f:%d, xhd_f:%d, xed:%d, xed_in_xedxhd:%d, xhd:%d, xhd_in_xedxhd:%d`

**结论**：XED/XHD 是 Adam(NPU) 检测器输出在 Keypoint 后处理的封装层（X- 家族还有 XAD/XRI）；
XED=眼（眼 AF 用），XHD=人形关键点/部位（主体识别与部位判定用）。"X" 缩写本义无字符串证据。

## 2. AED（眼部检测引擎，NPU S6）

- 模型：S6 `aed_03_00_05_rc2`（128×128×3，AF_LOGIC.md §二）；字典 `/usr/sabin/aed_dic1.bin`、
  `aed_dic2.bin`；二代 `Aed2Drv::initialize` + `/usr/sabin/aed2_dic1.bin`、`aed2_dic2.bin`、
  `aed2_dica_s2f.bin`、`aed2_dicb_s2f.bin`（s2f = score-to-flag 查表）
- 驱动：`AedDrv::initialize`（[TRK] 日志域）；显示眼位计算 `calcDisplayEye_AED__is_detect_vi…`、
  `calcDisplayEye_AED__touched_eye…`（process/post/aed_display_eye_cal.cpp；含左右眼归属
  `IDT::AttributeLeftRight`，FUN_00893a96 构造属性上下文）
- **AedConfidence ∈ {0,1,3}**：由 staple 判分阈值化（FUN_008973fa：
  `(t_c<=score)?3:(t8<=score)?1:0`，门限来自调参虚表）；二次校验
  `set SecondAedConfidence AED_CONFIDENCE_VERIFY(id=%d)`（FUN_00306xxx，
  不合格 → `id:%d set score to 0, valid to …` 清分）
- AED 校验失败 → 强制回退/重初始化（AF_LOGIC.md §十六：xed/xhd_confidence==0 或 AED 结果不正确 → StartInit）

## 3. FoundStatus（官方签名 + 枚举映射）

符号：`Camera::FC::Keypoint::FoundStatus Camera::FC::Keypoint::ResultCalculator::getFoundStatus(
Camera::FC::Keypoint::AedConfidence, Camera::FC::Keypoint::StapleConfidence)`
（process/post/result_calculator.cpp；打印 tag `"prio"`，见 REPORT_result_calc_frame_selector.md §1.11）

映射（反编译实证，§1.10）：
```
FoundStatus = (aed==3) ? 2 : (stpl==2) ? 3 : (aed==1) ? 1 : 0
```
| 值 | 含义 |
|---|---|
| 0 | 未确立（AED 低置信以下、staple 未稳态） |
| 1 | AedConfidence==1（低置信检出） |
| 2 | AedConfidence==3（高置信检出，XED 主导） |
| 3 | StapleConfidence==2（STAPLE 跟踪稳态） |

下游 result_converter 输出面：`xed:%d xhd:%d transfer:%d left_eye_pos_valid:%d right_eye_pos_valid:%d Visible:%d`。

## 4. 同批新确认的官方类型名（字符串表符号）

| 类型/函数 | 用途 |
|---|---|
| `Keypoint::KeypointPartType` | 部位枚举（0–4 = Eye/Head1/Head2/Body1/Body2） |
| `Keypoint::XhdType` | XHD 目标类别（0–7） |
| `Keypoint::DetectedTarget` | 检出目标（置信度门限按其分档） |
| `Keypoint::FirCalculatorType` | FIR 滞回计算器类别（ResultHysteresisCalculator::calculateFirFilter） |
| `Keypoint::AedConfidence` / `StapleConfidence` / `FoundStatus` | §2/§3 |
| `Api::RecognitionSensitivityMode` / `Api::TrackingSensitivityMode` | 识别/跟踪灵敏度档（门限 getter 通用尾参） |
| `TrackSettingProviderIF::RequestID` | 跟踪设置请求 ID |
| `Keypoint::(anonymous namespace)::LOCK_ON_RECTANGLE_JUDGE_TYPE` | isLockOnRectangle(SelectDfAreaInfo,u8,TYPE) 判定类型 |
| `AutoRecogSameObjectJudger::XedXhdType` | 同物体判定里的 XED/XHD 来源类型 |
| `TuningParamPostResult`（虚接口） | 全部阈值 getter 宿主：getFaceConfidenceMid/HighThreshold、getXhdConfidenceMid/HighThreshold、getXhdPartConfidenceMid/HighThreshold、getBetaRatioLower/UpperLimit(KeypointPartType)、getElapsedStapleCounterUsThreshold、getXhd(Slave)VerifyConfidence(Retry)Count、isCheckingResultByHistoryEnabled、getFirBufferClearExpireTimer |

这些类型名可反哺 REPORT_priority_judgment.md / REPORT_result_calc_frame_selector.md 中
"部位 ID 0–4"“XED/XHD 状态值"等表述的命名（该两报告的语义结论不变）。

## 5. Block A 新增（2026-10-11 晚，详见 REPORT_staple_reid_faceid.md）

| 名字/类型 | 语义 |
|---|---|
| `JdgStapleinit` 返回值 | 2/1=允许 init（字典版本新 + 时间窗口内），0=只 train/弃用 |
| HumanStaple part 状态 +0x24 | 2=有效继续训练，3=无效/弃用（train 路径只置位，滤波更新在 SA-IP 硬件） |
| `IDT::Staple::WINDOW_TYPE` | Hann 窗表选择枚举（0x400B/表，运行时 tuning 区） |
| `IDT::Staple::IDT_STAPLE_*` 虚接口 | DDL_MINNA staple 引擎访问面（fc_alg_staple_adjust） |
| ReID 相似度 u8 @tracklet+0x2288 | 0=与目标同，20=最大差异（fmin(dist−基线,0.2)×100） |
| `FRC_algo::swap_ID` | 人脸 ID 互换执行（judgeSwapFace_prio 通过后） |
| IDT 消息族 | FACE_INIT / BASE_SET / IMME / STOP_MON / STOP_ALL / STOP_IMME（+STOP_IMME@007ff85e） |
| FDT 结果表 | main 0x244B ≤36 脸 + branch 0x484B ≤72 脸（FDT 硬件 IRQ 直出） |
| 眼选 flash 阈值块 | 0x200B/块 ×7 mode @RAM 0x198bdde，{ra,rb,size_max,size_min,size_min_hard}，tuning 流式灌入（游标 DAT_011e8be8） |

## 6. Block B/C 日志前缀伪影修正（2026-10-11 深夜二批，重要）

**"pGFW"/"pGLC" 均为字符串/指令重叠伪影**：GCC 把日志串紧贴函数尾部放置，串首两字节
"pG"(0x70,0x47) 恰为 `bx lr` 返回指令——`strings` 提取出 "pGFW: …"，实际 printf 的 ADR
指向串+2，真实日志前缀：

| 伪影名 | 真实前缀 | 证据 |
|---|---|---|
| pGFW（196 条 SET_* 参数面） | **"FW: "** | decompile 199 条 `s_FW__SET_*`；0x37e45e 等全部首字节 7047 |
| pGLC / @pGLC（镜头 BL 日志） | **"LC: "** | 0x433166 等 +2 后 = "LC: Lens: [BL]..."，与无重叠的 "LC: Lens: mix_in..." 一致 |
| pGLENS_LC | **"LENS_LC"** | 同款（setPosOkFunc 串 +2） |

**含 "pG" 的日志前缀一律为 `bx lr` 重叠伪影；正名 = 去 "pG" 后的剩余部分**
（pGFW→FW、pGLC→LC、pGLENS_LC→LENS_LC；带 @ 前缀的 "@pGLC" → "@LC"？——@ 字节在串内
pG 之前，ADR+2 不含 @，@ 属前一串尾部，实际打印从 "LC" 起）。历史文档中 pGFW 表述按此更正
（AF_LOGIC §十七已改）。
