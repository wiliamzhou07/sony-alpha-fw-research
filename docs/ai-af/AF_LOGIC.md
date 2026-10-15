# α1 II AI 对焦逻辑逆向笔记（AF_LOGIC.md，运行时状态，持续更新）

> 目标：完全理清 α1 II（ILCE-1M2）的 AI 对焦：识别 → 关键点决策 → AF 控制。
> 数据源：`firmware_reverse/decompiled/a1m2_cpapp.c`（CP 固件 Ghidra 反编译，基址 0x108000，
> 47198 函数）、`a1m2_adam_app.c`、`a1m2_avcam.c`（AP 侧 AARCH64）。
> 索引：`a1m2_ai_pipeline/cpapp_fun_index.tsv`（FUN 地址 → 字符串引用）。
> 提取工具：`extract_fun.py FUN_xxx`、`extract_fun_by_range.py <start> <end>`。

## 一、系统架构（已确认，2026-10-11 修正）

```
AP (CXD90057, 4×A35, AARCH64)                CP (CXD90058, ARM32)
┌──────────────────────────────┐            ┌────────────────────────────────┐
│ av-cam.bin (13MB): 静态影像管线 │  PCIe      │ cpapp-b.bin (19MB):            │
│  VDT/SDF/StillMP/JPEG, 无 AF   │ ←────────→ │  · FW 层 = 主相机控制            │
│ appFw.so (57MB): UI 框架 (ux)  │            │    (AFMAP/AE/AWB/AF序列/         │
│ kmod: liro.ko (镜头I/O序列)     │            │     SET_FOCAL_PLANE_PHASE_DET)  │
│ nflasha3/adam_app.bin (539KB   │            │  · AdamDriver+AdamSequencer     │
│  ARM32, 另一颗处理器/前置CP?)    │            │  · FC::Keypoint (AI AF 决策)     │
│  "FRONT_CP_INTERCHIP" → 双CP    │            │  · FC::Alg::Staple / HUMAN_MOT  │
└──────────────────────────────┘            │  · IDT (人脸检测硬件抽象)          │
                                            └────────────────────────────────┘
AI 资产: /usr/data/ai_dict/default/default.nab (17 子网) + scd_dic1/2/3 + sabin/*
```

要点：**AF 的"脑"(主体选择/关键点/搜索区域)和"手"(对焦序列/镜头驱动)都在 CP**；
AP 只做影像处理与 UI。adam_app.bin 在 nflasha3(引导分区)，独立于 cpapp，
经 interchip 与其协作（FRONT_CP）。

## 二、识别模型清单（default.nab 17 子网，元数据层已破译）

| # | name | 输入→输出 | 角色 |
|---|---|---|---|
| S0 | sony_net_opt_NHWC | 512×336×3 → 19ch热图+40ch PAF | 姿态主干第一段 (OpenPose式) |
| S1/S2 | reid / reidpost | 64×128×3 → 64维 | 行人重识别 (跨帧锁定同一人) |
| S3 | tfl107_t58_e70_q58_d53 | 224×224×3 → 13el | 人脸 107 关键点(?) |
| S4/S5 | model_NCHW ×2 | 双输入→uid_1 | 人脸对齐/仿射 |
| S6 | aed_03_00_05_rc2 | 128×128×3 → 4 out | 眼部检测 (AED) |
| S7-S10/S13/S14 | dummy 家族 | 80/40/20/10/5 网格 | 人体检测金字塔 |
| S11 | tflite_djd5-U-resnet7-32_64 | 32×64×3 → 64 | 小分类器 |
| S12 | sfr_tf_resnet_454-80-160-320-512 | 64×64×3 → 512d fp16 | 人脸识别嵌入 |
| S15/S16 | v58_h27_head (416×288/288×416) | → 18/36/2/1ch | ROI 姿态头 (27关键点, 双方向) |

权重块 = NPU SRAM 镜像（内嵌 DMA 描述符 + tile 打包），重建网络需 NPU ISA（见 NOTES_NAB_REVERSE.md 第十一轮）。

## 三、FC::Keypoint 模块地图（反编译文件结构，全对上源码文件名）

- process/post/inclusion_checker.cpp @0x302b40+：judgmentInclusion（主体类别→优先部位判定）
- process/post/estimate_region_generator.cpp @0x302074+
- process/post/result_calculator.cpp @0x306178-0x308588（drop 条件/staple 置信度/FoundStatus）
- process/post/result_hysteresis_calculator.cpp @0x308588
- process/post/result_manager.cpp @0x3088dc；result_sender.cpp @0x308ad0（发 AP）
- process/post/xedxhd/{adam_callback,result_maker,calculation,frame_selector,xed_result_impl}.cpp @0x30a0c0-0x30d4e0
- process/pre/aed/{resolver_search,resolver/xhd_search}.cpp @0x30dbd4-0x310b00
- process/pre/generator/{all_search,region_generator,xed_estimate_frame_selector,xhd_z_align,xy_search}.cpp @0x310b00-0x313000
- process/pre/region_provider.cpp / search_controller.cpp @0x312894-0x313139
- process/pre/track/{track_request,track_setting,track_controller}.cpp @0x313944-0x3179a8 + src/track_task.cpp
- XED = 高置信度跟踪结果(XedResult)、XHD = 次级(XhdResult)；XRI = XedResultImpl

## 四、主体类别枚举（judgmentInclusion 分发表，已确认）

