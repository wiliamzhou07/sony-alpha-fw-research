# Sony α1/α1 II 固件项目 — 完整状态档案（上下文压缩）

> 目的：一份自包含的项目状态，供上下文压缩后快速恢复。最后更新：2026-10-12（凌晨五）。
>
> **2026-10-12 凌晨五·C-6+ 三轮收敛：appFw 差分覆盖率 20%→88%（REPORT_a1_a1m2_appfw_diff.md §五）**：
> - 收敛曲线：R1 字符串/行集锚 32,903（19.5%）→ R2 调用图传播 57,709（34.2%）→
>   R3 LIS 单调地标链+区间顺序对齐 117,469（69.7%）→ R3b 数据地址分区线性插值
>   （0x6b 区 11311 对 IQR=0！vtable 级精度）127,151（75.4%）→ R3d 密集锚传播
>   （唯一未配对边直配+单票强约束）145,688（86.4%）→ R3e/f 贪心最优对 147,629 →
>   **R3g 终轮收敛确认 148,261 对（88.0%/84.5%）**
> - 方法发现：①两代 .so 布局=局部线性+连续漂移（偏移带 0x17-0x30，全局单调假
>   设错误——贪心 LIS 只剩 7 地标，真 LIS 43k→125k 地标）；②顺序对齐在分数噪声
>   下级联脆断，大间隔须用贪心最优对+偏移窗；③数据地址映射精度 IQR≈0 可直接翻译
> - **精度抽检（随机 400 对）**：尺寸比 0.75-1.33 占 97.2%（中位 1.00）、行集
>   Jaccard 中位 1.00 —— 配对精度 ~95%+
> - **剩余定性（100% 记账）**：a1 20,277/a1m2 27,349；两侧差 7,072≈总函数差 6,943
>   → α1 II 真新增 ~7k（尾部 0x30-0x34 区 1,917 纯新增）；a1_only 52% 聚集 0x24-0x28
>   =字段偏移已变的胶水/注册桩（5-20 行，特征法识别极限）；最后 12% 需语义级等价
>   判定（Diaphora 级），已列可选后续
> - 产物：appfw_diff_summary_v9.tsv（最终）+ 引擎链 diff_appfw_r2/r3/r3b/r3d/r3e/r3f/r3g.py
>
> **2026-10-12 凌晨三·C-6 a1/a1m2 appFw 函数级差分（Block C 收官，REPORT_a1_a1m2_appfw_diff.md）**：
> - a1m2 重导完成（**175481 函数/135MB**）；a1=168538（本解析口径/172190 计数口径）。
>   队列后续补跑完：**darwin_core.bin ARM32@0x0 重试成功**（1175 函数/818KB，上轮 0B 已解，
>   无字符串数值代码身份待查）；bonobo AARCH64@av-cam 基址仍 0 函数（1 秒假完成，基址不对，遗留）
> - **差分（diff_appfw.py 三级匹配：字符串锚/归一化行集投票/常量签名）**：匹配 32903 对
>   （全同 19072/有差异 13831），未匹配 a1 135635/a1m2 142578=两代同源小访问器
>   （"仅a1"与"仅a1m2"高频串簇几乎逐条相同、UIBiz_221H 两边都在 → 仅aX 计数≠新增/删除）
> - 结论：①两代同一 UI 框架（UIBiz_221H 同基线）+基础设施同源（REMOTE/BT/媒体/model_api）；
>   ②匹配对地址呈区域恒偏移（+0x183148 族）→ **α1 II appFw = α1 appFw + AI/UI 增量**移植模型成立；
>   ③真实差异：★a1m2 新增 `14mp_distributor`（adjust/senser.cpp）★、boot_start_seq 签名简化、
>   infra_wrapper_imaging 源文件重组、[REMOTE] 调试符号名化；万行级 diff=Ghidra 合并伪影（排除）
> - 产物：appfw_diff_summary.tsv / appfw_diff_modified_top.tsv / diff_appfw.py；
>   改进路径=调用图传播匹配（覆盖率 20%→60%+）；14mp_distributor 与 A 级 12 条 PID 发起方的关联待查
>
> **2026-10-12 凌晨四·"无 Adam a1 II"四项验证全绿（REPORT_no_adam_feasibility.md，B3/B4 会话）**：
> - **验证1 Aed2 = 活代码双引擎**：common/driver/keypoint_driver.cpp FUN_008897ba 按
>   tuning 单例(0x143ebe8) vtable+0xdc==1 选 Aed2(aed2_dic1/2)，否则 Aed 一代
>   (aed_dic1/2=α1 同款)；两套字典都在固件树；**Adam 只是提案源(StartAdamSetInitialRegion)
>   不是检测器**
> - **验证2 interchip diff = 传输/协议类同集**：UDIF 核心四件 .text 同(并行会话实证)；
>   协议类 0x2003/0x200d/0x8003 两台同集；result_sender 两台都有(a1m2 增动物 QVGA)；
>   真差异=45 PID/NID 族(A级12必须补)+13 NID 重编号冲突（基线会话已分级）
> - **验证3 XHD 恒空 = 优雅降级**：track_setting.cpp FUN_00314df8——置信度只在"XHD 存在
>   但 id 矛盾"时=0；**无 XHD 恒为 1/2，不触发 StartInit 死循环**；FoundStatus 不含 XHD；
>   HumanCross HB/BB 退化但 HH 存活
> - **验证4 beta = CP 从硬件 df+镜头校准换算**：adam_recognition_param_generator.cpp
>   FUN_002d38f0——df(ZPD→DFE)→FUN_00aaa0ea 查镜头结构(+0x128..+0x1b4)换 β→BetaSmoother
>   →发 Adam 中继回传；**Adam 不是计算者**；α1 原生有同款 β 串；XYZ 深度搜索输入存活
> - **路线甲打桩清单（9 项，详见报告）**：#1 Adam BOOT fail-soft≈0（原生：
>   BOOT_RDY_timeout→log→return，FUN_00152f24）；#2 结果缺失≈0（序列有界超时+置信度1/2）；
>   **#3 提案源切换 Adam→IDT = 核心工作量**；#4 引擎选择=tuning 配置；#5 PID 映射层
>   （13 冲突+12 A级）；#6 文件搬运；#7 tomco≈0（无需 192MB carve）；#8 机型码待验；
>   #9 硬件路线=共同前置
> - 遗留：#3 的 IDT→FC 接线现状；0x143ebe8 默认值；AdamSalvage 重试行为；机型码校验
>
> **2026-10-12 凌晨·appFw 函数级差分第一遍（α1 基线会话，appfw_func_diff_pass1.txt）**：
> - a1m2 重导完成 179292 函数/135.5MB；第一遍结构差：a1=168538 vs a1m2=175481 函数
>   （+6943）、串 10425/10974（a1m2 新 922）、cpp 872/909（a1m2 新 49 / a1 独 11）
> - a1m2 新增 49 cpp = 连接域重构 ~35（PC Remote 全家 *_re_arch/蓝牙 Classic/MFI/云/
>   流媒体 PTP/FTP-RTMPS 证书/SDI-HDMI，CT_ID_* 串族主体）+ 创作者功能（clip flag×4/
>   zebra/raw-only）+ **★infra_wrapper_aidictionary.cpp（AP 侧 AI 词典封装，α1 appFw
>   完全没有；adam_app 仅 a1m2 有）★**
> - ★移植结构性约束★：AI 功能 AP 侧入口（aidictionary 封装+scr7078/7181/7258 新屏控）
>   只在 α1 II appFw → **α1 原装 UI 无法开关 AI 对焦**，只能靠 CP 侧默认值/α1 既有菜单
>   映射新 PID/调试通道；A 级 12 条 PID 要点修正为"CP 主动 GET/SET 时 α1 appFw 必须应答
>   不崩（缺失属性容错行为待逆向）"。AI 相关 appFw 增量远小于 +6943 表面数字
> - §9.4 已按 C-5 的 scan_bl 修正更正（onMoveFcCmdIssued 4 BL=静态闭环、mix_in=
>   唯一运行时注册）
> - 下一批（α1 基线侧）：差分第二遍=AI 相关 cpp 函数级精对（aidictionary 封装全函数
>   提取）；A 级 12 条逐条发起方验证（与 C-5 的 Cons_FunctionNotify 注册表联动）
>
> **2026-10-12 凌晨三·B3/B4 收口（REPORT_cp_fw_pdaf_defocus.md，本会话）**：
> - queue_v2 完成验收：**a1m2_appfw.c=179,292 函数/135MB、a1_appfw.c=172,190 函数/129MB
>   （全量，10 万上限截断已补）；darwin_core.bin=ARM32（a1m2_darwin.c 1,242 函数）**；
>   bonobo 两基址 0 函数（遗留）；四份索引就绪（avcam×2+appFw×2=35 万函数）
> - **B3 PDAF/散焦链**：ZPD(pupil 配置 ZpdDcsetter setPupilNum/ZpdAIF)→FOPD 控制器
>   (ddl_fopd_controller,IP_TYPE 4 路分派)→DFE(dfeParam)→ADF(执行监视器)→df 分发
>   （Mario=ZPD→DFE 实证；算法在硬件，同 STAPLE 模式）；df 消费=JudgeDefocusFace/
>   lock-on 扩展(FUN_0012e730：df 阈值+beta 定窗口)/景虚化选主体；镜头数据=nflasha18+
>   镜头 ROM 经 Backup(BKID_LIF_LENSDATA)→LIF/Mount；SET_FOCAL_PLANE_PHASE_DETECTION
>   进 LiroSeq 参数面
> - **B4 AE/AWB**：AE=EC 家族（EC_AESchedule/CaptureRaw_CalcAe/IrisAutoManualController+
>   Lens_Iris* 机械光圈驱动+IrisDrivabilityData）；**face_ae_mode=LiroSeq 序列参数**（FC
>   主体结果同时喂 AF/AE）；ImportPackedRawByPcie=AP RAW 统计回流；PQD_DigitalGain；
>   **AWB=CP 无独立模块**（在 darwin ISP/avcam，归 Block C）
>
> **2026-10-12 凌晨二·C-5 LIRO 任务表解密（第四批，REPORT_cp_fw_af_execution.md §十）**：
> - ★**scan_bl.py 符号扩展 bug 发现并修复**★：S=0 时误用 I1 位（bit23）判符号 → I1=1 的
>   BL 全漏报。已修+capstone 全量线性反汇编（7.8M 指令/66 万边）交叉验证。修正结论：
>   onMoveFcCmdIssued 0x428324 实有 4 BL（调用者=mix_in 内 2 处+BL_ASYNC 内 2 处——
>   B2 投递链两路上游恰为其静态调用者，链条完全闭环无需运行时注册）；JobDispatcher
>   0x427948 调用者 5 族（ALH_lensAttach/onMoveFcCmdIssued/0xae3xxx 尾助手×3 含
>   setLensInfo tail-b.w）；快照器 0x94b662 有 1 BL（0x5250b8）；**mix_in 0x43242c
>   七路扫描全阴性=全 FW 唯一真运行时注册**（vsync 回调）；Cons_FunctionNotify=表驱动
>   （{id,fn|1,0} 12B 注册表@0xe452e0/0x11ea8e8，命令 id 0x2009-0x201b 族）
> - **LIRO 任务表=分派器代码内联 BL 链**（非数据表，故二进制中无入口指针字——
>   指针/ADR/B.W/BLX/TBB-TBH/movw-movt 六路全阴性的原因）。四链全圈定：
>   电源/唤醒链 runner **0x6d43f0**（Ghidra 漏标签，误并入日志函数 FUN_006d4398）：
>   0x1a00a8→0x1a0e78→0x1a1dac→0x1a37d0→tail 0x19ece0；MainLoop/boot 链 0x6d46c0：
>   0x19dadc→0x19e38c（"MainLoop Start"/"boot_fact.type"）；显示链 0x6d4b00
>   （yuvLayTableSize/play_Logo_ToDecode）；按键链 0x6d4cca（keymap/keycode）。
>   模块统一形状=ctx+0x10xx 状态槽三态子状态机（0=init/1=run/2=done），由 FW 消息
>   分派器 blob **FUN_0019d490**（0x19d490-0x19e644 4.5KB，Ghidra 只反了首块 44 行）
>   驱动：receiver 0x19e644 ← 内核尾分支 0x6d33aa 进入 0x19d490；内核胶水第二区
>   0x6d6000-0x6db000=LIRO_PMCB 电源管理（"unreg sync cb on LIRO_PMCB"）
> - **唤醒序列宿主实锤**：FUN_0019fedc=电源链第 5 模块（0x19ece0）的步进 5
>   （+0x110c 槽：0=Normal_Wake_Up FUN_0046a334→1=Fast_Wake_Up FUN_0046a5ac→3=done，
>   "is_Ee_Play"/"CmdEE false"）——§9.1 电源序列落位完成
> - **AF 大状态机三簇候选圈定**（§10.3）：①FW 模式/参数引擎=0x3dd000-0x3e4000 调用方+
>   静默函数族 0xa1e000-0xa24000（~300 函数全读 FW 上下文指针 0x1506738，零日志串）+
>   14-case tbh 模式分派器 FUN_003e1b08；②FW 主序列大函数区 0x524000-0x52cb78
>   （Ghidra 合并，含快照调用 0x5250b8）；③消息分派器 blob 0x19d490。
>   剩余：三簇中钉死 AF 模式机状态迁移表；mix_in 的 vsync 回调注册点
> - 新工具：scan_ptr.py/scan_adr.py/scan_b.py/scan_tbh.py + scan_bl 修正；方法论=
>   七路引用扫描+capstone 全量 xref 交叉，单工具阴性不下"无静态引用"结论
> - 后台：a1_appfw.c 重导完成（172190 函数/129MB）；a1m2 重导进行中（400k 上限）
>   →bonobo→darwin ARM32
> - 下一批：a1m2 重导完成后 **a1/a1m2 appFw 函数级差分**（Block C 收官项，与 α1 基线
>   批次的 A 级 12 条逐条发起方联动）；AF 模式机状态迁移表；mcmn 0x8028017c 上浮通道
>
> **2026-10-12 凌晨·α1 侧直接分析第一批（REPORT_a1_baseline.md，落点面）**：
> - **kmod 双级普查**：MD5 层 102/123 相同（独有=nfc/r8168 vs r8125 全硬件差异）；
>   .text 层 19 个差异 kmod 中 **12 个代码逐字节一致**（含 UDIF 核心四件 icdt/mcmn_drv/
>   osal_uipc/osal_ulogio——B7"传输层同版"升级为内核态代码级实证）；真变 7 个：pcie-if
>   （+968B，DMA API 重构 dma_execute→set_lli+start_dma）、upm(-14KB)、usb_beets/dmm/input/
>   kikilog/wlanIrq 小改
> - **appFw 属性注册表差分（移植风险面主发现）**：a1=547 条(PID342+NID205) vs
>   a1m2=585(370+215,与C-2复核一致)，共有 540；产物 a1_appfw_pid_nid_registry.tsv +
>   a1_a1m2_pid_nid_diff.tsv。三类：仅 a1 7 条（低风险）/ **仅 a1m2 45 条**（α1 appFw
>   无注册，α1 II cpapp 发出即丢——含 AI 对焦族 SET_DETECTION_SETTING(0x415f)/
>   GET_DISPLAY_POSITION(0x4160)/FOLLOW_FOCUS 族，移植必须补齐）/ **ID 重编号冲突 13 条★**
>   （NID 0x20a4-0x20ae 全族错位 + PID 0x414e/0x4152-55——换 cpapp 必须做 ID 映射层）
> - **avcam mcMsgIf 枢纽同构**：a1=FUN_ffffffc0010a01dc(9233B) vs a1m2=…0a1ef4(9488B)，
>   源地址 9/10 同、消息首字五类逐分支同、word1 子类型同——avcam 契约跨代稳定；
>   唯一 a1m2 新增源端点 0xd2fc0991 发送方未定位（无用户态构造点/无数据表命中，疑似内核侧）
> - **cpapp FW 层同构确认**：a1_cpapp 中 LiroSeq(22处)/setMoveFcCmd(6)/FC 队列
>   0x90060197(7)/ALH 家族全在位——两代 CP 同架构，支持整体替换 cpapp-b.bin 前提
> - **45 条独有 PID 移植分级完成**（续批，已写回 a1_a1m2_pid_nid_diff.tsv level 列）：
>   **A=12**（AI 对焦/检测族：DETECTION_SETTING/DETECTION_AUTO_TARGET/GET_DISPLAY_POSITION/
>   DEFOCUS_CONTROL_POSITION/BACKGROUND_DEFOCUS_CUSTOMIZE/FOLLOW_FOCUS 族/
>   AF_SPEED_SENSIBILITY/MF_DRIVE_IN_STILL_AF/BREATHING_CORRECTION/ISCN_LOCK）、
>   **B=8**（镜头/预置/遥控族）、**C=21**（α1 II 新功能，α1 菜单无入口天然休眠——
>   仅 TIMESHIFT NID 族在 CP 有 3-16 处活跃引用）、**D=4**（显示/视频）。机制注记：
>   45 条中 41 条在 a1m2_cpapp 零立即数引用（下界，描述符表是数据）+ 35 条在 CP 358
>   注册表内；真实风险面 = CP 主动发起的方向，GET_DISPLAY_POSITION 有 cpapp 侧
>   FW: 日志实证，逐条发起方留待换 cpapp 联调验证
> - a1 FW 状态块标定受阻：a1_cpapp 反编译文本仅 11 处 FW: SET 串直引（a1m2 199 处），
>   handler 簇 0x303xxx-0x305xxx 需 B1 式 capstone 直读——遗留
> - 下一批：a1/a1m2 appFw 函数级差分（a1m2 400k 重导进行中）；A 级 12 条逐条发起方/
>   降级方案；a1 cpapp handler 簇 capstone 直读（状态块标定）
>
> **2026-10-12 凌晨·C-3/C-4 完成（第三批）**：
> - **C-3 AP 队列分派全表**（REPORT_interchip_protocol.md §二点六）：avcam 接收骨架=
>   4 槽 mcTsk 任务（FUN_ffffffc0010a4398/4444/44e0/457c）→recv 循环(0x180B/条)→
>   **mcMsgIf 分派枢纽 FUN_ffffffc0010a1ef4**（源地址×消息首字双分派：0x61003c/0x9061003c=
>   内存共享 0x8021/0x8023、0x80c2019f/0xc20219=四路扇出、0x2103=六路广播、0x1000=RPC、
>   0x2003=codec、0x8003=系统查询/HW 版本、0x8021/8023=share/free async）；TSK_V_DNC
>   视频解码独立分派 0x200-0x221=INF_VIDEO_DEC_{OPEN,START,CLOSE,STOP,CHANGE_SPEED,RESET,
>   IMOLA_CREATE/REMOVE_CHANNEL,FATAL_ERROR}；mcObjectCtrl 4 槽×18 地址路由表全录
>   （0x8057 族低半字含通道 nibble：槽1=槽0 的 b13 位点亮 00f9→20f9）；appFw 注册面
>   5 项全名单（UTIMER 0x910040 两段式握手/ADJ 0x80870935/调试台 0x8087094e/
>   **senser 0x1050244+0x2170625**=adjust::senser.cpp 两回调）。
>   ★C-1 残留误判清正★："主体结果消费方在 appFw 队列回调族"作废——appFw+avcam 全量
>   扫描零 9/10 分派、零 0x90060197 → 主体结果从不离开 CP（CP 内闭环第三重实证），
>   AP 侧跨芯片消费只有 codec/显示族
> - **C-4 LiroSeq AF 序列本体**（REPORT_cp_fw_af_execution.md §九）：LiroSeq=CP FW 层
>   **电源+参数+AF 三合一序列器**——电源/唤醒序列（FUN_0046a334 Normal/FUN_0046a5ac
>   Fast Wake Up、Spinal on/off、16 键 backup@0x015fb6f0、唤醒码 1-11、trace 队列
>   0x8f013a）；参数序列（**Cons_FunctionNotify FUN_0037d284**=完成键接收主循环
>   "receive…before comp FAILED/QUEUEING"+SET_COMP 群+ParamCheckErr 30+ 参数族+
>   FW 状态块 0x1502ec8/0xf18B/指针 0x1506738/快照器 FUN_0094b662@mutex 0x26）；
>   AF 驱动序列（**BL 漏斗 19 调用方全名单**：LIF API 00451f14→BL_ASYNC 004520a8→
>   onMoveFcCmdIssued，LC::Lens Send_Pos_Cycle/move_fc_rejected、LENS_EC B2L_SWITCH_IRIS、
>   LENS_DRIVE_FREQUENCY、位打包发送器 0044d6c8、BL 电源状态机 0045036c 等；
>   **setMoveFcCmd sync(0x1d)/async 双体**=FUN_0042d778/0042d914，源命令
>   {cmd,+1 u16 位置,+3 单元,+4 flags(速度格式/半档标度 0x018da770/wob/shift)}，
>   唯一上层=addMoveFcCmd（BL 扫描 1:1 证实）；**AsyncVDLensHistory FUN_0042c2cc
>   11.6KB**=vsync 时基镜头历史/ALH 家族本体（FocusDriveEvent::do_merge 宿主）；
>   ALH_lensAttach FUN_004276d4=JobDispatcher 唯一静态提交方）。工具固化
>   a1m2_ai_pipeline/scan_bl.py（Thumb-2 BL 目标反查）
> - **appFw 补量第一段完成**：a1_appfw.c 重导成功 **172190 函数/129MB**（原 10 万截断
>   已破）；queue_v2 自动续跑 a1m2 重导（400k 上限，跑约 1-2h）→bonobo→darwin ARM32
> - 下一批：a1m2 重导完成后做 **a1/a1m2 appFw 函数级差分**；AF "大状态机"任务体
>   （运行时注册，需 LIRO 任务表/scenario 动态定位）；mcmn 内核面 0x8028017c 等内核态
>   UIPC 地址的上浮通道
> - 范围：只做 α1/α1 II（a9m2/A7M4 分区解密不在本轮）；硬件实测项等用户备料
>
> **2026-10-11 深夜·全量深挖计划启动（计划已批准，逐块推进）**：
> - 阶段 0 完成：**re_assets/**（314MB/478 文件，MANIFEST.sha256）= 两台 kmod 全集/appFw.so/
>   av-cam/bonobo/wole/adam_app/cpapp/sabin/scenario/darwin/loader_nor/libInfra* 持久化副本
>   （/tmp 解密树重启即失，现以 re_assets 为准）；新索引工具 a1m2_ai_pipeline/build_fun_index.py
>   （avcam 两台索引已建）；Ghidra 队列 queue_full_traversal.sh 已跑完小文件
>   （a1m2_liro/icdt/mcmn/pcie_if/pcieatu/pci_ep_cp/interchip/skd/loader_nor/bonobo 已出），
>   appFw a1m2 反编译中（/tmp/gh2_appfw_a1m2.log），darwin 0B 待复查
> - **Block A 完成**：REPORT_staple_reid_faceid.md（STAPLE 定界=相关滤波在 SA-IP 硬件,
>   CPU 只做 Hann 窗/参数/解包；ReID 全数学=64维欧氏距离-漂移基线-fmin0.2×100 存
>   tracklet+0x2288；人脸 ID=8 槽×0x570 注册表+judgeSwapFace/isFaceSwapPermittedByCross
>   全条件；IDT=NSX::Face 消息驱动+FDT 硬件双结果表 36/72 脸；眼选 mode=RAM tuning 块,
>   语义疑为闪光状态）。NOTES_ENUMS_NAMING.md §五、AF_LOGIC.md §八/§九已增补
> - **Block B 第一批完成**：REPORT_cp_fw_af_execution.md（pGFW=FW 层日志前缀 196 条=
>   全 PID 面；**PID 描述符表 0x11eb02c-0x11ecc10 = 358 条×20B {fn1,PID 0x4000-0x4182,fn2}**
>   → fw_pid_registry.tsv；LENS_LC 镜头控制模块函数级地图=JobDispatcher/addMoveFcCmd/
>   predictFcPos/calcMoveFcStartTime(打印 SET_DEFOCUS_CONTROL)/ECOG；**liro.ko 身份修正=
>   ITRON/T-Kernel RTOS 模拟层而非镜头驱动**，镜头 I/O 在 LIRO 任务体）；工具
>   scan_movw_movt.py（movw/movt 对扫描,双阴性证明 pGFW 串走邻接放置）。B2 上游投递方/
>   B3 PDAF/B4 AE-AWB 留下批
> - REPORT_interchip_protocol.md（B7）：UDIF=内核内建芯片间框架(193 符号,7 种传输后端,
>   PCIe 只是其一)；用户态 lib=OSAL 邮箱回调桩(0x2820746/0x282078f)；协议兼容性在应用层
>   消息 ID,传输层两台同版
> - **B2 已闭环（2026-10-11 23:34，并行会话补全，见 REPORT_cp_fw_af_execution.md §四）**：
>   投递链 FC result_sender →0x170B(=0x170 字节 Buffer,池 0x90060197/UIPC 0x0197)→ FW
>   LiroSeq → LIF BL 命令层(FUN_00451f14/LIF::BL_ASYNC FUN_004520a8 + Mount_AM 环→mix_in
>   每 vsync) → onMoveFcCmdIssued(FUN_00428324) → JobDispatcher cmd3 → addMoveFcCmd；
>   镜头 INFO2 回流 drv::UpdateLensData→setLensInfo→cmd6；**a1m2_appfw.c 零 pGFW 命中=
>   FW AF 序列确认 CP 驻留**；两套 PID 命名空间(0x4000-0x4182 注册表 vs 0x40xxxx/0x31xxxxxx 复合 ID)
> - appFw 首轮导出撞 10 万函数上限（截断）；queue_v2.sh 后台补量中（a1 复用工程重导 40 万上限、
>   a1m2 换名 appFw_a1m2.so 重导入、bonobo 换 av-cam 基址、darwin 换 ARM32 重试）
> - **B3 PDAF + B4 AE/AWB 已落账（2026-10-11 深夜，REPORT_cp_fw_af_execution.md §五/§六）**：
>   B3=CheckSetFocalPlanePhaseDetection→RAM 0x1503790；ZPD→DFE→Mario 全栈 RTTI 落图
>   （mtg_set_zpd_*→ZpdPre/ZpdAif/ZpdDcSetter→DFECore Ifmt/Det/CorrMario*/DDX-DMA→
>   LC ZpdMarioSequenceData+MarioAfcState 9 态机→FC ZpdInfoManager/DefocusInfoGenerator/
>   DefocusInfoTranslator→DefocusFace/Keypoint 判定族）；nflasha18(/lens) 校准流=16B 镜头名
>   匹配器(0x564334,fixed_lensfile 内置回退)→镜头 DB→DFE Corr*表加载。
>   B4=EC Exposure Control ~80cpp(CalcAe/CalcExpose/AESchedule/StateMachine/ContAllot_{Cam,
>   Dsc,ProCam}/Iris/ElecShutter/EC_Detect{Get,Set}IDT 面部优先 AE/MainObject 主主体联动)；
>   统计硬件 CUC_CAM0_ATRCAE/DET_CAE(分区直方图+可编程测光窗)；WB 硬件块 ArcWb/NrsWb/SigWb/
>   VatrWb+CC: CalAwbAim；AWB 估计全 CP（appFw 仅菜单面）
> - ★**日志前缀伪影修正（影响全部历史文档）**★："pGFW"→实打印 **"FW: "**、"pGLC"→**"LC: "**、
>   pGLENS_LC→LENS_LC——串首 "pG"(0x70,0x47) 与函数尾 `bx lr` 指令重叠放置，ADR 实际指向串+2
>   （cpapp 199 条 s_FW__SET_* 实证；NOTES_ENUMS_NAMING.md §6 有对照表）
> - **Block C 首批完成（2026-10-12 凌晨，a1m2_appfw.c 98420 函数）**：
>   - **C-1 消息/端口首表**（REPORT_interchip_protocol.md §二点五）：FC 队列 0x90060197 消息
>     类型表（9/10=主体结果、0x1700=Adam 资源请求 adam_process_manager、0x210=STAPLE
>     fc_drv_staple、0xc80/0xd80=Adam alloc/FeatureScalar）；"0x170B 主体结果"确证为误名
>     （=0x170 字节 Buffer）；UIPC 服务端口 0x910040=UTIMER、0x80870935=ADJ 工厂调整、
>     0x8087094e=文本调试台、0x8057060a=codec HIF；**avcam=纯编解码守护（imola2/SFMC），
>     主体结果消费方在 appFw 队列回调族（原"分发 switch 在 avcam"作废）**
>   - **C-2 PID 官方名对齐★10 万函数遍历最大收获★**：appFw 属性注册表（FUN_032f75ec 族
>     (描述符,id,"PID_SET_*")）= 370 PID + 215 NID 全名单（appfw_pid_nid_registry.tsv），
>     与 CP 358 条注册表对齐 345 条 → **fw_pid_registry_named.tsv**（25 AP 独有=DUMMY/
>     CAPTURE_START_END/锁管理）；眼选族 0x4047/0x40fd/0x40ff/0x4102/0x4104/0x4105 全名
>   - 下一批 C：AP 队列 0x8068xxxx 族分派全表、LiroSeq AF 序列本体、a1/a1m2 appFw 差分
>     （a1_appfw.c 后台重导中 96.5MB+，a1m2_darwin.c 0B 待 ARM32 重试）
> - 范围：只做 α1/α1 II（a9m2/A7M4 分区解密不在本轮）；硬件实测项等用户备料

