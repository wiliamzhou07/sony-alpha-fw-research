# REPORT_staple_reid_faceid.md — STAPLE 本体 / ReID / 人脸 ID / IDT / 眼选（Block A，2026-10-11）

> 数据源：a1m2_cpapp.c（基址 0x108000）+ copro/cpapp-b.bin 常量直读。
> 本文收口 AF_LOGIC.md §九/§八 的遗留：STAPLE 训练数学在哪、ReID 怎么比、人脸 ID 怎么管、
> IDT 硬件人脸检测长什么样、眼选 mode 0-6 语义。

## 一、STAPLE 本体定界（A1）★训练/相关计算在 SA-IP 硬件，CPU 只做窗口+参数+解包★

**结论：cpapp 内无 FFT、无相关运算代码（字符串与代码双证）。相关滤波本体在 DDL_MINNA
（SA-IP）硬件引擎里跑；CPU 侧只做四件事：资格判定、参数化、Hann 窗供给、结果解包。**

分层（fc_alg_staple → fc_drv_staple → DDL_MINNA staple 引擎）：

1. **训练资格判定 JdgStapleinit（FUN_002d9fbc，src/parts_trainer.cpp）**，返回值 2/1/0：
   - 字典版本校验：字典上下文 +0x24c（当前版本）vs vtable+0xac / +0xdc（按字典类型 +0x250
     ∈{0,1} 选接口）查询引擎字典版本，版本过期 → 不允许 init；
   - track 状态/矛盾标志检查（+0x2c/+0x4d/+0x21e/+0x21f/+0x23c/+0x22c）；
   - **时间基线**：全局时间戳对 `_DAT_013df0f0/f4`（上次 init 时刻），与当前差窗口内判 1/2，
     差上限 99999（µs×1000? tick）——**"训练太久不重训"规则**。
2. **分发器 HumanStaple（FUN_002d9d40，parts_trainer.cpp）**：JdgStapleinit∈{1,2} → **init 路径**
   FUN_00871ba0；否则 **train 路径** FUN_00871e5e（双 part 结构 stride 0xb0×2）。
   双 part 全失败（0xb0 步长扫 +0xb1/+0x161 标志）→ +0x24 = 3（弃用）。
3. **init（FUN_00871ba0）**：按 part 类型 param_3∈{1,2} 从 param_2[9]/[8] 取字典与模板基址
   （+0x36*4 / +2*4 偏移）；`local_76[0..1]=5` 后 FUN_00871ebe 微调 → 每 part 一个模板表索引；
   对每 part 调 **FUN_002da218（part 参数化）**：
   - 目标尺寸定点缩放（<<12 定点；尺寸分级：≤0x10 → pad 类 4；≤0xb4 → 0；≤0x168 → 1；否则 2；
     缩放目标上限 0x5a=90，源头尺寸上限 0x167=359）；
   - 搜索区尺寸 = `*(u32*)(param_1+0x34) * 表[质量类] >>12`（表 @0x2da39c，类 0/1/2 索引，
     类 4=0x28），封顶由引擎能力查询（vtable+0x268）；
   - 模板中心 = 目标中心偏移（FUN_00802836/285e）。
4. **train（FUN_00871e5e）＝纯状态置位**：每 part `+0x24 = 2（有效，继续训练）或 3（无效）`，
   `+0x20 = 1`——**滤波器更新由硬件引擎按此标志自行执行**，CPU 不参与数学。
5. **Hann 窗供给（FUN_00292070，ddl_minna_staple_param_manager.cpp）**：
   `FUN_006704b0(dst, &DAT_00d8ee28, 0x400)` 与 `&DAT_00f8862e + idx*0x400, 0x400` ——
   **0x400B（256×f32?）窗表 × WINDOW_TYPE（IDT::Staple::WINDOW_TYPE 枚举）**，窗表存于
   RAM（运行时 tuning 载入），setHanwindow 日志确认。
6. **结果解包（FUN_00294070 retrieveResult，IDT_DDL_MINNA::_Staple）**：
   每 part 结果结构 stride 0x114 @ +0x110 基表；每条从 VMM 页表（DAT_00d88ba0 表）解出
   物理缓冲，结果条 0x1cB = 7×u32（位置/尺寸/响应值族）复制到 param_2 + i*0x1c。

