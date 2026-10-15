# REPORT_cp_fw_af_execution.md — CP FW 执行层 / AF 控制环（Block B 第一批，2026-10-11）

> 数据源：a1m2_cpapp.c + copro/cpapp-b.bin + re_assets kmod 符号表。
> 覆盖 B1（AF 主循环/镜头控制）、B6 修正（liro.ko 身份）、B5 部分（PID 注册表）、
> **B2（投递方闭环，§四）、B3（PDAF/ZPD-DFE-Mario + nflasha18 校准流，§五）、
> B4（AE/AWB 模块面，§六）、C-4（LiroSeq AF 序列本体，§九）**。遗留见 §八。

## 一、FW 层身份与 PID 面（B5 部分）

- FW 层日志前缀 **"pGFW: "**：全二进制 196 条，覆盖 AF/AE/AWB/闪光/事件全部参数族
  （PID_SET_EYE_AF_MODE、PID_SET_EYE_SELECT_MODE、PID_SET_TRACKING_EYE_SELECT_MODE、
  PID_SET_MOVIE_EYE_AF、SET_EYE_START_AF、SET_FACE_AF_MODE、SET_FOCAL_PLANE*、
  SET_AF_RANGE_LIMIT、SET_AF_DRIVE_SPEED、SET_DEFOCUS_CONTROL、SET_BACKGROUND_DEFOCUS_MODE、
  AfSpeedSensibity、FOCUS_RANGE_LIMITER…）。清单：
  `gunzip -c firmware_reverse/strings_corpus/a1m2_cpapp-b.bin.strings.txt.gz | grep pGFW`
- **PID 描述符表已定位**（a1m2）：RAM 0x11eb02c–0x11ecc10，**358 条 × 20B，pid 单调
  0x4000→0x4182**，记录 = `{w0, fn1, PID, fn2, w4}`（两个代码指针 + 属性字），
  全表已导出 `a1m2_ai_pipeline/fw_pid_registry.tsv`（pid→handler 函数映射）。
  注：handler 指针多为函数中部地址；Ghidra 对该区按代码切分不准，精确的
  "pid 名 ↔ handler" 对齐需 Ghidra 内以数据模式重解释该区（遗留）。
- **引用机制注记**：pGFW 串几乎全部**不被** literal pool / movw-movt 直接引用
  （scan_movw_movt.py + 池扫描双阴性）；观察到的规律 = 每条 pGFW 串紧邻其 handler 代码
  前后放置（如 SET_EYE_START_AF 串@0x3803da 与表内 handler 指针 0x3803f9 相距 0x1f）。
  已固化工具：`a1m2_ai_pipeline/scan_movw_movt.py`（ARM/Thumb 双编码 movw+movt 对扫描）。
- **A5 眼选 mode 补全**：PID_SET_EYE_SELECT_MODE 与 PID_SET_TRACKING_EYE_SELECT_MODE
  两条 PID 都存在——眼选模式由 FW 层 SET 下发，候选+0xC8 的来源即此。

## 二、镜头控制模块 LENS_LC（B1 主体）★已定位到函数级★

`Camera::FC::(FW) LENS_LC`（0x427948–0x42c2xx + 0xae3e28-0xae6558 尾部助手）：

| 函数 | 大小 | 职能（字符串实证） |
|---|---|---|
| FUN_00427948 | 14730B | **JobDispatcher_Entry**：任务主循环，switch(param_2) 分发子命令（case 2=updImage→FUN_00427b08，case 3=addMoveFc→FUN_0042846c，case 4=…）；SYS_EVENT_START 触发 |
| FUN_00427b08 | 3284B | updImage：图像位置/变焦状态更新（ALH_updImageM_D/E/S、ALH_updImageZ_D/E/S 日志族） |
| FUN_0042846c | 4158B | **addMoveFcCmd**：对焦移动命令入队（命令类型 'C'/'\x1d' 校验，ALH_addMoveFc_S/E 日志，资源 FUN_00644328/FUN_00638a38 分配，失败码 0xffffffd7/-9/-0x12 族） |
| FUN_00428798 | 2835B | **calcMoveFcStartTime**：对焦移动起始时刻计算，**此处打印 pGFW: SET_DEFOCUS_CONTROL**——背景虚化联动影响移动启动时序 |
| FUN_00428a1c | 13356B | **predictFcPos（递归）**：预测性对焦位置（ALH_predictPos_S/E），LENS_LC 的运动学核心 |
| FUN_004291bc | 3118B | addLensPos（镜头位置历史入队） |
| FUN_0042a8b4 | 6119B | shut_cycle 断言/镜头行程管理 |
| FUN_0042bf2c | 2987B | procExpCogCalcEnd（曝光 cog/ECOG 计算，ALH_ecogOK） |
| FUN_00ae3e28/00ae422e/00ae600a | ~1KB | alloc_or_recycle（历史缓冲分配回收） |
| FUN_00ae5668/00ae6558 | 5.4/2.6KB | convCamVTime2FRC（相机时间→FRC 时间基转换）+ getEcogData |
| FUN_00ae6536 | 1.6KB | calcExposureEndPos（曝光结束位置预测） |
| FUN_00ae6526 | 815B | getLensHistoryData |

**队列/任务模型**：LENS_LC 以 `DAT_01564a10` 为任务上下文（0x8cae8 步长大结构 = 历史/命令区），
经 SYS_EVENT_START 启动；命令从消息队列进入 JobDispatcher。**上游投递方（谁调 addMoveFc/
updImage 的消息发送侧）尚未定位** —— 这是 B2（0x170B→镜头动作闭环）的最后一环（遗留）。