类别值（XED 取 data[0xA9]，XHD 取 data[0x59]，子类 data[0x5a]）：
- 1, 2 → FUN_00302d90（人/动物通用部位判定 → judgmentAnimalBirdPrioPartEye 部位表迭代）
- 3, 4, 5, 8 → FUN_00302e08 judgmentInsectAndAirplane
- 6 → FUN_00302eb8 judgmentTrain
- 7 → FUN_00302fe4 judgmentCar
- (另有 judgmentAnimalBirdPrioPartHead1/Head2/Body1/Body2 @0x3041f8-0x304788，由 1/2 类深路径调用)
- 对应 AP 侧 LiroSeq 参数: detection_auto_target_{human?/animal_common/animal_bird/insect} + car/train/airplane

## 五、α1 vs α1 II 差分（3544 条新增字符串，全量清单 diff_a1m2_new_strings.txt）

α1 II 相对 α1 全新增的模块（α1 无）：
1. **Camera::FC::Keypoint 整个子系统**（57 pretty 串）— AI 对焦核心
2. **Adam 驱动**（241 条）：AdamSequencer、AdamDrv、JnpDetectPose、Adam1st/2ndCallback、StartAdamCalcResultAndNextRe...
3. **HumanCross**（HH 人-人 / HB 人-躯干交叉判定）+ **HumanMainSubject**(judgeMainSubject) — 多人主主体仲裁
4. **SeqMonPoseTrack / FeatureMonPoseTrack** — 姿态跟踪序列（getStapleTr/receiveMonFace/startCalc/startDetect）
5. judgmentAnimalBirdPrioPartEye/Body1/Body2 新部位判定；STAPLE_OCCLUSION_TYPE 遮挡类型
6. setInitialParamReid — ReID 初始化
→ **α1 已有**：人脸/眼检测跟踪、Staple 基础跟踪、IDT 硬件人脸检测管线；α1 II 加的是"姿态+多人+深度搜索"层。

**识别目标 UI 层差分（2026-10-11 补充，appFw.so 字符串实证）**：
- α1 II appFw：`auto_recognition_target_setting` + `auto_recognition_target_candidates` +
  `EVENT_REMOTE_AUTO_RECOGNITION_TARGET_SETTING` —— 识别目标菜单含 **Auto（自动）** 选项（候选列表式多选）
- α1 appFw：仅 `recognition_target` 属性与 remote_presenter 各主体 sensitivity/subject_shift_range
  设置（bird/insect/plane/car_train/animal 的 remote API 管线居然都在），**无 Auto 选项**（0 命中）
- 含义：把"自动选择主体"带给 α1 需处理 UI 侧（appFw 补丁/寄生存量设置值）+ CP 侧跨类仲裁；
  remote API 已有的 recognition_target 属性通道可作免 UI 注入点的候选。

## 六、KeypointPriorityResult / 判定细节（已确认部分）

- InclusionChecker::judgmentInclusion (FUN_00302b40)：
  - 输出结构 param_1+0x15..0x18 初始化 0xff/0/0/0；5 元素循环重置 +0x758=0/+0x75d=1
  - XED(type=1) 优先级类 = 数据对象[0xa9]；XHD = [0x59]（校验 [0x140]!=-1）
  - 类别 dispatch（见第四节）；"Target mismutch" 校验 vtable+0x178 查询
  - XHD 路径：FUN_00303a98 (BEST/CURRENT change_array_index) → FUN_00303120 → FUN_00303ee0 (ChangeBaseFrame BEST/XHD)
  - 状态标志：+0x17=1 表示 "XHD is verifying"；帧表 stride 0x148/部位
- 部位表 DAT_003041dc（静态表，3 部位迭代，index 4 特殊处理）

## 七、AdamSequencer(NPU 调度)★已解★

源码 adam_sequence_manager.cpp;上下文 DAT_0131f1d0,队列 DAT_011c9970。

**内存布局(FUN_0015e914 memory_alloc)**:
- input_data ×10(stride 0x2b300)—— 输入帧环(10 深)
- img_reid_out ×8(stride 0x6000)—— ReID 输出,最多 8 主体
- img_pose_out(+paf_map+head_map)—— S0 姿态输出
- param_pose-reid-reid_sim(0x4200 间隔)+ param_scene(+0x4700)

**每帧时序**:
```
VSYNC → SyncUtilityAdamSeq(FUN_00bc453c) → Adam::SetInputImageInfo(FUN_0015e1a4)
  → PrcInfo 4 深环(0x68B/项: +0x54 buf句柄 +0x58 帧id +0x5c/60 地址 +0x64 flag);满→丢帧还缓冲
FUN_0015c0f0 模式判定(mode=PrcInfo+0x2dc, 1-5):
  mode1-3 → Adam::AdamExecRequest(FUN_002a5ca0)(pose 判定; 写 reg 0x13; msg 0x1700 资源请求; 99000 tick 节流)
  全部 → CC::GetAdamProcessRequest(FUN_0023f4e4)(reid/scene 判定)
  → 4 个子网使能位 +0x2ed/+0x2fd/+0x30d/+0x31d; m_mode_info_now=最大分辨率级
FUN_0015bccc 建序列节点(0x58B 模式块, [0x17]=0x14 超时) → 3 通道×7 请求环(依赖位图)
每子网完成 IRQ → Callback(FUN_0015b608, ch=0..2):
  状态∈{0,2,10} 校验 → 结果回调[+0x3e4] → 清依赖位(帧+0x644/序列+0x3a8)
  → 帧掩码清零 → StartPRCImageTransDirect(FUN_0015b7dc, 查 4 项区域表 DAT_00d89120 直映)
     / 通道空 → Parallel(FUN_0015b994 兜底) → 启动下一帧搬运
帧间 PowerSave_Execute(FUN_0015cca0): 负载/空闲阈值(0x1e000/0x3c000; 56000/22000µs·推断)
```
- Adam 协处理器侧(adam_app.bin, ARM32 裸机):FUN_0002e3d8 = NAB 块装载器(魔数 0x8010e02/0x801022c,
  与 NAB 块头加载地址 0x0801xxxx 同族!);FUN_0003ded4 = **17 关键点姿态解码**(COCO17,0.5/-0.5 归一化);
  OSPI flash 驱动(0x15fxxx)加载其固件