>
> **2026-10-11 晚二·收尾清单三项全部完成（AF_LOGIC.md §十九 全勾）**：
> - REPORT_human_cross.md：HumanCross 全解——配对表(24B×8/主体@+0x3BC,跨帧页复用)、
>   CrossJudge HH/HB/BH/BB(Head/Body 框 2×2 IoMin)、AdjacentJudge(扩展框仅 HH)、
>   FrontJudge(itr_df/ref_df：**更糊=前景遮挡者 pos1，更清晰=被跟后景 pos2**)；
>   官方命名 is_crossing/is_adjacent/crossing_position/时间戳；全部消费方(REGISTER_TRACKED
>   镜像、CalcCoef 防串号、交叉期热图保活、isFaceSwapPermittedByCross 人脸 ID 互换)
> - NOTES_ENUMS_NAMING.md：XED=眼检/XHD=人形关键点(XhdType0-7)、FoundStatus=
>   (aed==3)?2:(stpl==2)?3:(aed==1)?1:0、AedConfidence∈{0,1,3}、Mario=ZPD→DFE 散焦引擎代号
> - REPORT_defocus_subject_selector.md：景虚化选主体全解(PreFaceIsInLockOnRange 脸/头/躯干
>   三区 min_df 判定、getMinAverage/MinReliableDefocusFace 终选、curr_top 提升主主体链表头)
> - 新工具：movw/movt 立即数对扫描器（cpapp 地址引用搜素，AArch32 无 literal pool 直址）
>
> **2026-10-11 晚·AI 对焦逻辑大突破**：cpapp-b.bin 反编译资产已存在
> （`firmware_reverse/decompiled/a1m2_cpapp.c` 46MB/47198 函数，基址 0x108000），
> 本轮完成 α1 II AI 对焦决策层主体逆向：
> - **AF_LOGIC.md** = 主文档（19 节：架构/模型/AdamSequencer 调度/眼选/STAPLE/主主体/
>   结果计算/滞回/verify 状态机/搜索模式 ModePattern 0-25/区域生成/TrackSequencer 10 态/
>   FW 执行层/全流水合成/优先级判定）
> - **六份详细报告+一份枚举笔记**：REPORT_adam_sequencer_subject_eye_staple.md、
>   REPORT_result_calc_frame_selector.md、REPORT_search_region_track.md、
>   REPORT_priority_judgment.md、REPORT_human_cross.md、REPORT_defocus_subject_selector.md、
>   NOTES_ENUMS_NAMING.md
> - 工具：a1m2_ai_pipeline/extract_fun.py（按 FUN 名提取）、extract_fun_by_range.py、
>   cpapp_fun_index.tsv（函数→字符串索引）、diff_a1m2_new_strings.txt（α1 II 新增 3544 串）
> - 关键结论：识别与对焦决策全在 CP；权重=NPU SRAM 镜像（重建需 NPU ISA，非移植必需）；
>   移植路径仍是硬件路线（rp2040 串口引导）
>
> 2026-10-11 早·default.nab 战略结论：格式主体已破译（见 a1m2_ai_pipeline/NOTES_NAB_REVERSE.md
> 1-11 轮），权重块=NPU SRAM 镜像（内嵌 DMA 描述符+tile），重建网络需逆 NPU 命令语言；
> 该逆向不是移植 AI 对焦的必要条件。