## 三、liro.ko 身份修正（B6）★推翻旧论断★

**liro.ko ≠ 镜头 I/O 驱动。nm 实证（330 符号，未剥）：liro.ko = ITRON/T-Kernel RTOS
模拟层**——`CRE_TSK/CRE_SEM/CRE_FLG/CRE_MBX/CRE_MBF/CRE_MPF/CRE_MPL/CRE_CYC/CRE_ALM`、
`acre_*`、`act_tsk/chg_pri/wup_tsk/can_*`、`Vcur_cpu/Vset_cpu/Vspin_*`、buddy 分配器、
cache_flush/inv_range —— 与 adam_app 的 "SMP T-Kernel" 同族（Etools-LIRO = 索尼的
Linux 内核内 ITRON 兼容运行时）。

**修正后的镜头驱动链**：CP FW 的 AF 序列（LiroSeq = LIRO 上的 **任务/序列代码**，
非数据表）经 UDIF 投到 AP；AP 内核由 liro.ko 提供任务执行环境。镜头 I/O 本体（对焦马
达/光圈序列的最终驱动）不在 kmod（无 lens/focus 命名模块）——由 LIRO 任务经 **UDIF
总线（icdt/pci_ep_cp/mcmn_drv）** 回写 CP 或直接操作外设，具体寄存器面属 LIRO 任务
体（在 vmlinux 或 CP 内，遗留）。

## 四、B2 上游投递方闭环 ★已解★（2026-10-11 深夜第二批）

> 方法：JobDispatcher（FUN_00427948）直接调用者反查 + 全二进制 BL/ADR/movw-movt/指针四路扫描
> （Ghidra 反编译漏掉了 FUN_004520a8 等调用者，BL 扫描补齐）。

**LENS_LC JobDispatcher（FUN_00427948，任务入口）的投递方（直接调用者，全部同步直调）：**

| 投递方 | 命令 | 机制 |
|---|---|---|
| **FUN_00428324 = `LC::Lens::onMoveFcCmdIssued`**（断言串实证） | cmd3 (addMoveFc) | 命令拷入 4 槽环形缓冲（步长 0x110 @ 0x15f3790，槽轮转 DAT_01a00371 & 3，payload ≤0x100B）→ `FUN_00427948(ctx,3,2,slot)` |
| **FUN_00ae51de**（setLensInfo 投递） | cmd6 | 镜头信息 6 字 + 有效标志(+0x18=1)写入条目，记录 _DAT_018d8394 → `FUN_00427948(ctx,6,2)` |

**onMoveFcCmdIssued 的上游（两路汇入）：**
1. **FUN_0043242c = `LC::Lens::mix_in`**（模块串 `LC: Lens: mix_in() returns error`、
   `Mount_AM_DEQ_CmdData() returns Null:LC vsync[2]`）：每 LC vsync 从 Mount_AM 命令环
   （锁 DAT_0121ae88，环 DAT_0121aea4，14B/条：1B 命令 + 14B 数据）出队，转发 5B/0xcB 两种
   命令。**全二进制零引用（BL/B/ADR/movw/指针全无）→ 运行时注册的 LIRO 周期任务/vsync 回调**
   （与 JobDispatcher 同为任务入口特征）。
2. **FUN_004520a8 = `LIF::BL_ASYNC`**（串 `LIF:: BL_ASYNC_QUE_OVERFLOW`；**Ghidra 反编译未
   收录其调用，BL 扫描发现**）：字母编码镜头命令（0x41-0x61，命令属性表 @DAT_00d80c80）
   直接入 onMoveFcCmdIssued。LIF 发送 API = FUN_00451f14（19 个调用者：
   LC::Lens Send_Pos_Cycle/move_fc_rejected、**LENS_EC::B2L_SWITCH_IRIS**、
   LIF::BL_CommState_LensState/ErrCntQueSync 等）。

**setLensInfo 投递方的上游（镜头信息回流）：**
FUN_004339e0（LB:INFO2 镜头信息处理器）← FUN_00403730 = `drv::UpdateLensData`
（串 `s_drv_UpdateLensData`/`s_drv_AlreadyLatched`，先 FUN_00a3b1ec(3,0x400a12,0) 记 PID 轨迹）
← FUN_00a7435c（任务入口，唯一 BL 调用者）。

**PID 0x400a12 注记**：FUN_00a3b1ec 记录的 PID 族（0x400a12/0x3124612/0x3134612）为复合 ID
（模块前缀 0x40/0x31 + 子命令），**不在** 0x4000-0x4182 的 pGFW PID 注册表内——两套 PID 命名空间。

**0x170B 包传输层确认**：result_sender（FUN_0089a694）分配 0x170B 缓冲（**0x170B = 0x170 字节
Buffer**，FUN_00852f78 = fc_lib_message.cpp 池分配，池/队列 ID **0x90060197**），FUN_0085307c 发送
（osal_snd_msg → UIPC，队列号 0x0197）。同队列还承载 0xc80（AdamProcessManager）/0xd80
（FeatureScalar oneshot）等 FC 内部消息；SendCompMsg/WaitCompMsg（FUN_002bf008/002bf0b4）=
完成端口对。**FW 层归属确认：a1m2_appfw.c（AP 侧 98420 函数）零 pGFW/LiroSeq/Lens 命中 →
FW AF 序列(LiroSeq)/LC::Lens/LENS_LC 全部 CP 驻留（cpapp），§十七"CP 内闭环"成立。**