- CP↔Adam 接口:DMM 共享内存(AdamParamMgr FUN_002f8acc + ConvCetusVA2AdamPHY FUN_002ce0ec)
  + OSAL 消息(0x1700 资源请求/0x210 STAPLE 应答)+ IRQ
- 结果导入:AdamFrManager::loadDetectionResult(FUN_002a4148):暂存区 DAT_013b4c20(头+0x7e0=检测数≤8,
  0xfc/条)→ 主体结构 0x498/主体,关键点 9B 元组 @+0x38c-0x3bc,/1.25 归一化 → REGISTER_TRACKED 注册 tracklet

## 八、眼选规则(TrackingEyeSelector)★已解★

- 接口 fc_get_if_tracking_eye_selector(FUN_002bd31c):mode∈0..6 → 5 张 flash 阈值表(0x198bdde+mode*0x200),
  每表 {u8 ratio_a, u8 ratio_b, u16 size_max, u16 size_min, u16 size_min_hard};mode3=条件表(子参==2→B else A)
- 接受半径(FUN_0029e9c0):s<硬下限→0;比例 a·s / b·s / 线性插值;>>4 定点。**半径随脸尺寸线性变化**
- 主判定(FUN_0029e8bc):双眼可用→**距当前对焦点最近者胜**(平手→右);单眼→直接选;
  选中者需距焦点 ≤ 接受半径。跟踪侧 HUMAN_MOT::ALG(FUN_0086ec44)同样"最近者胜"
- EYE_SELECT_MODE 字符串不存在;菜单枚举名未恢复(mode 0-6 语义待 AP 侧确认)
- **Block A 补充(详见 REPORT_staple_reid_faceid.md §五)**:阈值表在 RAM tuning 区运行时
  流式填充(游标 DAT_011e8be8),非编译期常数;mode 经候选结构 +0xC8 传入(上位 vtable 间
  接调用);接口来自 fc_lib_if_flash(闪光灯库)→ mode 语义疑为**闪光状态**而非菜单选项

## 九、STAPLE 跟踪/遮挡/降级 ★已解★

- STAPLE 引擎 = 独立硬/固件单元 DDL_MINNA(fc_drv_staple.cpp 驱动);批量启动 FUN_002b7b40
  (0x228B/track, 应答 0x210)
- **遮挡判定**(FUN_008766ae/ca):与其它 tracklet 矩形重叠率 ≥ 阈值(虚表+0xb0)→ occluded(bit0)
- **放弃判定**(FUN_002dfe54):bit1 → normalize_parts_pos 失败则放弃本帧(bit1);状态 2bit/帧/track
  写 trackctx+0x15b9+frame*0x458
- **init 位置跳过规则**(FUN_00832e94):10 深历史环中查 id;合成矩形越界或旧 init 位置 ∉ 矩形 → 跳过 init 更新
- 结果落地(FUN_002e09f8):part 类型 0 只写当前,1/2/3 写历史槽 0/1/2(类型1=脸侧+0xcd.., 类型0=体侧+0xcc..)
- tracklet:注册经 loadDetectionResult→REGISTER_TRACKED(0x18B/项);距离校验 src_tracklet_handler.cpp
  (isSameHumanViewOfDistance/calcDistanceOfTargetFace|Body/ConvertBeta8_24toDistance32);
  SubSeq Init/Track/Train(FUN_002eaf10/002eabd4/002eb2a4);部件字典有效性 JdgStapleinit(FUN_002d9fbc)
- **Block A 补充(详见 REPORT_staple_reid_faceid.md §一)**:训练资格 JdgStapleinit(字典版本
  + 时间窗 99999)、init=逐 part 参数化(FUN_002da218 尺寸分级/搜索区表 0x2da39c)、train=
  纯状态置位(FUN_00871e5e)、Hann 窗 0x400B×WINDOW_TYPE(FUN_00292070)、结果解包 0x114/
  part(FUN_00294070)——**相关滤波本体在 SA-IP 硬件,cpapp 无 FFT/相关代码(双证)**

## 十、result_sender:发 AP 的 0x170B 包 ★已解★

- FUN_00308ad0 输入帧结果结构:+0x1c main_subject_num、+0x24 subject id、+0x72 part、+0x2c disp_eye、
  +0x70/71 左右眼 valid+坐标、+0x9a head 矩形、+0xa4 body 矩形
- disp_eye 参考点:1→eyeL/R、2→head 中心、3→body 中心
- AP 包 FUN_0089a694(0x170B):type 9/10+帧号;**le/re/head/body 四组 id 对**;
  QVGA(÷2)几何:10 组 u16 矩形(眼/头/体+运动框)+copyRawAnimalDataQVGA_HeadBody 动物中心;
  ≤5 part 清单;抑制条件(+0xa8 全局/+0x120 主体/虚表+0x168)
- 主体优先级评分 FUN_003099f8:模式 1-4,距离²+尺寸增益(虚表+0x1a0..+0x1b8)+边缘权重(case2/3)