## 一、最终目标
给 α1（ILCE-1, 国行 CN2, fw V4.00）移植 α1 II（ILCE-1M2）的 AI 对焦（人体姿态估计 + 新主体识别）。

## 二、已解决的（真实成果）
1. **gen5 固件解密完全打通**：GitHub `q19032/Sony-firmware-unpacker` 给出 gen5 AES 密钥。
   - key_CXD90057CXD90058 = `376A61D9...7FB6`（解 α1 V1.35）
   - key_CXD90057CXD90058gen2 = `43458943...DC69`（解 α1 V2.01/V4.00 + α1 II V4.00）
   - 结构：UFU 容器(DATV/PROV/UDID/FDAT/DEND) → FDAT: 512B头(key_aes ECB) + 1024B分块CBC(key2) + IV@payload[-0x110:-0x100] + 尾256B
   - 工具：`gen5_pack.py`（解密+重打包，离线回环逐字节一致）；修改版 fwtool 备份在 `fwtool-gen5/`
2. **两台相机硬件架构完全解析**（`HARDWARE_ARCHITECTURE.md` + `cxd90057_decompiled.dts`）：
   - 同平台：CXD90057(主,4×A35,8GB) + CXD90058(协处理器,带NPU)；设备树两台 MD5 一致
   - 差异：网卡 r8168(1G)→r8125(2.5G)、α1 II 砍 NFC、加 AI 单元(40MB default.nab 姿态模型+scd_dic1/2/3+libAiDictionary.so)
   - 内部 NAND=NVMe SSD（nflasha1-30 分区）；协处理器经 PCIe 互联（pci_ep_cp.ko）
   - 拆机佐证：双 Bionz XR、IMX610 传感器、整机 16GB
