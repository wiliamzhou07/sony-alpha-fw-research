# α1 II 固件：AdamSequencer(NPU 调度)→ 主体/眼选 → 结果发送 分析报告

**重要前置发现(影响任务2)**:`a1m2_adam_app.c` 是 Adam 协处理器自身的裸机固件(0x0 起异常向量表)，Ghidra 反编译中**没有任何 s_ 字符串标签**(grep `s_`、带引号字符串均为 0),且多个大函数带 "Control flow encountered bad instruction data" 警告。因此“adam_app 模块清单”无法从该文件字符串得出；真实可用的模块名全部在 CP 侧 `a1m2_cpapp.c`(所有 `s_adam_*.cpp` 字符串都在这里)。以下如实按两部分报告。

---

## 任务 1:AdamSequencer 簇(0x15b608–0x15e914+)

源文件字符串:`adam_sequence_manager.cpp`。管理器全局上下文约在 `DAT_0131f1d0`,队列 `DAT_011c9970`。

**逐函数语义：**

- **FUN_0015e914(初始化内存布局)** — `AdamSequencer::memory_alloc`。一次性切分 Adam 工作内存，字符串逐段打印布局：
  - `input_data ×10` 块，stride 0x2b300(每块有效 0x2a300,1KB 对齐)—— 输入图像帧环(10 深)；
  - `img_reid_out ×8` 块(stride 0x6000)—— ReID 512d/64d 输出，8 份对应最多 8 个检测主体；
  - `img_pose_out`(连同 `paf_map:%llx, head_map:%llx` 一条日志打印)—— S0 姿态网输出(19ch 热图+40ch PAF,见 NOTES_NAB_REVERSE.md);
  - `param_pose-reid-reid_sim`(三连 buffer,间距 0x4200)与 `param_scene`(+0x4700)—— 各子网的推理参数块；
  - 末尾 `size_over!!` 检查(超容量则清空 param 区)。
  - 该布局与 default.nab 的 17 子网 IO 对应(S0 姿态链 S7–S16、S1/S2 ReID、S3–S5 人脸、S6 眼、S11/S12 分类)。
- **FUN_0015e1a4(Adam::SetInputImageInfo)** — 帧入口。先过 FUN_0015e028 的 **API order-stop 门**(标志 DAT_019adf31–34,停机后拒绝并停队列)，否则 FUN_0015ddac 把 0x68 字节 PrcInfo 压入 **4 深环形队列**(字段：+0x54 缓冲句柄、+0x58 帧 id、+0x5c/+0x60 地址、+0x64 flag);**队列满 → `PrcInfo_reject_re…` 日志并释放缓冲**(FUN_002a8620)。真正写入方是 `SyncUtilityAdamSeq.cpp` 的 FUN_00bc453c(打包 0x50 字节帧信息后调用)。
- **FUN_0015c0f0(逐帧模式判定)** — 读 mode(=PrcInfo+0x2dc,1–5):mode1–3 调 `FUN_002a5ca0`=**Adam::AdamExecRequest**(fc_api_adam_sequence.cpp,pose 判定)；mode4 调 thunk_FUN_00a64bee;全部还要过 `FUN_0023f4e4`=**CC::GetAdamProcessRequest**(reid/scene 判定，字符串 `_ADAM_/_PARA_/_REQU_/_SW_` 四种失败)。产出 4 个子网使能位(+0x2ed/+0x2fd/+0x30d/+0x31d)和 `m_mode_info_now`(=三者最大分辨率等级，+0x328)。FUN_002a5ca0 内部：mode∈{1,2,3};按 SW 状态分派 AdamProcessManager;写硬件寄存器 `FUN_00850602(0x13,…)`,发 **msg 0x1700**(资源请求)，输出所需 buffer 等级(4K 单位表)，另有 99000 tick 帧间节流。
- **FUN_0015bccc(建序列请求)** — 从 PrcInfo 项(0x68 图像描述符)+ 模式块(0x58B)拼一个序列节点，`[0x17]=0x14`(疑似 20 帧超时)，入 RequestQueueManager(FUN_00154dbc:全局 0x16408d4 起的队列数组，环容量在 0xd9d35c,溢出打 `Sequence_ER`)。
- **FUN_0015b608(AdamSequencer::Callback)** — 子网完成中断回调，`param_2 = 通道号 0..2`(**3 条请求队列**，每条 7×0x1c 请求环，头索引在 +0x3bc+ch*4):
  1. 校验完成状态 ∈ {0,2,10}(位掩码 0x405),非法 → `Callback_Error_ap…` 并置全局错误 +0x12dc=1;
  2. 执行该请求的回调 `*(+0x3e4)(status, mgr+0xc0)`(结果搬运/后处理钩子)；
  3. 清依赖位：帧级掩码 +0x644 &= ~请求[+0x3dc],序列级 +0x3a8 &= ~请求[+0x3d0];
  4. **帧掩码 0x644 归零 → FUN_0015b7dc**;**该通道请求环空(+0x3d8==0)→ FUN_0015b994**;最后可选触发总回调 `*(mgr+0x3a4)()`。