**佐证**：全 cpapp 无 fft/correlation 字符串（strings 扫描 0 命中）；α1 II 的 Staple 走
SA-IP 封套（REPORT §二十：Staple/StapleDrv = tagSA_STAPLE_IO_ALLES）。

## 二、ReID 外观相似度（A2）★全数学闭环★

**数据结构**：tracklet 0x498B/主体（≤8），64 维 f32 嵌入 @ +0x12c（300），长度 0x40（64）；
相似度字节 @ +0x2288，f32 缓存 @ +0x388。ReID 输出环 = AdamParamMgr 8×0x414
（FUN_002cdd14 setInitialParamReid：cmd 类 0x20001 + ConvCetusVA2AdamPHY 物理地址，
AdamPrmMgr/cetus_va_base_addr）。

**计算链（FUN_002d4544，src/app_similarity_calculator.cpp，HUMAN_MOT::ALG）**：
1. **参考基准**（FUN_002d46d8）：对当前跟踪目标，取其**自身 10 深环形历史**（@+0x130，
   写指针 +0x158，计数 +0x15c）的 f32 均值——这是目标自身嵌入漂移的基线（历史环内容 =
   目标帧间嵌入距离，写入方在 HUMAN_MOT 更新路径）；无历史 → 默认 DAT_002d4738。
2. **逐候选距离**（FUN_002ee3a8）：`dist = ||emb_target - emb_candidate||₂`，
   **欧氏距离**，实现 = 平方和 + **0x5f3759df 快速逆平方根（2 次牛顿迭代）**；
   候选无效（+0x128==0）→ 默认 0.2。
3. **归一**：`sim = fmin( max(dist - baseline, 0), 0.2 )`（FUN_002ee324 = fminf，
   0x3e4ccccd = 0.2f）。
4. **量化落地**：`u8 = (sim * 100.0 > 0) ? (u8)(sim*100) : 0` 写 @+0x2288（0=与目标同，
   20=最大差异）；f32 原值缓存 @+0x388。

**常量（cpapp-b.bin 直读）**：DAT_002d46cc=0.2（默认/封顶）、DAT_002d46d0=0.0（钳位下限）、
DAT_002d46d4=100.0（量化因子）。

**消费方**：同文件族 similarity_coef_calculator.cpp（FUN_002df380 CalcCoef，含
"CalcCoef det x is_crossing" 日志）把 app_sim 与 pose_sim（FUN_002da3a8）合成防串号系数；
FUN_00870df0 重选资格/HUMAN_MOT 匹配读取 +0x2288 字节。

## 三、人脸 ID 管理（A3）★闭环★

**注册表**：8 槽 × 0x570B @ Human 上下文 +0x500，占用位图 @ +0x3080[8]，face ID @ slot+4。

- **FR 特征在 ADAM 侧计算**：AdamFrManager::setParametersFr（FUN_002a2214，"FR_disabled_by_
  backup_sw"）下发；FR 可被备份开关禁用。
- **CompFace_ID（FUN_002d1724，Human StateFunction）**：
  1. FUN_008258a2 计算当前脸的 FR 描述符（S12 512 维消费点）；
  2. 注册表内按 ID 重认领（匹配 → 从挂起链摘回，FUN_00868b78 刷新）；
  3. 无匹配 → 找空闲槽（位图扫描）；**>7 槽占用 → 驱逐最老**（FUN_008562c0）；
  4. 8 槽全满 → 断言。
- **互换判定 judgeSwapFace_prio（FUN_002dec0c，regist_face_judger.cpp）**：
  条件 = 新脸 score < 现主脸 score 且 < prio 上限（双 `<` 比较，param_3={id,score}）→
  **FRC_algo::swap_ID**：两 tracklet 的 face-ID 绑定互换（+0x30 = 1/0），结果结构清 -1，
  被换脸状态位 (+0x35/+0x37) = 4。
- **放行闸 isFaceSwapPermittedByCross（FUN_002dea8c）**（全条件）：
  - 交叉时间戳 @+0x2fc（tick），标志 +0x2f8，交叉态 +0x300==2；
  - 放行：无窗口参数（+0x10==0）/ 无记录（0x2fc==0）/ 交叉态==2 / `now - ts < window`
    （日志以 tick/2000 显示秒，`+0x334 = ts/20000` = 剩余秒）；
  - 其余拒绝；结果镜像 +0x331/0x332/0x337。
