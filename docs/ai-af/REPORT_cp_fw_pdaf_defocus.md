# REPORT_cp_fw_pdaf_defocus.md — PDAF/散焦链路（Block B 第三项 B3，2026-10-12）

> 数据源：a1m2_cpapp.c + copro/cpapp-b.bin + strings corpus。
> 回答：焦平面相位检测（PDAF）的硬件面、散焦量（df）怎么产生、流向谁、镜头校准数据从哪来。

## 一、PDAF/散焦硬件栈（模块地图）

```
[传感器相位像素] → ZPD 硬件块（phase detection）
    ├─ CamCore::ZpdDcsetter（FUN_0027241c 族）: setEyePtnO*/setPupilNum* —— PDAF pupil
    │   （相位检测像素对）布局/眼图配置
    └─ CamCore::ZpdAIF（FUN_00270c50/00270dbc）: CalcParam Width/Height/Extent/IP_Type ——
        ZPD AF 接口的缓冲参数化（out > memsize 断言）
  → FOPD 硬件块: ddl_ddl_fopd_controller.cpp
    ├─ FUN_00269d84 FopdController（5302B）: 4 路 IP 实例（+0x14/+0x18/+0x1c/+0x20），
    │   按 *(ctx+0x54)+0x1c..0x24 的 IP_TYPE switch 分派；FUN_0026dc68 FopdFrm（6836B，
    │   anomaly_fopd_rate/illegal_size 校验）= 帧处理
    └─ FUN_0026a394/0026a41c（错误路径）、FUN_0026db74（Spinlock 保护 setter/getter）
  → DFE（散焦估算引擎）: CamCore::dfeParam（FUN_0026f518，IifPre::Set…）
  → ADF 处理模块（0x1957xx）: AdfExecCountMonitor / AdfExecTimeMonitor（执行计数/耗时
    监视，Resume/Suspend/EndExec）—— ADF = 散焦处理管线，有完整性能监控面
  → df 值分发
```

**命名对应**：NOTES_ENUMS 的 "Mario = ZPD→DFE 散焦引擎代号" 即此链（ZPD 取相位 →
DFE 出散焦量）。FOPD/DFE 相关计算本体在硬件（与 STAPLE 同模式：cpapp 无相关运算代码）。

## 二、df 的 FC 侧消费（已在决策层证实）

- **JudgeDefocusFace 族**（REPORT_defocus_subject_selector.md 已覆盖景虚化选主体）：
  `JudgeFaceInfocus VGA face(...) defocus_th:%d`、`getMinReliableDefocusFace
  select_defocus_abs_:%u min_defocus:%u`
- **lock-on 范围扩展**（FUN_0012e730，fc_alg_transfer_to_animal.cpp）：
  `BeforeExpandLockon defocus_th:%d near_df:%d base_df:%d` → 以 beta 与 df 阈值扩展
  lockon 矩形（`AfterExpandLockon_beta` / `LCDFInfo base_defcocus near/far`）——
  **df 直接决定跟踪 lock-on 的窗口宽窄**
- `<DefocusValueNotify>`（@0x101fedc）：散焦值通知日志前缀
- FC 内部消息：同队列（0x90060197/UIPC 0x0197）承载 0xc80（AdamProcessManager）/
  0xd80（FeatureScalar oneshot），df/beta 经此进入 FC（REPORT_cp_fw_af_execution.md §四）

## 三、SET_FOCAL_PLANE_PHASE_DETECTION（FW 层开关面）

- PID：`pGFW: SET_FOCAL_PLANE_PHASE_DETECTION[%d]`（@0x3822d2）
- LiroSeq 参数检查：`FW: LiroSeq ParamCheckErr@%s[set_focal_plane_phase_detection] cur:%d req:%d`
  （@0x105faec）—— 该设置进 LiroSeq 序列参数面，cur/req 不一致即报错
- `CheckSetFocalPlanePhaseDetection`（@0x38c50c，__PRETTY_FUNCTION__ 断言串）
- 相关族：`SET_DEFOCUS_CONTROL / SET_DEFOCUS_CONTROL_POSITION /
  SET_BACKGROUND_DEFOCUS_MODE / FW: SET_BACKGROUND_DEFOCUS_CUSTOMIZE[%d][%d]`、
  `LC: exist_near_defocus_threshold %d` —— 近端散焦阈值联动