- **FUN_0015b7dc / FUN_0015b994(StartPRCImageTransDirect / Parallel)** — 在 4 项区域表 `DAT_00d89120` 里查当前帧(地址，大小)所属区域算 DMA 偏移；查不到则走 `FUN_00152218(…, s_StartPRCImageTransDirect,0x10)` 兜底；随后 `FUN_0068b068(mgr,0,3|0,1,0)` 取传输描述符、`FUN_00687302/00687204` 提交(完成钩子 LAB_0068ae4e/0068adee),最后向队列 0x11c9970 发 type=5 事件(Direct 子类型 0x18,Parallel 子类型 6),日志 `AmS_PRCImgTransD/P:%04X`。即：**一帧最后一个子网完成后立即启动下一帧图像搬运，Direct=查表直映，Parallel=兜底并行通路**(两条路径的物理差异未能进一步确认)。
- **FUN_0015bfc8(CancelSequence)** — 对 3 条通道逐一释放未完成请求(数组基 0x3cc/0x458/0x4e4,≤7×0x1c),置 +0x3f=1,日志 `AmS_CancelSequence`,发 type=9 事件。
- **FUN_0015cca0(PowerSave_Execute)** — 帧间节能：负载 `uVar5`(日志按 uVar5>>0xc 打印)满足 `uVar5<0x1e000` 或 (`uVar5<0x3c000` 且空闲 `uVar4<56000`µs) 或 (`uVar5≥0x3c000` 且 `uVar4<22000`µs)时执行 `PowerDown_CmdExec`,注册掉电命令并广播；有序列在跑则改为回调 (3|4) 中止。空闲阈值数值确定，但 56000/22000 的单位与方向(µs 自上次执行起)为推断。
- **FUN_0015b424 / FUN_0015b3d8** — `AdamDriver::Sens` 注册 Adam 硬件中断(0x92f00961)/ Test Sandbox。
- 0x15fxxx–0x162xxx 是 **OctalSPI Adam flash 驱动**(`OctalSPI_Adam_hw_init/cpu_4b_write/Adam_ReadStatusReg/Adam_SoftReset`)——Adam 协处理器固件经 OSPI 加载，与调度无关。