**完整投递链（自上而下）**：
```
FC::Keypoint result_sender ──0x170B(0x170B buf)──▶ FC 消息队列 0x90060197 ──▶ FW AF 序列(LiroSeq, CP)
LiroSeq 决策 ──▶ LIF BL 命令层(FUN_00451f14, 字母命令 19 调用方)
   ├─ LIF::BL_ASYNC(FUN_004520a8) ──────────────▶ onMoveFcCmdIssued
   └─ Mount_AM 命令环(0x15f3790 前置 14B 环) ─▶ mix_in(每 vsync) ─▶ onMoveFcCmdIssued
onMoveFcCmdIssued(FUN_00428324, 4 槽环 0x15f3790) ─▶ JobDispatcher cmd3 ─▶ addMoveFcCmd(FUN_0042846c)
镜头 INFO2 回报 ─▶ drv::UpdateLensData(FUN_00403730) ─▶ FUN_004339e0 ─▶ FUN_00ae51de ─▶ JobDispatcher cmd6
```
BL 命令命名空间（cpapp 内实证）：ID_BL_CMD_MOVE_FC_2 / ID_BL_CMD_MOVE_FC_CAP2 /
ID_BL_CMD_POS_CYCLE_A / ID_BL_CMD_FC_DRIVE_CYCLE；日志标签 BL:MOVE_FC(A)/LB:FC_POS_PER_A/
LB:MOVE_FC_A/LB:INFO2；FW 层镜头侧日志前缀 **pGLC**（`@pGLC: Lens: [BL]...`）。

## 五、B3 PDAF ★已解(接口面/数据流)★（2026-10-11 深夜第二批）

### 5.1 FW 层 setter（焦平面相位检测参数）

- LiroSeq 参数检查函数 **`CheckSetFocalPlanePhaseDetection`**（串 0x38c51e；ParamCheckErr
  `[set_focal_plane_phase_detection] cur:%d req:%d`）。
- FW: handler 族规律解码（0x37e-0x386 区，Ghidra 未分块，capstone 直读）：每 handler =
  `ldrb param,[cmd+8]` → `str.w param,[0x1502ec8+off]`（FW 状态块顺序参数槽）→
  调试位(DAT_019386ac+0x32)条件日志 → `movs r0,#1; bx lr`。
  **SET_FOCAL_PLANE_PHASE_DETECTION → RAM 0x1503790**（相邻：SET_AF_RANGE_LIMIT→0x1503794、
  SET_AF_RANGE_LIMIT_DRIVE→0x1503798）。
- ★前缀修正★：**"pGFW" 是解析伪影**——全部 196 条字符串的首两字节 "pG"(0x70,0x47) 与函数
  尾部 `bx lr` 指令重叠放置（编译器字符串/指令重叠优化）；真实日志前缀 = **"FW: "**。
  反编译实证 199 条 `s_FW__SET_*` vs 仅 2 处 pGFW 残留。**项目文档中 "pGFW" 应更正为 "FW:"**。

### 5.2 ZPD→DFE→Mario 散焦引擎全栈（RTTI 实证，N6Camera7* 类型名）

```
传感器 PDAF 硬件(双像素/掩蔽像素对)
  mtg_set_zpd_onoff / mtg_set_zpd_syn_param[finv,period,async,win] / mtg_set_zpd_syn_hs_param
  mtg_set_zpd_cdc_chgtm / mtg_set_zpd_cdc_param[sel,offset,over1v]   ← CDC=电荷域比较器时序
  pbl_clkctl_zpd::[ip][sclk_zpdx][sclk_zpdz]                          ← ZPD 时钟域
    ↓
CamCore 预处理: ZpdController(IntStart/IntEnd/Stop/SetParam) / ZpdPre(setEye/setAddEye eyeBitPtn,
  startZafLadd, LaddRegion/FirstLineOffset, read_hs_cycle 无缝切换) / ZpdAif(Extent/memsize 校验)
  IifZpd(writeIifZpdZafTable SGC) / ExlWrapper::writeZpdPreSgcTable / ZpdPreInterruption(回调注册)
  ZpdDcSetter(setEyePtnOffset A/B, setPupilNum —— 瞳孔分割 PDAF 眼图配置)
    ↓
DFECore 硬件引擎(全部 Getter/Setter 寄存器面对):
  Ifmt{TestGif,Gif,Emb,Ps,Dec} → Det{Buf,Pg,Opbfk,H3,Rpo} →
  Corr{MarioPg,MarioPga,MarioDc,MarioRpo, Pg,Clp,Pga,Dfi,Tdl,Dl,Ddx,Pls,Tzr,Dcm,Rpo} →
  Cow{Dec,Dcm} / Img{TopDclWbIwbOfst,SdcDfiMro,Dwc(+Coef)}
  驱动参数 dump: CSDrvParamDfe/CamcoreDrvParamDfe/CamcoreDrvFrameParamDfe/CamcoreDrvFrameZafParamDfe/
  LCDrvParamDfe/LCZafDrvParamDfe/otherParam{DfeSystemDelay,isNeedFclrMask,isDfeDrvParamAvailable}
  缺陷校正: HeadDdxSetter::loadDefectPos → DMA330 → DDX SRAM; IMG:ExecZpdDefectCorrection
  流水资源: CapRsrc_DFECORE / DFE_STORE_TRANS0 / DFE_TRANS1 / Stage_UnlockSyncRes_DFETRANS_END
  "FW: ReadExecuteBase[DRIVE INFO] IMG%x DFE%x CAM%x CLV%x FOPD%x ZPD%x"
    ↓
LC 层: LC:ZpdDetStart / LC_get_zpd_det_info / SetZpdDrvPrm / LC:GetZpdPrePrm /
  ZpdMarioSequenceData{SetRecognitionData,SetAllRecognitionDataNoWait,RejectRecognitionProcess}
  zpd_{ClearMotionPredictRecord,SetMotionPredictNg,RestoreMotionPredictResultData,
  ClearHistoryIfAlongTheWallorFloor} / CalcBigDfDriveRawTarget / LcZpdResultInfo / SetZpdResult/CopyZpdData
  **LC::MarioAfcState 状态机**: Nop/MoveToPeak/Wait/Locked/Approach/Tracking/Scan/Search/Stop
    ↓ (FW: LC isZpdPreEnable / zpdpreDriveInfo / "LC->DFE StartParam")
FC 层: FC_Sync{Zpd,ZpdImpl,ZpdProxy} / Alg::ZpdInfoManager(initialize) /
  Alg::DefocusInfoGenerator(IFE) / Alg::DefocusInfoTranslator(IFE)(zpd_area_num/zpd_max/select_area,
  is_lockon) / SegZpdData::WriteDataToMem(ZpdSensorInfo*, LC::LcZpdResultInfo*) /
  FunctionZpdWholeDetection(整幅 ZPD 检测) / fc_alg_zpd_area_position_converter.cpp /
  zpd_coordinate_convert_judger.cpp / src/defocus_calculator.cpp
  消费方: [AfSelectPos]getLcZpdResultInfo / [DefocusFace]/[DefocusKeypoint] 判定族(JudgeMatchFaceDf,
  JudgeFaceInfocus VGA defocus_th, JudgeSmallFaceInfocus mario_small_df, JudgeUsingBeta) /
  SearchModeSwitcher is_zpd_valid / TrackletUpdater::zpdResultValidateForTrack(mario ng) /
  MarioAlignSearchRegionGenerator / Exif Makernote "Mario Debug Data"
```
散焦量算法本体（DFECore 硬件+defocus_calculator）属寄存器/微架构级——接口面如上，
重建数值算法需 DFE 硬件手册级逆向（同 NPU 结论：非移植必要）。