## 四、镜头校准/数据流（nflasha18 → AF）

- **载体 = Backup 子系统**：`BKID_LIF_LENSDATA(_USR_LMT)`、`BKID_RAM_ADDR_LENS_DATA`、
  `InitializeLensDataArea / ExtractFromCombinedLensData / RAM_SIZE_LENS_DATA`（LIF 日志族）
  —— 镜头数据（nflasha18 /lens 的 lensfile.bin + 镜头 ROM 内数据）经 backup.ko 的
  Backup_read/nread（含 **Backup_nread_interchip** 跨芯片变体）进入 LIF
- **LIF = Lens Interface**（BL 命令层的数据源）：`Mount_GetLensModelID() /
  Mount_GetLensSwitchInfo()`（BL_LENS_DATA null 断言）——与 REPORT_cp_fw_af_execution.md
  §四的 LIF::BL_ASYNC / Mount_AM 命令环同属一层
- 温度补偿：`Common/Lens_TempADcontrol.cpp`（镜头 AD 温度采集控制）

## 五、B4 首轮：CP 内 AE/AWB 模块图（2026-10-12 补）

**AE（曝光控制，CP 驻留，EC = Exposure Controller 家族）**：
- 调度：`EC_AESchedule.cpp`；静态截幅计算：`CaptureRaw/EC_CaptureRaw_CalcAe.cpp`、
  `EC_CaptureRaw_CalcExpose.cpp`、`SB_CaptureRawExposureInit.cpp`、`CaptureExposure_Selector.cpp`、`SB_Ae.cpp`
- 光圈：`EC_IrisAutoManualController.cpp` + 镜头侧机械光圈驱动
  `Lens_IrisInitStepper_Cam/Lens_IrisStepper_Dsc/Lens_IrisMKGetBear3_Cam/Lens_CommonIrisNDMK.cpp` +
  `Mount_DividedInfo_IrisDrivabilityData.cpp`（光圈 drivability 来自镜头数据）
- PID 面：`pGFW: SET_AE_METER_MODE[%d,%d,%d]`、`SET_CAP_AE_SMOOTHING[%d]`、
  EV_COMP1/EV_COMP2（双 EV 补偿通道）、CheckSet*EvShift 族（闪光/无反 EV 偏移）
- **脸优先 AE = LiroSeq 序列参数**：`FW: LiroSeq ParamCheckErr@[face_ae_mode]` ——
  与 AF 同机制：FC 主体结果同时喂 AF 序列与 AE 序列（主体联动曝光的证据链闭合）
- 原始统计回流：`ImportPackedRawByPcie`（AP 打包 RAW 经 PCIe 送 CP 做 AE 统计）
- 数字增益：`Cetus/PQD_DigitalGain_SystemDepend.cpp`（CP 侧增益）

**AWB 判定**：CP（cpapp）内**无独立 AWB 模块**（.cpp 源名/日志域零命中）——AWB 统计与
白平衡决策疑在 darwin ISP（刚反编译 1,242 函数，a1m2_darwin.c 可查）或 avcam 影像管线；
CP 只经 PQD_DigitalGain 落增益。→ AWB 归入 Block C（darwin/avcam 遍历）收口。

## 六、遗留

1. FOPD/DFE/ADF 的具体算法（相关性/相位差→df 换算）在硬件 + tuning 数据，寄存器面未挖
   （与 STAPLE 同判定：非 CPU 软件）。
2. `Acquire_DFE/Acquire_ZPD` 字符串（@0x4d9ed8 族）的资源管理器归属未定。
3. ADF 管线的完整数据流（入口帧格式、出口 df 精度单位）待需要时下钻。
4. BKID_LIF_LENSDATA 的 Backup 分区结构（对写回路线的 CRC 清单有用，并入 Block D4）。
5. AWB 全链 → Block C（darwin/avcam）。
6. AE 决策律（测光加权/收敛曲线）未下钻——EC_AESchedule 的调度器本体待挖。