**编排结论(伪代码)：**
```
每帧: SyncUtilityAdamSeq → SetInputImageInfo → PrcInfo环(4深,满则丢弃+还缓冲)
Sequencer: mode判定(AdamExecRequest pose / CC::GetAdamProcessRequest reid+scene)
        → 生成序列节点 → 3通道×(≤7)请求环, 请求带依赖位图
        → 经 OSAL 消息(0x1700 等)+共享内存(DMM, ConvCetusVA2AdamPHY)发给 Adam
每个子网完成IRQ → Callback(ch): 状态校验{0,2,10} → 结果回调 → 清依赖位
        → 全部完成: StartPRCImageTrans(Direct) 启动下一帧搬运; 通道空闲: Parallel
帧间: PowerSave 判定; 停机: API order-stop 门
```
“哪个网先跑”：显式静态优先级表未直接暴露；可确认的次序约束是——输入图像先到(input_data 环)，**S0 姿态链是每帧首选执行网**(AdamExecRequest mode1 直通路径 LAB_002a4638),姿态输出(img_pose_out/paf_map/head_map)与 ReID 输出(img_reid_out×8)按依赖位图串接(NOTES:姿态链 S0→S7→S8/S10/S14→S9/S13→S15/S16)。3 通道并发 × 位图依赖是编排机制本身。

---

## 任务 2:adam_app 与 FC::Keypoint 接口

**CP 侧 adam 模块清单**(来自 cpapp 字符串，`s_<file>_cpp`):
`adam_drv_api.cpp`、`adam_drv_request_manager.cpp`、`adam_drv_utility.cpp`、`src_adam_driver.cpp`(驱动层)； `adam_sequence_manager.cpp`、`adam_sequencer_adjust.cpp`、`adam_sequencer_utility.cpp`(调度层)； `adam_process_manager.cpp`、`adam_fr_manager.cpp`、`adam_command_param_manager.cpp`(业务层)； `fc_api_adam_sequence.cpp`(FC API); `proxy_adam_proxy_ospi.cpp` + `controller_adam_{gpio,ospi,spi}_controller.cpp`(传输/控制)；另有 `SyncUtilityAdamSeq.cpp`。

**Adam 侧(adam_app.c)可确认的结构证据：**
- `FUN_0002e3d8`:写魔数 **0x8010e02 / 0x801022c** —— 与 NOTES 里 NAB 块头加载地址(0x08010E4F/50)同族 ⇒ 这是 **Adam 侧子网二进制(NAB 块)装载/解析器**；
- `FUN_0003ded4`(最大，1105 行)：入参强校验(尺寸上限 0x4000/0x270、对齐 0x10),失败清 `_DAT_0febc854=0`(状态寄存器)返回 3;产出 **17 对 (float,float)**(0x3f000000=0.5、0xbf000000=-0.5 参与缩放)—— **17 关节姿态关键点解码**(COCO17);输出坐标减 0.5/加 0.5 的归一化痕迹。
- `FUN_000702ec`(9 参数)：多输入后处理(疑似 PAF/热图→关键点)。
其余因无符号、无字符串、反编译损伤，**不再进一步命名(不臆测)**。

**与 FC::Keypoint 的接口(均在 CP 侧，证据充分)= 共享内存 + 消息 + 中断三件套：**
1. **共享内存**:`Camera::FC::Keypoint::AdamParamMgr`(FUN_002f8acc–002f9778,断言文件 `common/driver/adam_keypoint/adam_…`):Initialize/Validate/Invalidate/Finalize、`Adam_AllocAdamMemory`/`Adam_FreeAdamMemory`/`DMM_AllocNew`(日志 `ERR_DMM_*`),`AdamPrmMgr::cetus_va_base_addr` + `ConvCetusVA2AdamPHY`(FUN_002ce0ec)——**DMM 分配、Cetus VA→Adam 物理地址转换后交给 Adam**;
2. **消息**:OSAL msgq(FUN_00852f78 分配/FUN_002bee3c 取块/FUN_0085307c 发送)，已见命令 id:0x1700(资源/参数请求，应答带 resource id 数组，校验 `Resource_id_mismatch`/`Number_of_resource_i…`,FUN_00156ea0)、0x210(STAPLE 批启动应答)等；
3. **结果回传**：Adam 写结果到约定缓冲(FUN_0015e914 布局)+ IRQ(`AdamDriver::Sens` 注册的回调 FUN_0015b608 簇)；CP 侧 **AdamFrManager::loadDetectionResult(FUN_002a4148)** 从暂存区 `DAT_013b4c20`(头部 +0x7e0=检测数，≤8;每条 0xfc)导入主体结构(0x498/主体)，关键点三组 9B 元组在 +0x38c–0x3bc,浮点 /1.25 归一化；随后 `REGISTER_TRACKED:is_succeeded` 注册 tracklet;回调 `AdamPrmMgr::cb_getAdamResultPar`(FUN_0084088e)。