### 5.3 nflasha18（/lens）校准数据流

- 分区用途（FIRMWARE_BLOCK_MAP/DRIVER_HARDWARE_MAP 已有）：/lens 20MB = **按镜头的补偿/特性数据**。
- **镜头名匹配器（cpapp 0x564334，Ghidra 漏块，capstone 解出）**：16 字节镜头名（挂载时镜头
  上报）先与内置 **`fixed_lensfile`**（0x56449c，16B 记录）比对 → 命中则用内置数据（r1=
  0x383b03+0xc0000 路径）；未命中则遍历镜头数据库表（[r8+4]，条目 16B 名+扩展记录，stride
  0x10）→ 得到该镜头专属记录指针。
- **提交点**：镜头 attach 处理 FUN_00be827a（`param_2`=镜头数据块 0xbc-0x134 能力字全部拷入
  LC 镜头上下文；+0x1c 标志触发 FUN_0056477c→匹配器；+4==2 时 thunk_FUN_00b2e99e 提交）。
- **消费点**：匹配到的记录经 DFECore Corr*/DDX 表面加载进硬件（CorrMarioPg/Pga/Dc/Rpo 等
  Setter + loadDefectPos DMA）。**即：/lens 校准数据 → 镜头名匹配 → DFE 修正表/缺陷表 → ZPD 散焦量**。
- 注：`fixed_lensfile` 字符串在 0xf4c548 有第二引用（未定位函数体，同族文件路径逻辑）。

## 六、B4 CP 内 AE/AWB 管线模块图 ★已解(模块面)★（2026-10-11 深夜第二批）

### 7.1 EC = Exposure Control 模块（cpapp 内 ~80 源文件，路径串实证）

**AE 计算核心**：CaptureRaw/EC_CaptureRaw_CalcAe.cpp、EC_CaptureRaw_CalcExpose.cpp、
EC_CaptureRaw_CaIf.cpp（CamCore 接口）、EC_AESchedule.cpp、EC_AgcDrv.cpp、EC_Histogram.cpp、
EC_ContCal.cpp / EC_ContLevel.cpp / EC_ContAllot_{Cam,Dsc,ProCam}.cpp（控制量三态分发）、
Mode/EC_StateMachine.cpp（AE 状态机）、Mode/EC_AutoBB.cpp（AutoBB=自动背光补偿/亮度基准）、
Mode/EC_Lock.cpp（AE 锁）、EC_Manual.cpp（M 挡）、EC_Ref.cpp（基准曝光）、EC_Gamma.cpp、
EC_CalcCaptureGamma / CalcGammaIsoStd（job_EC_*）

**快门/光圈/ND 执行**：EC_ElecShutter_Main.cpp、EC_CurtainSpeedAdj.cpp、
EC_NonlinearElecShutter_MechShutterTable.cpp（电子快门非线性+机械快门表）、
EC_IrisAutoManualController.cpp、Lens_{CommonIrisNDMK,IrisInitStepper_Cam,IrisMKGetBear3_Cam}.cpp、
ND_Cam/EC_NDAdj_Cam.cpp、job_EC_move_iris / job_EC_Cont2ShutSpd_Dsc