## 十一、主主体判定(MainSubjectJudger)★已解(骨架)★

- FUN_002d9454 judgeMainSubject(src/main_subject_judger.cpp):
  - vtable+0xc0()==1 → 触摸/强制模式:全部候选置选中(+0x71=1)
  - 常规:首个候选锁定为当前主主体(*param_2==0 时);已有主主体 → FUN_00870df0 重选
  - 丢失条件不满足 → 清空(id 全 -1)
- 重选资格(FUN_00870df0):候选时间戳(+0x14c/14d)与当前时间差在窗口内(sVar6×1000ms)
  且 vtable+0xe4 有效性 != 0 且 +0x40c(跟踪中) != 0 → +0x71=1;最终选择由 Keypoint 流水线
  优先级评分(FUN_003099f8: 距离²+尺寸增益)定夺
- HumanCross ★已解★(详见 REPORT_human_cross.md):两两判定 6 主体配对,配对表(24B 条目×8/主体
  @+0x3BC,跨帧页复用)去重;CrossJudge=Head/Body 框 2×2 IoMin 重叠(日志 HH/HB/BH/BB),
  AdjacentJudge=扩展框仅 HH 确认;FrontJudge 比较两脸 df(散焦量,主体+0x484/+0x488):
  **更糊=前景遮挡者(pos=1),更清晰=被跟后景(pos=2,"my face is in background")**;
  输出 is_crossing(+0x47C)/is_adjacent(+0x47D)/crossing_position(+0x47E)/时间戳(+0x480)
  → 注册镜像到 track(+0x236C-E/+0x2370/74/78);消费:CalcCoef 防串号系数、交叉期热图保活、
  isFaceSwapPermittedByCross 人脸 ID 互换放行
- PriorityDefocusSubjectSelector ★已解★(详见 REPORT_defocus_subject_selector.md):
  电影 LockOn/Subject 下景虚化选主体——≤2 脸直锁当前 top;否则 PreTopFace 脸/头/躯干
  三候选区 PreFaceIsInLockOnRange(min_df,Mario=ZPD→DFE 散焦引擎)保持性判定;
  终选 getMinAverage/MinReliableDefocusFace(SelectDfAreaInfo[24] 取 df 最小);
  curr_top 把胜者移到主主体链表头。AfAssist 路径与 df 兜底在本构建为 abort 桩

## 十二、结果计算/置信度/跨帧选择 ★已解★(详见 REPORT_result_calc_frame_selector.md)

**Adam→FC 数据结构**(ResultMaker):
- Raw XED 帧 0xd14B,脸 0x344B:id/cx/cy/w/h/roll/class/score/pitch/yaw/vis(eL,eR,nose)/
  眼+鼻关键点数组{f32 score,s16 x,y}(每眼独立数组 @+0xd58/+0xe5c/+0xf60)
- Raw XHD 目标 0xa24B:id/框/roll/数组{score,x1,y1,x2,y2,type}(16B/条)
- KeypointXedResult 0xC8B:valid/score/elx/ely/erx/ery/nx/ny/image/target/part/beta u64/focal u64
- KeypointXhdResult 0x148B:数组条目 24B

**帧级编排 ResultCalc(FUN_00307d5c)**:
1. FrameSelector init:af_select_pos = 配置点或 AF 区域中心;apply[5]=2(NOT_APPLIED)
2. cmpBest(逐 part):XHD best 与当前 AF 区域重叠比较 + IoU 门限 + prio 目标一致性 → apply 1/2
3. getFoundStatus:**FoundStatus = aed==3?2 : stpl==2?3 : aed==1?1 : 0**
   AedConfidence = staple 判分阈值化(≥t_c→3, ≥t8→1, else 0)
4. drop 链:beta∉[low,high](flag 0x80000)、eye_dist 容差(flag 0x100000)、OutOfFaceArea
   (重力点出预测框,半宽=眼距×scale_b)、eye_dist_over、EYE not included in part、
   zDdrop_by_roll、EEP 期望眼距偏差
5. ScoreAndFrame pickup:**跨帧最佳 = 以 af_select_pos 为基准的最小 dist² 竞争**
   {XED best 历史(200B stride 环), 当前 XED, XHD};prio 目标豁免;非 prio XHD 距离×惩罚系数;
   XHD 须过面框 IoU/面积比门
6. NearestXhdSameTarget:与上一帧连续性校验(IoU 距离 ≥ prioIOU 门限 + 尺寸比)→ 不同目标 apply=0 否决
7. XRI 判废:type1 眼误差≥上限(0x170 型享豁免阈值)/type2 置信<下限
8. 滞回:20 槽 FIR 环形缓冲(stride 0x740),≤10 抽头加权;AedConfidence≠3 超 timeout(µs)清缓冲
9. verify 状态机:0=LOW,1=M计数,2=M饱和(5帧),4=VERIFYING,5=STABLE;
   xhd==3 或 stpl==2 直接稳定;丢失 L 计数(Lmax 封顶);V≥specMax 连续 verify 才升 STABLE
10. TrackingCancelByDfValidRatio 计数器:每帧++,AedConfidence==3 清零(丢焦保护滞回)

**位置切换滞回常数**(实测):单轴死区 ×0.9035(下)/×1.1025(上)——防两目标接近时抖动;
特判类型集 {0x160,0x170,0x180,0x260}(4:3 型优先);最近点像素门限 800.0f

## 十五、搜索模式/区域生成/跟踪状态机 ★已解★(详见 REPORT_search_region_track.md)