---

## 任务 3:主体选择 / 眼选(TrackingEyeSelector)

文件:`fc_alg_tracking_eye_selector.cpp`、`fc_lib_if_flash.cpp`。**二进制内不存在 "EYE_SELECT_MODE" 字符串**；实际接口名是 `fc_get_if_tracking_eye_selector` / `fc_set_keypoint_…`。

- **FUN_002bd31c(fc_get_if_tracking_eye_selector)**:mode∈{0..6} → 5 张 flash 阈值表(0x198bdde 基址，步距 0x200):mode1→A(0x198bdde),2→B(0x198bfde),**3→条件表(子参==2→B,==1→A,其它回 A)**,4/5/6→C/D/E;mode0 → 断言错误。每表拷 8B:{u8 ratio_a, u8 ratio_b, u16 size_max, u16 size_min, u16 size_min_hard}。setter 是 FUN_002bb374(同 switch 逻辑，写全局 DAT_011e8be8),由设置层 FUN_008515ea 调用 —— mode 来自相机设置(菜单枚举名不在本固件，未能恢复)。
- **FUN_0029e9c0(阈值插值)**：输入表 {a,b,c=size_max,d=size_min,e=size_min_hard} 与人脸尺寸 s:
  - 断言 d<c(`face_size_m…`)、b<a(`lower_ratio`);
  - s < e → 返回 0(脸太小，不参与眼选)；
  - s ≤ d → thr=a·s; s ≥ c → thr=b·s; d<s<c → 线性插值 `a·d + (s-d)·(b·c-a·d)/(c-d)`;结果 `>>4`(定点 /16)。
  即**眼选接受半径随人脸尺寸线性变化**，小于硬下限直接淘汰。
- **FUN_0029e8bc(TrackingEyeSelector 主判定)**：
  ```
  if (mode==0) → 日志"can't use fo…" 返回 0
  thr_tab = fc_get_if_tracking_eye_selector(mode, *(face+200))
  okL = FUN_00839ff2(ctx, 0, *(short*)(face+0xda))   // 左眼可用性
  okR = FUN_00839ff2(ctx, 1, *(short*)(face+0xda))
  if (okL && okR):
      dL² = (eyeL.x - fx)² + (eyeL.y - fy)²   // eyeL=(face+8,+10)
      dR² = (eyeR.x - fx)² + (eyeR.y - fy)²   // eyeR=(face+0x34,+0x36)
      选距离较小者(平手→右眼候选路径)
  elif okL: 选左; elif okR: 选右; else: 返回 0
  选中者再过 FUN_0083a040: 距焦点距离² ≤ FUN_0029e9c0(阈值表, size)² → 返回 2(选中), 否则 0
  ```
  **选眼规则 = 距当前对焦点最近者胜，且必须落在按脸尺寸插值的接受半径内**；单眼可用直接选该眼。FUN_00839ff2 里还带一个基于 FUN_00852368() 上限的左右符号校验(参数 +0xda 为带符号偏移，语义未定，存疑)。
- **跟踪侧眼选**(区别于 AF 侧):`src_eye_selector.cpp` FUN_0086ec44(HUMAN_MOT::ALG):两名候选均 valid 时，比较 `FUN_00802774(candA+0x1c, candB+0x2c)` vs `(candA+0x1c, candB+0x34)`——**离参考点(+0x1c,疑似脸/焦点中心)更近者胜**；另 FUN_0037c4fc `YcInfoEye::isIgnorableEyeSelectI…`:标志(+0x1ef)置位且(计数 0 / 上下文标志)时忽略眼选结果。