**联动接口**：EC_DetectGetIDT.cpp/EC_DetectSetIDT.cpp + job_EC_GetIDT_HighResDet（**IDT 人脸检测
硬件联动 = 面部优先 AE**）、EC_MainObject.cpp（主主体联动）、EC_GetExtInfoFromAPP/Strobe
（闪光灯集成）、EC_PqdWrapper.cpp + job_PQD_senser_copy_bkshadow、
EC_CaptureDevPrelight{,PreCalc,WL}（预闪光/预拍摄）、EC_MkAdj_DSC/EC_MakerNoteCA（EXIF Markernote）、
EC_BackupDmnAPI（BkDmn 备份守护）、FixedLens/ 分支（固定镜头机身变体）。

**FW: SET 参数面（AE/AWB/闪光族，cpapp 全 144 条 FW: SET_*）**：SET_SPOT_METER_FOCUS、
SET_TOUCH_SPOT_METER、SET_AE_METER_MODE、SET_AE_LEVEL_OFFSET、SET_MANUAL_EXPOSURE_DRIVE、
SET_EXPOSURE_BIAS、SET_EXPOSURE_POINT、SET_EXPOSURE_CANCEL、SET_ISO_SPEED_RATE(BaseSens/EIValue)、
SET_IRIS_DRIVE、SET_SHUT_DRIVE(drv/sum/typ/m/c/abs/f)、SET_FACE_AE_MODE、
SET_CAP_AE_SMOOTHING、SET_INTERVAL_REC_AE_SMOOTHING_END、SET_SET_STANDARD_EXPOSURE_STEP/SHIDT_*、
SET_WB_MODE(6+8 参两版)、SET_WB_SHIFT、SET_WB_LOCK、SET_SHUTTER_AWBLOCK_MODE、SET_AWBLOCK_MODE、
SET_CUSTOM_WB_SAVE/REQ_CUSTOM_WB_DATA/CWB_SETTING_DISPLAY、SET_WB_CHANGE_SPEED、
SET_FLASH_TIMING_SHIFT、SET_FLASH_SHUT_SPEED、SET_HIGH_RESO_SHUT_MODE。
LiroSeq 校验对：AeMeter/AeMeterSpotSize/AeSpotMeteringPoint/wb_color_temp(_fine)/PP_WBShift{Bgain,CC}。

### 7.2 AE/AWB 统计硬件（CamCore/CUC）

- **CAE 硬件块（CUC_CAM0 命名空间）**：`CUC_CAM0_ATRCAE_{CNT,I2DAT,IDAT}_{H,L}`（分区累计/数据，
  H/L 双字）、`CUC_CAM0_IS_DET_CAE_{START_X/Y,END_X/Y,INTERVAL_X/Y,HPTH_{H,L}}`（AE 测光窗几何+
  高光阈值）——**分区直方图/累计式测光硬件，测光窗可编程**。
- **WB 硬件块（CamCore, RTTI 实证 Getter/Setter 对）**：`ArcWb` / `NrsWb` / `SigWb` / `VatrWb`
  （+ DFECore ImgTopDclWbIwbOfst——DFE 内 WB 偏移）；原始增益面 `RawWbRGain/RawWbBGain`
  （FW 日志 `RawTargetColorSpace RawWbRGain RawWbBGain`）。
- **AWB 算法节点**：`CC: CalAwbAim() [AwbRawAim:%x] [exposure_id:%d]`（CamCore 内 AWB 目标值
  计算，raw 域）；闪光 WB：`CC: CalcStrbWBContPreDet(_Start/_End) Rratio Bratio AmbL`；
  自定义 WB：`PID_SET_CUSTOM_WB_AREA x/y_start/end` + SET_CUSTOM_WB_SAVE/REQ_CUSTOM_WB_DATA。
  **结论：AWB 估计全在 CP（appFw 仅菜单/属性面 s_allocate_white_balance_* 三态）**，
  算法本体日志极少（CamCore 内环），统计入口=CAE/ATRCAE+WB 硬件块。

### 7.3 SB 块（AF/散焦统计，与 AE 交织）

job_SB_* 122 个 job 中 ~50 个 = SB（Raw 域 AF 评价统计：CalcEvalValue/GenDiffHistogram/
HiReflectExclusion/HiResMulti*/CalcObjectOutlightCorrection/DvCalc）；**job_SB_ZpdResultSet**
（ZPD 结果经 SB 面进 FW）、job_EC_ValidZpdPriorityValue（EC 消费 ZPD 优先值）。
CapturePrelight/SB_CaptureRawPrelight{Init,Wait,End}.cpp = 预拍摄 RAW 流。

## 八、遗留（下一批）

1. ~~PID 表名字对齐~~ ★已解（Block C-2）★：appFw 属性注册表（FUN_032f75ec 族
   `(描述符, id, "PID_SET_*")` 调用）直接给出官方名——370 条 PID 全覆盖 0x4000-0x4182，
   与 CP 注册表 358 条对齐 345 条 → **fw_pid_registry_named.tsv**；25 条 AP 独有
   （DUMMY01/02/04/05/07、CAPTURE_START/END、锁管理族、RAW_EXTERNAL_OUTPUT 等）。
   眼选族：0x4047 SET_EYE_START_AF / 0x40fd SET_EYE_SELECT_MODE / 0x40ff
   SET_TRACKING_EYE_SELECT_MODE / 0x4102 SET_EYE_AF_MODE / 0x4104 SET_ANIMAL_EYE_FRAME_MODE /
   0x4105 SET_MOVIE_EYE_AF；通知 NID_EYE_SELECT_STATUS(0x20a2)/NID_TRACKING_EYE_SELECT_STATUS
   (0x2071)/NID_EYE_BLINK_INFO。仍留：fn1/fn2 语义（getter/setter?）。