- **外围**：add_priority_face_ID（FUN_0029e710，tracking.cpp，分配失败日志 alloc_error）、
  按钮 select/cancel face ID（FUN_0029a86c fc_alg_frc / FUN_002d541c cursor_face_judger）、
  RegistFaceJ* 批量（FUN_0087382a/00873c42/00873dcc）、det_id 匹配（FUN_008732a0）。

## 四、IDT 硬件人脸检测管线（A4）★定界★

- 驱动 = **Camera::NSX::Face::idt_face_***（ddl_ddl_idt_face_control.cpp），消息驱动：
  `{FACE_INIT(0027da30), BASE_SET(0027dad4), IMME 立即触发(0027dc18), STOP_MON(0027dd58),
  STOP_ALL(0027de14), STOP_IMME(007ff85e)}`，init 处理器 FUN_0027f048（SA_Malloc/状态机）。
- **FDT 硬件中断（FUN_0027ea3c，ddl_idt_face_fdt_int.cpp）**：
  - 中断因子寄存器读 FUN_0080143c，高 4 位（0xf0）= 错误因子（日志 FDT_Int_Error factor）；
  - **双结果表**：main 0x244B（**≤0x24=36 脸**）+ branch 0x484B（**≤0x48=72 脸**），
    从 VMM/DMA 区拷出（getResult），超限报错清零；
  - 结果解析器三胞胎 FUN_0027d880/0027d910/0027d9a0（"result_main/result_branch"）。
- 分工：IDT（硬件 FDT，36+72 脸）供原始人脸流 → FC Human/StateFunction → STAPLE（SA-IP）
  跟踪；关联硬件 **iro2G**（fc_drv_iro2g.cpp，idt_iro2G_stop）挂同一状态机。

## 五、眼选 mode 0-6（A5）★机制全解，语义半解★

- **接口 FUN_002bd31c（void Camera::FC::fc_get_if_tracking_eye_selector(...)，
  fc_lib_if_flash.cpp）**：mode∈0..6 → 从 RAM `&DAT_0198bdde + mode*0x200` 取一个 0x200B
  阈值块 `{u8 ratio_a, u8 ratio_b, u16 size_max, u16 size_min, u16 size_min_hard}`；
  mode3 = 条件表（子参数==2 选 B 否则 A）。
- **表是运行时填充的**：0x198bdde 超出 cpapp 文件范围（RAM/tuning 区），填充走游标
  DAT_011e8be8（`if (DAT_011e8be8 == &DAT_0198bdde)` → 流式写入器分块灌入）→ **tuning
  blob 来源，非编译期常数**。
- **mode 传播链**：候选结构 +0xC8（200）→ FUN_0029e8bc；FUN_0029e8bc 无直接调用者
  （vtable 间接），上位写 +0xC8 的配置在 FW 层（后续 Block B 顺带确认）。
- **主判定（FUN_0029e8bc）复核**：双眼有效（FUN_00839ff2 side 0/1）→ 距 AF 点近者胜
  （dist²，右眼平手胜逻辑在 FUN_0083a040）→ 接受半径校验（FUN_0029e9c0：s<硬下限→0；
  a·s / b·s / 线性插值，>>4 定点）→ 返回 2=接受。
- **命名语义假说**：接口来自 **fc_lib_if_flash（闪光灯库）** → mode 很可能是**闪光状态**
  （未闪/预闪/全光分级等）而非菜单"左眼/右眼"选项；菜单枚举（EYE_SELECT_MODE）在 AP 侧
  仍未现——留待 Block C appFw 遍历确认。表数值本身在 tuning 区，需运行时 blob 才能取值。

## 六、遗留

- ReID 参考基线的写入方（10 深环 +0x130 的写入点）未定位（语义已定：目标自身帧间漂移）。
- 眼选 mode 的菜单级命名 → Block C（appFw）。
- AdamSequencer 多分辨率/节能残余（A6）→ 并入 Block B 的 FW 层扫描顺带完成。