---

## 任务 4:STAPLE 跟踪器与 HUMAN_MOT

**名称澄清**：全固件(含 avcam)grep 不到 `CalcOcclusion`/`JudgeSetInitPos`/`STAPLE_INIT_POS`;最接近的实存符号是 `JdgStapleinit`(=Judge Staple init)、`ManageIsSkipUpdateInitPos`、`sendTrackingInitPosition`、`ErrorStaple_overlap_ratio`。STAPLE 引擎本体由 `fc_drv_staple.cpp` 驱动(FUN_00294070 提到 `DDL_MINNA_Staple` —— 独立跟踪硬/固件单元)，批量启动：

- **FUN_002b7b40(ProcessStaple 批启动)**：日志 `Staple_Bulk_start_num:%d`;参数数组 stride **0x228**/tracker(+0x1ec 矩形、+0x214 id);引擎未初始化(`not_staple_Initi…`)→ 每 tracker 置状态 3 并报错；否则 vtable+8 发消息，回包 {u16 0x210, u8 1, u8 ok, u8 num, 每 tracker 6×u16(矩形+id)} 经 FUN_00853292 发出。
- **遮挡/放弃判定(src_staple_result_updater.cpp)**:
  - FUN_008766ae / FUN_008766ca(`ErrorStaple_overlap_ratio:%d,%d`):遍历 tracklet 环链(跳过 id==-1 与“自身”)，对 STAPLE 结果的每条检测项(计数 *param_3,stride 0xb0,双标志 +0x20 与 +0xb1)计算其矩形(类型2用 tracklet+0x14/+0x18,类型1用 +0xe4/+0xe8)与跟踪矩形的**重叠率 FUN_0085085e**,`阈值(虚表+0xb0) ≤ 重叠率 → 返回 1`(被遮挡/与他者重叠)。两个函数只差矩形字段组(=两种 part 类型)。
  - FUN_002dfe54(`_Giveup_ErrorStaple:%d,%d`):虚表 +0xb8 位掩码决定启用项；bit0→overlap 检查(FUN_008766ae);bit1 且未重叠→FUN_002e001c(ErrorStaple_normalize_parts_pos)再判，失败则清 +0x20/+0xd0 并**放弃本帧**。最终把 2bit 状态写入 `trackctx+0x15b9 + frame_idx*0x458`:`bit0=重叠, bit1=放弃`。
- **初始化位置判定(fc_alg_staple.cpp)FUN_00832e94(`_ManageIsSkipUpdateInitPos__new__/is_s…`)**:
  ```
  条件: FUN_0085243e()==1 && ctx+0x1888 && ctx+0x1b0 才评估
  在 10 深历史环(ctx+0x1894, 项={id, x, y, …})中找当前 id(先查 DAT_017025b4 表)或 id 最接近项
  用 FUN_00835940 按 (ctx+0x18a0: 0/1→kind6, 2→7, 3→8) 合成当前矩形
  若合成矩形越界(宽/高为负)或 存储的 init 位置 ∉ [x, x+w]×[y, y+h] → skip=1
  → ctx+0x193c = skip;  日志打印 (init_x, init_y, rect_x, rect_y, rect_w, rect_h)
  ```
  即 **STAPLE 初始位置更新跳过规则：一旦此前记录的 init 位置跑出当前跟踪矩形之外(目标丢失/漂移)，则不再更新 init 位置**。