**ModePattern 0-25(全命名,表 DAT_00d74cd0)**:0 ALL, 1 RELIABLE_SHIFT, 2 POTENTIAL, 3/4 VERIFY(_FB),
5 RELIABLE, 6 ALL_ALIGN, 7 RELIABLE_SHIFT_ALIGN, 8/9 RELIABLE_XYZ_ALIGN/RELIABLE_ALIGN, 10 RELIABLE_XYZ,
11 RELIABLE_SECOND, 12 RELIABLE_ONLY, 13-16 RELIABLE_ONLY_{SHIFT_ALIGN,XYZ_ALIGN,ALIGN,XYZ},
17 ALL_MARIO, 18/19 SLAVE_XYZ(_SPEED), 20/21/22 SLAVE_POTENTIAL/VERIFY/VERIFY_FB,
23/24/25 SLAVE_RELIABLE(_XYZ/_SECOND)。**XYZ 后缀=纵深搜索;ALIGN=中心锁定变体;SLAVE_=从实例**。

**XHD 模式 0-12**:XHD_ALL/XHD_AF_ALIGN/XHD_RELIBLE_AF_ALIGN/XHD_RELIABLE_MARIO/XHD_RELIABLE_ALL/
XHD_RELIABLE_XY/XHD_RELIABLE_ONLY/XHD_MARIO/XHD_TRACKING_ALIGN + 4 无名。

**搜索模式决策(主实例 getMasterPattern FUN_0030f404)**:
- 目标跑出 lock-on 范围 → ALL;未检出 → ALL/ALL_ALIGN/ALL_MARIO/POTENTIAL(场景判别)
- 已检出 → RELIABLE_SECOND / RELIABLE 族(XYZ 使能×场景判别×ALIGN 查询组合)
- 从实例 transfer:SLAVE_RELIABLE(_XYZ)/SLAVE_RELIABLE_SECOND;AED 眼结果校验失败→强制回退
- XhdResolver.transNg:状态机(prev→FoundEnable(只看 part3/4=body!)→LHEnable)→ XHD 模式映射

**区域生成**:
- 5 槽×0x6568B;assignable 恒 5;getModeInfo5 查 26×5 part-id 表(手动/自动×常规/XHD 四套)
- SHIFT 类模式 = 5 步×40B 扫视序列表逐帧播放
- calcScalingRegion:norm=size·zoom·level/640 → 32 项级别表(级别 1-4 = ÷2/4/8/16,min_size 64-120)
- **Z 纵深搜索** = XhdZAlignRegionGenerator:基准框尺寸 × 比例表[idx]/16 逐级缩放,每级一个方形区域
- XEFS 平滑器:IoU+尺寸比门限 + [cur+down, cur+up] 接受窗口(防检测框跳变)
- 输出 Region_Param[32B]{res,id,cx,cy,w,h,ip,indx}

**TrackSequencer 10 状态机(核心)**:
```
0 execStartInit → 1 execEndInit → 2 execStartTrain → 3 execEndTrain
8 execBulkInitTrain(批量合并)      4 execStartDetection → 5 execEndDetection(取回 staple_pos)
6 execCancel   7 execUpdateZpdResult
超时: type-7 定时器 + 每帧 elapsed>=timeout → 结果失效(rec+0x30=1)
重初始化: xed/xhd_confidence==0(矛盾证据)或 AED 结果不正确 → StartInit 重建
```
- **置信度三元值 {0=矛盾推翻, 1=高置信, 2=弱}**:xed_confidence/xhd_confidence 用"与已跟踪
  目标链表的 id 一致性"裁决矛盾;head_conf 在 part1/2(head)间选择;slave_disable_body_set 控 body
- part↔槽:slot0→part0(脸),slot1→part1/2(head),slot2→part3/4(body)
- part 名(FUN_008C505C):1,2→"head";3,4→"body";其他→"none"
- skip_request:每 N 帧挂起重初始化请求(节流);Init_start_img_type 表 {1,2,2,3,3}

## 十六、★全流水合成:α1 II AI 对焦每一帧发生了什么★