3. **AI 对焦组成已定位**：姿态模型 `/usr/data/ai_dict/default/default.nab`(40MB)、`sabin/scd_dic1/2/3.bin`、协处理器 `cpapp-b.bin` 里的 `AmS_PoseDetect*` 管线、框架 `libAiDictionary.so`
4. **QEMU 能跑 Sony 固件 Linux**：通用 ARM64 内核(6.8) + Sony initrd rootfs → busybox shell 可跑。产物：`boot_sony_vm.sh` + `sony-a1-initramfs.cpio` + `generic-arm64-kernel`。
   - 坑：fwtool 解包丢执行位(全644) → 需 chmod +x；相机专用内核在 QEMU virt 起不来（内存基址/UART 不符）
5. **A7M4 eMMC 转储解密链路打通（2026-10-10）**：`A7M4_EMMC_DUMP.BIN` = SDM2 明文分区表(魔数8246/2.00, 30表项15有效) + AES-XTS 加密分区。密钥直接用 `ILCE-7M4-RE` 的 bootrom(CXD90057_Mira)+esram loader 推导（脚本 `decrypt_a7m4_emmc.py`）。已解密 nflasha7(16MB rootfs ext2 原生权限/符号链接齐全)/nflasha15(650MB /usr, appFw.so 57MB, OpenSSL 1.1.1a)/nflasha3(75MB, 真机内核+initrd+模块, 非FAT, FAT引导扇区为残留)。α1 II 和 A7M4 用户态均已 QEMU 实测跑通。**三台相机图形 UI 仍不可行**（UI=appFw.so+索尼私有显示栈，需自制 CXD90057 机器模型）。