- **结果落地 FUN_002e09f8(TrackingStatus::updateStapleResult)**:对每条项(stride 0xb0)把当前矩形(+0xb8..)+第二矩形(+0xc4..)写入 tracklet(+0xc/+0x10/+0x1c/+0x20),valid 位置 1;part 类型(+0x28 经 FUN_0087c85c 映射，<4):**类型 0 只写当前，1/2/3 额外写入历史槽 0/1/2(+0x48/+0x88 起，0x10 一步)**，并置状态 7;类型 1 另记 +0xcd/+0xdc/+0xec(人脸侧)，类型 0 记 +0xcc/+0xd4/+0xe4(体侧)，`+0xf0/+0xf4=3`。日志 `Staple_update:…` 12 字段。
- **tracklet 管理**：
  - 注册：AdamFrManager::loadDetectionResult(任务 2)→ REGISTER_TRACKED:is_succeeded;按处理类型 2/3-4/5-6 走不同注册路径(FUN_0083fe1a/FUN_002a2708/FUN_0083ff82),注册项 0x18B {id, flag, …};
  - 距离校验:`src_tracklet_handler.cpp` 簇 —— `isSameHumanViewOfDistance_trk_id…`(FUN_002e4330)、`calcDistanceOfTargetFace/Body`(FUN_002e4a64/002e4ba8,`df_best/dfs_count/miniBody/neck…`)、`getNearestDfIndexFromPoint`、`adjustAndCheckDfPointIndexWithin`、`ConvertBeta8_24toDistance32`;
  - 子序列跟踪:`src_phase_track_controller.cpp` —— FUN_002eaf10 `TrackController::SubSeq::Init`(取前 2 个候选：valid flag+0x20、中心 ×2(+0x30/+0x32>>1)、type+0x28、+0x65 权重、矩形 +0x38–0x42、+0x6c,半分辨率发送 `sendTrackingInitPosition…` 两条日志)；FUN_002eabd4 `::Track`、FUN_002eb2a4 `::Train`、FUN_002eb39c `setPrcInfo_for_subseq`;FUN_0087fa42 `getStapleInitResult_for_subseq` 把 init 结果写回 FC(+0x1348)并清待定标志；
  - 训练:`src_parts_trainer.cpp` `HumanStaple_init0/init1/train0/train1`(FUN_002d9d40)与 **FUN_002d9fbc `JdgStapleinit`**(字典有效性:+0xfc 使能、+0x108≥0x30、+0x250 状态==1;再按 param_2+0x28 子模式 1/2 与 `=='\a'(7)`、+0x44c==3 等判定是否(重)初始化 —— 细分支较深，语义为“判定 STAPLE 部件字典是否可用于 init”,细节存疑)；
  - 删除：未找到显式 "DeleteTrack" 字符串；tracklet 节点以 id==-1 作空槽标记(FUN_008766ae/ca、FUN_002eaf10 后段循环把 0x28 起数组整体清 0xff/0 —— 疑似注销路径)，删除的具体触发函数未锁定(不确定)。

---

## 任务 5:result_sender(0x308ad0–0x309f54,process_post_result_sender.cpp)

**FUN_00308ad0(主发送)**，输入 param_4 = 逐帧主体结果结构，字段(日志逐条印证)：
| 偏移 | 含义 |
|---|---|
| +0x04 (u16) | full_count(`full_count 0x%04X`) |
| +0x1c (u32) | **main_subject_num** |
| +0x24 (u8) / +0x72 (u8) / +0x2c (u32) | subject id / part / disp_eye(`subject:%d part:%d disp_eye:%d`) |
| +0x70 (u8), +0x30/0x32 (u16) | **eyeL valid + 坐标** |
| +0x71 (u8), +0x34/0x36 (u16) | **eyeR valid + 坐标** |
| +0x9a (u8), +0x92/0x94/0x96/0x98 (u16) | **head valid + 矩形** |
| +0xa4 (u8), +0x9c/0x9e/0xa0/0xa2 (u16) | **body valid + 矩形** |

随后按 disp_eye(+0x2c)选参考点：1→param_2+0x74/+0x78 或 +0x60/+0x64(依 +0x72);2→head 中心 `x + w/2, y + h/2`(定点移位)；3→body 中心；非法值断言 `void Camera::FC::Keypoint::__anon…`(**该文件属于 FC::Keypoint 处理链**)。