```
[传感器 RAW → CP]
  ↓ (前置: IDT 硬件人脸检测管线 + FOPD/AFMAP 硬件块并行工作)
[VSYNC] SyncUtilityAdamSeq → Adam::SetInputImageInfo(PrcInfo 4深环)
  ↓
AdamSequencer 模式判定(pose/reid/scene 使能) → 3 通道请求环(依赖位图) → NPU(adam_app)
  → 17 子网推理: 姿态链 S0→S7→S8/S10/S14→S9/S13→S15/S16 (19热图+40PAF→27关键点)
                 ReID S1/S2 (64维), 人脸 S3-S5, 眼 S6(AED), 分类 S11/S12
  ↓ IRQ
AdamFrManager::loadDetectionResult: ≤8 主体/0x498B(框+关键点/1.25) → REGISTER_TRACKED
  ↓
ResultMaker: Raw XED(脸+眼+鼻关键点)/Raw XHD(部位框) → KeypointXed/XhdResult(+beta/focal)
  ↓
[FC::Keypoint post 层]
  ├─ drop 链: beta带外 / eye_dist容差 / OutOfFaceArea预测框 / EYE not in part / roll / EEP
  ├─ FoundStatus = aed==3?2 : stpl==2?3 : aed==1?1 : 0   (AedConfidence 由 staple 判分双门限)
  ├─ FrameSelector: af_select_pos(=AF基准点) → 跨帧最小 dist² 竞争{XED历史,当前XED,XHD}
  │    + prio豁免 + XHD惩罚系数 + NearestXhdSameTarget 连续性否决 + XRI 判废
  ├─ FIR 滞回(20槽/10抽头) + verify 状态机(LOW→M计数→VERIFYING→STABLE) + TrackingCancel计数器
  ↓
[主体与部位仲裁]
  ├─ MainSubjectJudger: 资格(时间窗+跟踪中) → 多候选由评分(距离²+尺寸增益)定主主体
  ├─ HumanCross: 人-人/人-躯干交叉仲裁; STAPLE: 遮挡(重叠率)/放弃(normalize失败)/init跳过规则
  ├─ TrackingEyeSelector: 距对焦点最近的眼胜, 接受半径随脸尺寸插值(5 张模式表)
  └─ InclusionChecker: 主体类别(人/动物/鸟/虫/车/火车/飞机)→ 优先部位判定(judgment* 族)
  ↓
[FC::Keypoint pre 层 = 下一帧搜索规划]
  ├─ TrackSequencer 10 态机: Init→Train→Detection(批量变体), 超时失效, 矛盾→重建
  ├─ xed/xhd_confidence {矛盾/高置信/弱} + head/body part 分配(slot0→脸,1→head,2→body)
  ├─ ModePattern 决策: lock-on 范围外→ALL; 未检出→ALL/ALIGN/MARIO/POTENTIAL;
  │    已检出→RELIABLE 族(XYZ 纵深×场景×ALIGN 组合); 从实例→SLAVE_*
  └─ 区域生成: 5 槽 part-id 表 + SHIFT 扫视序列(5步) + 级别表(÷2/4/8/16) + Z纵深逐级缩放
       → Region_Param[32B] → AED/STAPLE 引擎执行
  ↓
result_sender: 0x170B 包{main_subject, le/re/head/body id, QVGA 几何×10, ≤5 part 清单}
  ↓
[CP FW 层 AF 控制环]
  PID_SET_EYE_AF_MODE / SET_EYE_START_AF / SET_FACE_AF_MODE / SET_FOCAL_PLANE_PHASE_DETECTION
  / SET_AF_RANGE_LIMIT / AfSpeedSensibity / SET_DEFOCUS_CONTROL(背景虚化联动)
  → LiroSeq AF 驱动序列 → liro.ko(UDIF) → 镜头; PDAF 散焦量来自焦平面相位检测
```

**设计要点(逆向确认)**:
1. **双轨制**:XED(高置信跟踪结果)与 XHD(次级检测)全程并行,置信度由 staple 判分+
   id 一致性裁决,矛盾时 XHD 推翻 XED
2. **稳定性优先**:FIR 时间滞回 + verify 计数 + 位置死区(×0.9035/×1.1025)+ init 位置冻结
   —— 一切为了防 AF 呼吸/抖动
3. **纵深感知**:Z 搜索(RELIABLE_XYZ 族)+ beta/focal u64 参数 = AI 估算的物距/景深参与决策
4. **lock-on 语义**:目标出 lock-on 范围立即降级 ALL 全画面搜索
5. 所有阈值均为运行时配置(无编译期常数)——tuning 参数外部化

## 十七、AF 执行层(FW/LiroSeq,CP 内闭环)★已解(接口面)★

FC::Keypoint 的 0x170B 结果包**不离开 CP**——由同 CP 的 FW 层(AF 控制主循环)消费:
- PID 参数面(pGFW 日志):PID_SET_EYE_AF_MODE、PID_SET_MOVIE_EYE_AF、SET_EYE_START_AF、
  SET_FACE_AF_MODE、SET_FOCAL_PLANE_PHASE_DETECTION(焦平面 PDAF)、SET_AF_DRIVE_SPEED、
  SET_AF_RANGE_LIMIT(_DRIVE)、FOCUS_RANGE_LIMITER、SET_AF_PRIORITY_IRIS_DRIVE_MODE、
  SET_DEFOCUS_CONTROL(_POSITION)、SET_BACKGROUND_DEFOCUS_MODE(背景虚化联动!)、
  SET_EXPAND_FOCUS_AF_MODE、SET_FOCUS_BRK_EXEC_COUNT、AfSpeedSensibity、PreAf、
  AutoFocusSensingArea、AdjustSequencer
- **Block B 补充(详见 REPORT_cp_fw_af_execution.md)**:
  - ★前缀修正(深夜二批)★:"pGFW" 为解析伪影——全部 196 条串首两字节 "pG"(0x70,0x47)与函数尾
    `bx lr` 重叠放置;真实日志前缀 = **"FW: "**(decompile 199 条 s_FW__SET_* 实证)。
  - FW: SET_* 参数面 196 条=完整 PID 面;PID 描述符表@RAM 0x11eb02c-0x11ecc10
    (358 条×20B {fn1,PID 0x4000-0x4182,fn2})→ fw_pid_registry.tsv
  - **LENS_LC = 镜头控制模块**:JobDispatcher_Entry(FUN_00427948,子命令
    2=updImage/3=addMoveFc/4=...)、addMoveFcCmd(FUN_0042846c)、predictFcPos
    (FUN_00428a1c,预测对焦)、calcMoveFcStartTime(FUN_00428798,打印 SET_DEFOCUS_CONTROL
    =虚化联动影响移动时序)、ECOG/曝光结束位置预测、convCamVTime2FRC 时间基
  - **liro.ko 身份修正:nm 实证=ITRON/T-Kernel RTOS 模拟层(CRE_TSK/acre_*/Vspin_*)**,
    非"镜头 I/O 驱动"——LiroSeq=LIRO 上的任务代码;镜头 I/O 本体在 LIRO 任务体