2. LIRO 任务体的镜头寄存器面。
3. mix_in 的运行时注册点（★范围已收窄★：七路扫描后全 FW 唯一真运行时注册项；
   LC vsync 回调注册基础设施，与 Mount_AM 环同源——见 §10.1）。
4. ~~LiroSeq AF 序列本体~~ ★结构面已解（Block C-4，见 §九）★；~~AF "大状态机"任务体~~
   ★任务表机制已解 + 三簇候选圈定（Block C-5，见 §十）★：LIRO 任务表=分派器内联
   BL 链（非数据表）；剩余=在 §10.3 三簇中钉死 AF 模式机的具体状态迁移表。


## 九、LiroSeq AF 序列本体 ★C-4 已解（结构面全闭环）★（2026-10-12 凌晨第三批）

> 方法：BL 扫描器（/tmp/bl_scan.py，Thumb-2 BL 全扫）+ FC 队列地址反查 + FW 状态块数据流
> 反推。LiroSeq 的任务入口为运行时注册（静态零调用，与 JobDispatcher/mix_in 同特征），
> 但其三大序列的函数群已全部圈定。

### 9.1 LiroSeq = 三位一体序列器（身份修正/扩展）

"LiroSeq" 不只是 AF 序列——它是 **CP FW 层的电源+参数+AF 三合一主序列器**：

| 序列 | 函数群 | 证据 |
|---|---|---|
| **电源/唤醒** | FUN_0046a334（Normal Wake Up）/ FUN_0046a5ac（Fast Wake Up）/ FUN_0046a8f8（ReadKeysFromBackup） | 串 "LiroSeq: Normal_Wake_Up: Spinal_O…"、"Fast_Wake_Up: Spinal_On/Off"、"LiroSeq: Restore"、"LiroSeq: EEcmd"；Spinal=电源脊柱，唤醒源=16 键 backup 块（0x30162 参数→0x015fb6f0，"FW: ON_KEYS %x×12" 比对），唤醒码 1-11（键/EE/Spinal 分派），完成后 FUN_00bd9dac+FUN_00bd88ac(4,0x7006) 通知 |
| **参数序列** | FUN_0037d284（**Cons_FunctionNotify.cpp**，4865B）+ SET_COMP 群（0x37e000-0x386xxx）+ CheckSet* 校验器 | "FW: receive[0x%x,0x%x] before comp[0x%x,0x%x] (FAILED)/(QUEUEING)" 完成键接收机制；"FW: LiroSeq ParamCheckErr@%s[参数] cur/req" 全参数面（af_drive_speed/movie_af_drive_speed/zoom_drive/wb_*/ezoom_*/DROLevel/scene/StrobeMode/sl_ShutDriveSum…30+ 族）；"FW: %s: liroseq_for_next_boot[%d]" |
| **AF 驱动序列** | LC 层闭环（§9.3）+ AsyncVDLensHistory | "FW: SET_FOCUS_DRIVE[%d:%d:%d]"、"CheckSetAfDriveSpeed/CheckSetFocusDrive"、"LENS_BL_WAIT_FOCUS_DRIVE/LENS_BL_WAIT_STOP_MOVE_FC" |

LiroSeq trace 通道 = osal 队列 **0x008f013a**（FUN_0046a4a0 打印 "%4X %s %s"，级别 0/1/2）
——与 appFw 侧 snd_sync_msg 目标 0x8f013a 对上（C-3 §6.3 表）。

### 9.2 FW 状态块（参数序列的落点）

- **状态块 0x1502ec8，0xf18B**：全部 FW: SET_* handler 的写入目标（§5.1 已证顺序参数槽）；
  上下文指针全局 **0x1506738**（读方 `*(DAT_01506738 + off)` 解引用式访问）。
- **快照器 FUN_0094b662**：mutex 0x26（FUN_0063424c/00633c04）下整块拷出 +0x1503de0/df0 换代
  逻辑；静态零调用（任务侧运行时取）。getter FUN_0094bb5a 返回块基址。
- **Cons_FunctionNotify（FUN_0037d284）** = 参数序列接收主循环：56 处状态块引用（全二进制
  最多），完成键比对→FAILED/QUEUEING 双路径；其余 top 读方 = SET handler 群
  （FUN_0094b744=SET_PICTUREPROFILE、FUN_0094b3b2=SET_AF_AREA、FUN_0037a93c=
  Camera::FC::Api::DetectionTarget）。

### 9.3 AF 驱动序列：BL 命令漏斗全景（19 调用方全名单）

`LIF 发送 API FUN_00451f14` →（内部 BL）`LIF::BL_ASYNC FUN_004520a8` → `onMoveFcCmdIssued
FUN_00428324`（4 槽环）→ `JobDispatcher`。**19 个调用方（反编译 + BL 扫描双证）**：

| 调用方 | 身份 |
|---|---|
| FUN_00433000 | LC::Lens Send_Pos_Cycle（"PosCycleSens…" 失败日志） |
| FUN_00433764 | LC::Lens move_fc_is_rejected 处理 |
| FUN_0044d6c8 | 位打包 BL 命令发送器（+5/+6/+9 位域重排 → FUN_00b17cba trace 0x33000a/0x33001d → 发送，状态 2→3 迁移） |
| FUN_0044e374 | LENS_EC::B2L_SWITCH_IRIS |
| FUN_0045036c | BL 电源小状态机（0x15/0x16/0x17 态码，DAT_01a03ca9-ac） |
| FUN_00450730 | LIF::BL LENS_DRIVE_FREQUENCY |
| FUN_00450e64 | LIF::BL CommState 监控（LensState/PowMode/LC_T_O_Cnt/VsyncErrCnt/LIFState_Err/LensErr/LensTransErrCnt 全家） |
| FUN_00af729a/72c6/7330/74a2/7a14 | 0xaf7xxx LIF 客户端群（thunk 型包装） |
| FUN_00b1f3a0 / FUN_00b26cfc / FUN_00b2d650 / FUN_00b31aa6 / FUN_00b45504(6.1KB) | LIF 客户端散点 |
| FUN_00b2bdc6/bdf2 | LIF::IS_LENS_SHIFT_CYCLE_A_Send |
| FUN_00b2be82 | LIF::ALLOW_LENS_LOG_DATA_COM_A |