**FUN_0089a694(→ AP 的 0x170 字节通知包)** 经 OSAL 消息发送，主要字段：
- +0x00 u8=0、+0x01 u8=9/10(类型，param_9 决定)、+0x02 u16=虚表+0x2c()(帧序号)；
- **le/re/head/body 四组 id 对**(u32 对，FUN_00884f76 等打包):+0x34/0x35(le)、+0x20/0x24? 实为 +0x20/+0x24 偏移即 puVar7[8]/[9](re)、+0x60/0x61(head)、+0x8c/0x8d(body);日志 `le:%d,%d re:%d,%d head:%d,%d bod…`;置零条件:param_2+0xa8(全局抑制)、对应主体 +0x120 标志、虚表+0x168(param_2+0x730)返回 1→body,2→body+head+eyes;
- **QVGA(÷2)几何包**：主体中心 +0x10/0x12/0x3c/0x3e(参数 float×0.5)、+0xc4/0xc6/0xc8(copyRawAnimalDataQVGA_HeadBody 输出，见下)+0x68/0x6a 与 +0x94/0x96 两组中心；10 组 u16 四元组矩形(+0x20/0x2c/0x44/0x4c/0x58/0x78/0x84/0xa4/0xb0/0xd8 起，全部 >>1)——左右眼/头/体矩形及运动框；part 有效字节 +0x36/+0x3e(=0x62/0x8e);
- +0xbc 标志(*(param_4+0x4e)==0)、+0xcc param_5[0]、+0xd0 u8 主体数、+0xe8 u32、+0xec u32、+0x168 u8;
- +0xf0 起 **FUN_00308f54 结果清单**:3 字头 + 5×{3×u32 + u16}(最多 5 个 part 的矩形+id)+ u32 + 4×u32 + u32(经虚表 +0xc/+0x14(idx 0–4)/+0x1c/+0x20/+0x24 逐项取出)。

**FUN_00309090(copyRawAnimalDataQVGA_HeadBody)**:对动物/主体 idx(0xff 跳过)，取 `track + idx*0x148` 记录；+0x140(s8)=选中 part 序号：=-1 → 用整体(+0x4c/+0x4e);否则 part 记录(+part*0x18)取 x+ w/2、y + h/2 → **输出 (x>>1, y) 写入包(+4/+6 相对基址)** —— QVGA 半分辨率头/体中心。参数 5(param_9)为“动物优先”开关(0 时用 param_4 兜底)。

**FUN_003099f8(优先级评分)**：按模式(虚表+0x1bc,1–4/default)组合 `主体中心到目标点距离²`(ctx+0x68/0x6c vs +0x7c/0x80)、`FUN_0089be00`、缩放/尺寸增益(虚表 +0x1a0/+0x1a4/+0x1a8/+0x1ac/+0x1b0/+0x1b4/+0x1b8),case 2/3 引入与画面边距相关的 0–1 权重(下限 DAT_00309e90),取 max 下限后返回 u32 —— 主体排序打分(公式细节未完全复原)。

---

## 合成：AI 推理调度 → 主体/眼选择 → 结果打包发送 链路