- 驱动链:FW AF 序列(LiroSeq)→ liro.ko(AP 内核 UDIF 总线驱动, Etools-LIRO)→ 镜头
- 数据回流:FocusDistanceFromImagePlane/FocusRingPosition/ZoomRingPosition(FW 日志)
- interchip 传输层:UDIF 内核框架(7 种后端,PCIe 只是其一),详见 REPORT_interchip_protocol.md

### 17.1 B2 投递方闭环 ★已解★(深夜二批,详见 REPORT_cp_fw_af_execution.md §四)

JobDispatcher 投递方=同步直调三路:
- **LC::Lens::onMoveFcCmdIssued(FUN_00428324)**:4 槽环@0x15f3790 → cmd3(addMoveFc);
  上游=①**LC::Lens::mix_in(FUN_0043242c)** 每 LC vsync 出队 Mount_AM 命令环(14B/条,
  锁 DAT_0121ae88;运行时注册任务,静态零引用) ②**LIF::BL_ASYNC(FUN_004520a8,字母命令
  0x41-0x61,发送 API FUN_00451f14 有 19 调用方)**;
- **FUN_00ae51de**:镜头信息 6 字+有效标志 → cmd6;上游=FUN_004339e0(LB:INFO2 处理)
  ← drv::UpdateLensData(FUN_00403730) ← FUN_00a7435c(任务入口)。
- 0x170B 包 = **0x170 字节 Buffer**(fc_lib_message.cpp,池/队列 ID 0x90060197,osal_snd_msg
  →UIPC 0x0197);同队列承载 0xc80(AdamProcessManager)/0xd80(FeatureScalar oneshot)。
  **appFw(AP 侧 98420 函数)零 FW:/LiroSeq/Lens 命中 → FW 层全 CP 驻留,"CP 内闭环"成立。**
- BL 命令名空间:ID_BL_CMD_{MOVE_FC_2,MOVE_FC_CAP2,POS_CYCLE_A,FC_DRIVE_CYCLE};
  镜头侧日志 "pGLC: Lens: [BL]..." 为 bx lr 重叠伪影,实打印 **"LC: Lens: [BL]..."**
  (与 LC::Lens 模块名一致,详见 NOTES_ENUMS_NAMING.md §6)。

### 17.2 B3 PDAF/ZPD-DFE-Mario ★接口面已解★(详见 REPORT_cp_fw_af_execution.md §五)

CheckSetFocalPlanePhaseDetection(LiroSeq 校验)+FW: handler → RAM 0x1503790。引擎全栈(RTTI):
传感器 ZPD(mtg_set_zpd_* 寄存器/pbl_clkctl_zpd 时钟)→CamCore ZpdPre/ZpdAif/IifZpd/
ZpdDcSetter(眼图+瞳数)→**DFECore**(Ifmt/Det/Corr{MarioPg,Pga,Dc,Rpo,...}/Cow/Img 全寄存器面,
loadDefectPos→DMA330→DDX SRAM)→LC ZpdMarioSequenceData/LcZpdResultInfo/**MarioAfcState
状态机(Nop/MoveToPeak/Wait/Locked/Approach/Tracking/Scan/Search/Stop)**→FC ZpdInfoManager/
DefocusInfoGenerator(IFE)/DefocusInfoTranslator(IFE)/SegZpdData→[DefocusFace]/[DefocusKeypoint]
判定族→接 B2 链。nflasha18(/lens)校准流:16B 镜头名匹配器(0x564334,fixed_lensfile 内置回退)
→镜头 DB→DFE Corr*/DDX 表加载。

### 17.3 B4 AE/AWB 模块面 ★已解★(详见 REPORT_cp_fw_af_execution.md §六)

EC=Exposure Control(~80 cpp:EC_CaptureRaw_CalcAe/CalcExpose、EC_AESchedule、EC_AgcDrv、
Mode/EC_StateMachine、EC_ContAllot_{Cam,Dsc,ProCam}、EC_IrisAutoManualController、
EC_ElecShutter_Main、EC_Detect{Get,Set}IDT=IDT 人脸联动面部优先 AE、EC_MainObject=主主体联动);
统计硬件 CUC_CAM0_ATRCAE/DET_CAE(分区直方图+可编程测光窗);WB 硬件块 ArcWb/NrsWb/SigWb/VatrWb
+CC: CalAwbAim(raw 域 AWB 目标)+CalcStrbWBContPreDet(闪光 WB);AWB 估计全 CP,appFw 仅菜单面。

### 17.4 PID 官方名对齐 ★已解★(Block C-2,2026-10-12)

appFw 属性注册表(370 PID+215 NID,appfw_pid_nid_registry.tsv)与 CP 358 条描述符表对齐
345 条→**fw_pid_registry_named.tsv**。AF 关键名:0x4002 SET_AF_LIGHT、0x4005 SET_SPINAL_REFLEX、
0x4047 SET_EYE_START_AF、0x40fd SET_EYE_SELECT_MODE、0x40ff SET_TRACKING_EYE_SELECT_MODE、
0x4102 SET_EYE_AF_MODE、0x4103 SET_DETECTION_TARGET_MODE、0x4104 SET_ANIMAL_EYE_FRAME_MODE、
0x4105 SET_MOVIE_EYE_AF、0x415f SET_DETECTION_SETTING、0x4180 SET_DETECTION_AUTO_TARGET;
通知 NID_EYE_SELECT_STATUS(0x20a2)/NID_TRACKING_EYE_SELECT_STATUS(0x2071)/NID_EYE_BLINK_INFO。
§十 result_sender 的 0x170B 包名=0x170 字节 Buffer(误名),主体结果消息 type=9/10(REPORT_interchip
§二点五)。