**setMoveFcCmd 双体（LC::Lens，FUN_0042d778=sync/FUN_0042d914=async）**：
- sync 路径校验命令字 **0x1d**（≠则 "setMoveFcCmd(sync): wrong cmd"）；源命令布局
  `{+0 命令字, +1..2 u16 目标位置, +3 单元数, +4 flags}`（flags bit7=位置有效、bit0-1=
  速度格式 0=raw/2=半档（×(DAT_018da770+1)>>1 标度，0xffff 钳位）、bit4-5=b2_unit_wob
  （仅 0 支持）、+0x10=b3_unit_shift（仅 0 支持，串实证））→ 资源分配
  （FUN_00644328/00638a38，错误码 0xffffffd7/-9/-0x12 族）→ 写 LC 上下文 +0x25/+0x30/+0x32/+0x34/+0x36/+0x38/+0x3c。
- **唯一上层 = addMoveFcCmd（FUN_0042846c，BL 扫描证实 1:1）**——即 B1 表中的 JobDispatcher
  cmd3 处理器；B2 的投递链在 setMoveFcCmd 处闭环。
- **FocusDriveEvent（FUN_0042db80，构造注册 "FocusDriveEvent"）** 上层 =
  **FUN_0042c2cc = AsyncVDLensHistory（11.6KB）**：CamVTimeInfo/LensVTimeInfo/LensVDInfo
  时基日志、"is_VD_sync(%d)"、config dump——**vsync 时基的镜头历史/合并体（ALH 家族本体）**，
  FocusDriveEvent::do_merge（"LensV Offset not matched VID"）在此层发生。
- **ALH_lensAttach（FUN_004276d4）** = 镜头挂载钩子（JobDispatcher 的静态提交方）。

### 9.4 运行时注册复核（BL 扫描）★已按 C-5 修正★

★本节初版数字有误（scan_bl.py S=0 时 I1 位符号误判，BL 漏报）★——C-5（§十）已修工具
并 capstone 全量交叉验证，修正后结论：
**onMoveFcCmdIssued 0x428324 实有 4 个 BL**（调用者=mix_in 内 2 处 + BL_ASYNC 内 2 处
——B2 投递链两路上游恰为其静态调用者，链条完全闭环，无需运行时注册）；
**JobDispatcher 0x427948 调用者 5 族**（ALH_lensAttach/onMoveFcCmdIssued/0xae3xxx 尾助手
×3）；**mix_in 0x43242c 七路扫描全阴性 = 全 FW 唯一真运行时注册**（vsync 回调）。
详见 §十（LIRO 任务表/四链/Cons_FunctionNotify 表驱动注册表）。

### 9.5 与 AP 的分界（呼应 C-3 §6.4）

主体结果（type 9/10）在 CP 内经 0x90060197 直达 FW AF 序列，参数面（SET_*）经
Cons_FunctionNotify 完成键机制落状态块，AF 驱动经 BL 漏斗到 onMoveFcCmdIssued——
**三层全部 CP 驻留，AP 侧零参与**（C-3 扫描第三重实证）。

## 十、LIRO 任务表解密 + 全量 xref 修正 ★C-5（2026-10-12 第四批）★

> 方法：capstone 全量线性反汇编（7.8M 指令 / 66 万控制流边 → /tmp/xref_edges.tsv，
> 重跑用 a1m2_ai_pipeline 内 full_xref 逻辑）+ 指针/ADR/B.W/BLX/TBB-TBH 五路引用扫描
> （新工具 scan_ptr.py / scan_adr.py / scan_b.py / scan_tbh.py）。

### 10.1 ★scan_bl.py 符号扩展 bug★（影响 §四/§九 多处结论，已修）

旧 scan_bl.py 在 S=0 时用 `imm32 & 0x800000`（= I1 位）判负数并错误回减，
I1=1 的正向调用全部目标污染 → **系统性漏报**。已修复并对照 capstone 验证。
由此推翻/修正的旧结论：

| 函数 | 旧结论（bug 产物） | 修正后 |
|---|---|---|
| onMoveFcCmdIssued 0x428324 | 0 个 BL → 运行时注册 | **4 个 BL**：mix_in 内 2 处（0x43280c/0x4329d8）+ LIF::BL_ASYNC 内 2 处（0x4523f4/0x45247c）——§四投递链两路上游恰为其静态调用者，链条完全成立 |
| JobDispatcher 0x427948 | 唯一静态 BL = ALH_lensAttach | **5 个调用函数族**：ALH_lensAttach 0x4276d4、onMoveFcCmdIssued 0x428324（B2 的 cmd3 直调本就存在）、0xae3b6c/0xae406e/0xae4138（尾部助手区，含 setLensInfo FUN_00ae51de 的 tail-b.w 0xae521e） |
| 快照器 FUN_0094b662 | 静态零调用 | **1 个 BL**：0x5250b8（0x524000-0x52cb78 大型 FW 序列函数区内，Ghidra 合并未拆） |
| mix_in 0x43242c | 0 引用 | **维持 0 引用**（BL/B.W/BLX-imm/绝对指针/ADR/movw-movt/TBB-TBH 七路全阴性）——全 FW 唯一真运行时注册（vsync 回调），§8.3 范围收窄到此一点 |
| Cons_FunctionNotify 0x37d284 | 静态不可见 | 无 BL，但有 3 处 {id,fn} 注册表指针命中（0xe452e0/0xe453ac/0x11ea8e8，记录 `{命令id, fn|1, 0}` 12B；id 实测 0x2009-0x201b 族）——**表驱动分派确认** |