```
[VSYNC] SyncUtilityAdamSeq(FUN_00bc453c)
   └→ Adam::SetInputImageInfo(FUN_0015e1a4) ─ PrcInfo 4深环(满→丢帧+还缓冲)
AdamSequencer(FUN_0015c0f0)
   ├─ Adam::AdamExecRequest(FUN_002a5ca0)  → pose(S0 链)执行判定+分辨率等级
   ├─ CC::GetAdamProcessRequest(FUN_0023f4e4) → reid/scene 判定
   └─ 序列节点(FUN_0015bccc)→ 3 通道请求环(依赖位图)→ OSAL msg 0x1700
        + DMM 共享内存(ConvCetusVA2AdamPHY)→ [Adam 协处理器: NAB 装载(0x8010e02)+17子网推理]
每子网完成 IRQ → Callback(FUN_0015b608) 状态∈{0,2,10} → 结果回调
   → 帧掩码清零 → StartPRCImageTransDirect/Parallel(下一帧搬运)
   → AdamFrManager::loadDetectionResult(FUN_002a4148) 导入≤8 检测(0x498/主体, 关键点/1.25)
        → REGISTER_TRACKED 注册 tracklet
FC 处理(Keypoint 链)
   ├─ TrackingEyeSelector(FUN_0029e8bc): 双眼有效→距对焦点最近者;
   │    接受半径=按脸尺寸插值(FUN_0029e9c0, 模式表 0x198bdde+mode*0x200); 跟踪侧 eye_selector.cpp 同为"最近者"
   ├─ STAPLE(fc_drv_staple.cpp → DDL_MINNA): 批启动 0x228B/track;
   │    遮挡=与其它 tracklet 矩形重叠率≥阈值(ErrorStaple_overlap_ratio);
   │    放弃=normalize_parts_pos 失败(Giveup_ErrorStaple); 状态 2bit/帧/track;
   │    ManageIsSkipUpdateInitPos: init 位置出界→跳过 init 更新;
   │    SubSeq::Init/Track/Train + HumanStaple_init/train(部件字典 JdgStapleinit)
   ├─ tracklet 距离校验(src_tracklet_handler.cpp: isSameHumanViewOfDistance / calcDistanceOfTargetFace|Body)
   └─ 主体优先级评分(FUN_003099f8: 距离²+尺寸增益, 模式 1–4)
result_sender(FUN_00308ad0 → FUN_0089a694)
   └→ 0x170B AP 包: {type 9/10, 帧号, main_subject_num, le/re/head/body id 对,
        QVGA 矩形×10 + 中心, copyRawAnimalDataQVGA_HeadBody 动物中心, ≤5 part 清单}
```

## 不确定项汇总
1. `a1m2_adam_app.c` 无符号无字符串、多处 bad-instruction——其内部模块名、消息表、与 CP 的精确握手只能给出上述结构性证据(0x8010e02 装载器、17 关键点解码、状态寄存器 0xfebc854)。
2. AdamSequencer 3 通道的物理含义(3 条 NPU 命令队列 vs 3 类 DMA 通路)未直接证实;Direct/Parallel 两条搬运路径的硬件差异未证实。
3. PowerSave 阈值 56000/22000 的单位与"自上次执行起”方向为推断;FUN_002a5ca0 的 99000 tick 节流语义同样。
4. 眼选 mode 0–6 对应的菜单枚举名(Auto/左/右…)不在这些固件文件中，只有 5 张阈值表与条件表逻辑；FUN_00839ff2 的 +0xda 带符号偏移语义未定。
5. tracklet 的显式删除函数未锁定(仅见 id==-1 空槽与 0xff 清槽路径)；JdgStapleinit 的分支细节未完全展开。
6. 父任务提示名 `CalcOcclusion`/`JudgeSetInitPos`/`STAPLE_INIT_POS` 在全部反编译文件中不存在，已用实存等价物(overlap_ratio/Giveup、JdgStapleinit、ManageIsSkipUpdateInitPos、sendTrackingInitPosition)替代分析。

**关键文件/函数索引**:`<workspace>/firmware_reverse/decompiled/a1m2_cpapp.c`(FUN_0015b608/15b7dc/15b994/15bccc/15c0f0/15cca0/15ddac/15e028/15e1a4/15e914、002a5ca0、0023f4e4、00bc453c、002a4148、002f8c08、0029e8bc/0029e9c0/002bd31c/002bb374、0086ec44、00832e94、008766ae/ca、002dfe54、002e09f8、002eaf10、002b7b40、00308ad0/00308f54/00309090/003099f8/0089a694)、`a1m2_adam_app.c`(FUN_0002e3d8、0003ded4)、`<workspace>/a1m2_ai_pipeline/cpapp_fun_index.tsv`、`NOTES_NAB_REVERSE.md`。