## 三、已确认的死路（不要再试）
1. **刷改固件 = RSA-2048 签名封死**（实测）：FDAT 尾 256B 是 RSA 签名(均匀高熵)，boot ROM 的 InfSec 验签，内容一改就拒(错误码 0x56=慢闪5+快闪6)。
   - 版本号包 v401_00(内容=官方仅改版本号)也被拒 → 证明不是内容/尺寸/格式，是签名
   - 我加密管线无误(v401_00 解密后与官方仅差版本号+头CRC)
   - updater 二进制无验签代码; gen5 密钥派生盐不在固件包 → 验签在 boot ROM(不可见不可改)
   - RSA 攻击已试：gcd 模数恢复 e=3(8候选×6对)=0命中、e=65537 算不动(1.34亿位)；PSS 填充让公钥都恢复不出；MAC/CMAC 重算无匹配；尾签解密是乱码
2. **senser 服务模式 = 国行 CN2 锁死**：auth+info 能过，pull=128/shell=GenericUsbException/bootrom=128/bk r=129。锁=libsencore.so 的 terminal_change_function_is_disabled + A_AS_AREA_CHK。**V1.35 就有此锁(非新增)**，降级无用。
3. **MSC-ext(SCSI 0x7A) = 只读**：仅 DevInfo(插件1)+ExtBackup(插件4)响应，ExtBackup 只读(ReadBackup 无写)。
4. **updater 命令在 MSC 模式不响应**(Sense 0x9 0x81 0x83)，要进更新模式才行。
5. **α7C II 的方法(senser root shell)不能照搬**：α7C II senser 开放，α1 旗舰固件锁死。
6. **Wonder-Lantern(尼康)不能照搬**：尼康"签名"=SHA1(body||K8)对称可恢复密钥摘要；索尼=非对称 RSA。强度不同量级。