## 十八、优先级判定(部位选择)★已解★(详见 REPORT_priority_judgment.md)

**类别→部位分发(FUN_00302b40 judgmentInclusion)**:判定前有"类别==当前 AF 目标"检查;
类 1/2(人/动物/鸟)按 XHD 子类 [0x5a] 分 5 组;3/4/5/8→InsectAndAirplane;6→Train;7→Car。

**部位优先级静态表(二进制 dump 验证,0xFF 结尾)**:
| 主体 | 优先部位顺序 |
|---|---|
| Eye(子类0/XED) | [1,2,4] 首个 CURRENT 命中者胜,终选 4→补判 3 |
| Head1 | XED 扫描 → XHD[2,4] → 补 3 |
| Head2 | XHD 1 → XED → XHD 4 → 补 3 |
| Body1 | XHD[4,2,1](部位 4 全败→整组放弃)→ XED |
| Body2 | XHD 3 → [2,1] → XED |
| Insect/Airplane | 子类 3→部位 1,否则部位 3(无回退) |
| Train | 子类1→[2,3]、2→[3,1]、3→[0,2,1] |
| Car | 子类1→[3,2]、2→[3,1]、3→[1,2](部位 3 全败→截断) |

**判定原语**:接受 = IoMin(交/min面积)≥阈值 + **锚点包含**(部位 1 须命中头锚点 P1(+0x60)/
P2(+0x74) 任一;其余部位须罩住躯干锚点 P3(+0x88),边扩=宽×比例×½)。
平局:无基准→IoMin 大者;有基准→score 小/距离小者。**阈值全部运行时配置(RAM 0x1F1DEE8)**。
best 维护:updateBestResult 产出 DROP[5]/INDEX[5]("Use Prio_result" vs "Use XhdData")。

## 十九、收尾清单

- [x] 六种搜索模式区域生成 + 跟踪状态机
- [x] 优先级判定(部位表/锚点/IoMin 判据)
- [x] HumanCross 交叉仲裁(配对表/HH-HB-BH-BB/df 前后判定/全部消费方,详见 REPORT_human_cross.md)
- [x] XED/XHD 命名来源、FoundStatus 官方命名等枚举语义(详见 NOTES_ENUMS_NAMING.md:
      KeypointXedResult/XhdType 0-7/FoundStatus=(aed==3)?2:(stpl==2)?3:(aed==1)?1:0/
      AedConfidence∈{0,1,3}/AedDrv 与 aed_dic/Mario=ZPD-DFE 散焦引擎代号)
- [x] priority_defocus_subject_selector.cpp(景虚化选主体,详见 REPORT_defocus_subject_selector.md:
      Movie LockOn/Subject 下 PreTopFace 脸/头/躯干三区 PreFaceIsInLockOnRange(min_df) 判定,
      getMinAverage/MinReliableDefocusFace 终选,curr_top 提升为主主体链表头)

> 全部详细报告:REPORT_adam_sequencer_subject_eye_staple.md /
> REPORT_result_calc_frame_selector.md / REPORT_search_region_track.md /
> REPORT_priority_judgment.md / REPORT_human_cross.md /
> REPORT_defocus_subject_selector.md / NOTES_ENUMS_NAMING.md

## 二十、MINNA/SaIp 引擎家底盘点（2026-10-11，RTTI/字典实证）

**MINNA = Camera::Minna 命名空间,统一驱动模板 SaIpDriver_base<Drv,IF,Param,Result,Listener,In,Out,N,M>。
SA-IP 是"换字典即换任务"的固定功能小网引擎(封套 ≤568KB/字典)。**

α1 在用引擎(6):Keypoint::Aed(aed_dic1/2)、Keypoint::Aed2(aed2_dic1/2+s2f×2)、Keypoint::Bed(bed_dic1/2)、
Fdn(fdn_front/side_dict,正/侧脸两本)、Pdn(pdn_dic)、Drt(udrt_dic1/2 推断归其用,用途未标识)。

**α1 II 多出的引擎(2,即"可供添加"清单核心)**:
1. **Scd/ScdDrv**(scd_dic1/2/3=450+21+21KB,车辆/火车/昆虫/飞机分类)——
   ★RTTI 实证 SaIpDriver_base<ScdDrv...> = **SA-IP 引擎执行,修正此前"scd 绑 ADAM"结论**;
   字典在 SA-IP 封套内,文件在手(α1 II 固件即有)
2. **Staple/StapleDrv**(tagSA_STAPLE_IO_ALLES)——STAPLE 跟踪的 SA-IP 封装(α1 走 IDT 路径),
   证明 SA-IP 可跑相关滤波跟踪

缺口:①提案源(α1 II 由 ADAM ObjectDetect 供候选框,α1 无)②sa_sabin_cp_cam_post.bin 两台不同
(1921536 vs 1906176B,SA-IP 配置包适配未知)③scd 分类字典文件 α1 分区未装(文件在手)。
免费午餐:α1 appFw 的 remote API 已有 bird/insect/plane/car_train 全套 sensitivity/subject_shift_range
属性管线(菜单未暴露);recognition_target 属性通道在。
引擎侧 Auto 挡实证:模式枚举 mode:Bird/Animal/Plane/Vehicle/Insect/Animal&Bird +
`[AUTORECOG] ** SingleRecog->AutoRecog!! **`(CP 内单目标→自动识别执行态切换)。