### 10.2 LIRO 任务表 = 分派器代码内联 BL 链（"表"不存在于数据段）

"运行时注册"之谜的答案：**LIRO FW 的任务表不是数据表，是内核胶水区 runner 函数里的
顺序 BL 链**（编译器内联，故二进制中无入口指针字）。全部四条链已圈定：

| Runner（内核胶水区 0x6d3000-0x6db000） | 模块链（BL/B.W 顺序） | 身份（ADR 字符串实证） |
|---|---|---|
| **0x6d43f0**（电源/唤醒链；Ghidra 漏标签，误并入"FUN_006d4398"日志函数） | 0x1a00a8 → 0x1a0e78 → 0x1a1dac → 0x1a37d0 → tail 0x19ece0 | **唤醒场景**（§9.1 电源序列宿主） |
| **0x6d46c0** | 0x19dadc → 0x19e38c | **MainLoop/boot 链**（"MainLoop Start"、"boot_fact.type"、"sublcd"） |
| **0x6d4b00** | 0x1a0660 → 0x1a07a4（+0x19e644 消息发送） | **显示链**（yuvLayTableSize/yuvTimTableSize/play_Logo_ToDecode） |
| **0x6d4cca** | 0x1a19dc → 0x1a1ab8 | **按键链**（keymap/keycode/bk_size） |

- **模块统一形状**：入口 `ldr rX,[ctx+0x10xx]` → `cmp #2/1/0`（2=done/1=run/0=init）
  三态子状态机；每模块独占 ctx+0x10d4-0x1128 区间的一个状态槽。电源链 5 模块的
  完成判据（+0x10fc==7/+0x1100==0x11/+0x1104==0xd/+0x1108==3/+0x110c==3）在
  runner 尾部硬编码检查。
- **唤醒序列宿主实锤**：FUN_0019fedc（电源链第 5 模块 0x19ece0 的步进 5）=
  唤醒状态机（+0x110c 槽：0=FUN_0046a334 Normal_Wake_Up→1=FUN_0046a5ac Fast_Wake_Up
  →3=done；"is_Ee_Play"/"CmdEE false" 日志），唤醒码 1-11/Spinal/16 键 backup
  全在此步进内（§9.1 电源序列落位完成）。
- **驱动方式**：FW 消息分派器 blob **FUN_0019d490**（0x19d490-0x19e644 共 4.5KB，
  Ghidra 只反编译了首块，其余是 switch 分派体）收消息（receiver 0x19e644，9 处
  BL 发送方全在 FW 区内）→ 按类型 → 调 runner；0x19d490 自身被内核侧 0x6d335a
  尾分支（b.w @0x6d33aa）进入。发送端包装 = 0x6d4420（构造 0x28B 消息头
  {0x1000,1,0x28,2,...}）。内核胶水第二区 0x6d6000-0x6db000 = **LIRO_PMCB
  电源管理胶水**（串 "unreg sync cb on LIRO_PMCB"/"OFF: LIRO: UPM_CMD_OFF"），
  其内联分派指向 0x1a41c0/0x1a42a8/0x1a43d4/0x1a4618/0x1a46a8 族（PMCB 域）。

### 10.3 AF "大状态机"任务体：三簇候选（最终圈定）

1. **FW 模式/参数引擎**（最大嫌疑）：调用方区 0x3dd000-0x3e4000 + **静默工作函数族
   0xa1e000-0xa24000（约 300 个函数，全部经 movw/movt 引用 FW 上下文指针
   0x1506738，零日志串）** + 14-case tbh 模式分派器 FUN_003e1b08（←0x3dfdac/0x3dfe4c）。
   与 Cons 区（0x37d000-0x386000）相邻同域。
2. **FW 主序列大函数**：0x524000-0x52cb78 巨型函数区（Ghidra 合并），含快照器调用
   0x5250b8——FW 状态块 0x1502ec8 的任务侧消费者。
3. **消息分派器 blob FUN_0019d490**：FW 消息 → 四链 runner 的总入口，内含 3 处
   电源链 runner 调用（0x19e3f2/0x19e4a2/0x19e526）。
   真正剩余的"运行时注册"仅 mix_in 的 vsync 回调注册点（LC vsync 基础设施，
   Mount_AM 环同源，遗留）。

### 10.4 工具固化（本轮新增）

- `scan_ptr.py`（绝对指针/literal pool 反查，Thumb 位 ±1）· `scan_adr.py`
  （Thumb T1/T2/T3 + ARM ADR，含 ThumbExpandImm）· `scan_b.py`（B.T3/B.T4/BLX-imm）
  · `scan_tbh.py`（TBB/TBH 跳转表解表）· **scan_bl.py 符号扩展修正**。
  方法论：单工具阴性不作数，BL/B/BLX/ADR/指针/movw-movt/TBB-TBH 七路 + capstone
  全量 xref 交叉才可下"无静态引用"结论。