## 四、当前正在走的路线（用户坚持）→ 已被 A7M4 路线升级（2026-10-09 晚）
**ILCE-7M4-RE（已入库 `ILCE-7M4-RE/`）给出决定性升级：A7M4 主SoC=CXD90057/协处理器=CXD90058 与 α1 同芯片。**
1. 两颗芯片的 **bootrom 二进制已在手**（`ILCE-7M4-RE/bootrom/`）→ 验签层可静态逆向，不再依赖 QEMU。
2. bootrom 有秘密串口引导模式：Multi 口 RX 位敲 → 任意内存写 + 栈改写绕解锁 → 裸机 fastboot 载荷
   → **eMMC 分区转储 AES-XTS 可解、无签名校验**（固件层三条死路全部绕开）。
3. 工具：`serial-bridge/a1_uart_boot.py` + 移植指南 `serial-bridge/A7M4_ROUTE.md`（硬件: rp2040×1 + Multi 转接×2）。
4. 实施顺序：PoC 点灯 → `dumpbrom` 核对 α1 bootrom 修订差异 → 只读转储 eMMC/CP → 静态分析验签。
（旧路线存档：相机在 VM 里 MSC 可访问；α7M5 BOOT1/2 密文格式无用勿追。）

## 五、关键文件位置
- 工作目录：`<workspace>/`
- 串口桥工具：`serial-bridge/`（senser 通道桥 PTY+TCP+日志 + 物理 UART 桥；README 有 α1 CN2 可用范围）
- 固件版本库：`firmware_versions/`（README + 各版本 INFO.md；两个测试包刷机均失败已标注勿刷）
- 解密产物（/tmp 易失）：/tmp/a1_v400, /tmp/a1m2_v400, /tmp/a1_v201, /tmp/v135_plain.bin；/tmp/a7m4_parts/（A7M4 nflasha3/7/15 解密镜像），/tmp/a7m4_x/root/（A7M4 rootfs 拼装树）
- QEMU 运行产物：`generic-arm64-kernel` + 启动脚本 `boot_sony_fw.sh`(α1) / `boot_sony_a1m2_fw.sh` / `boot_sony_a7m4_fw.sh` + 对应 `sony-*-fullroot.cpio.gz`；A7M4 转储解密工具 `decrypt_a7m4_emmc.py`
- 混合固件(已证签名拒)：firmware_versions/v401_01_hybrid_ai_phase1/
- 日志：KEY_HUNT_LOG.md（完整证据链）

## 六、下一步（A7M4 路线，替代原 QEMU 完整运行方案）
1. 备料：rp2040 板(Pico/RP2040-Zero) + Multi Terminal 转接×2（见 A7M4_ROUTE.md 硬件清单）
2. 烧 `ILCE-7M4-RE/tools/uart_boot` 桥固件 → PoC 点灯载荷验证 α1 串口引导成立
3. fastboot 载荷 → `oem dumpbrom` 拿 α1 自己的 bootrom → 与 A7M4 版 diff（定位解锁栈址/密钥表偏移漂移）
4. **只读**转储全部 eMMC 分区（nflasha*，先两份完整备份）+ cetus 转储 CP NOR/bootrom
5. 静态逆向 CXD90057 bootrom 的 InfSec 验签逻辑（离线，无相机依赖）
6. （可选，数据路线续命）cpapp-b.bin 基址恢复 + NPU 驱动反编译 → VPMN 命令语言 → .nab 完整重建；
   入口点与已解结构见 `a1m2_ai_pipeline/NOTES_NAB_REVERSE.md` 第十一轮
