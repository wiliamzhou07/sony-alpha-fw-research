# REPORT_human_cross.md — α1 II HumanCross 交叉仲裁全解（2026-10-11）

> 收尾清单第 1 项。逐行逆向 `src/human_cross_judger.cpp` 两个函数 + 全部下游消费方 + 官方命名。
> 反编译基址 0x108000；地址均为 Ghidra 虚地址。日志串直接引自 cpapp-b.bin（α1 II V4.00）。

## 1. 定位与总览

| 函数 | 地址 | 大小 | 官方日志/符号 |
|---|---|---|---|
| HumanCross 主判定 | `FUN_002d77c4` | 13058B | `[HumanCross]Start Loop / Start Judge subjectId:%x, referenceId:%x / CrossJudge HH%d, HB%d, BH%d, BB%d / AdjacentJudge HH%d, HB%d, BH%d, BB%d / End Loop` |
| FrontJudge | `FUN_002d8084` | 2909B | `[HumanCross]FrontJudge itr_df:%d ref_df:%d` |
| 判据原语 | `FUN_00870a98` | — | （矩形 IoMin 重叠测试） |
| 消费方① | `FUN_002df380` | — | `SimilarityCoefCalculator::calcSimilarityCoef`（`src/similarity_coef_calculator.cpp`） |
| 消费方② | `FUN_0012f258` | — | 关键点热图过滤器（交叉窗口保活） |
| 消费方③ | `FUN_0087a1ae` | — | REGISTER_TRACKED 注册（det→track 状态镜像） |
| 消费方④ | `FUN_002dea8c` | — | `isFaceSwapPermittedByCross`（`src/regist_face_judger.cpp`） |
| 消费方⑤ | `FUN_002dec0c` | — | `judgeSwapFace` / `FRC_algo swap_ID`（人脸 ID 互换） |

**一句话**：每帧对全部人体主体两两判定"是否交叉/是否相邻"，交叉时用两脸**散焦量(df)**判前后；
结论（is_crossing / is_adjacent / crossing_position / 交叉时间戳 / df 值 / 配对表）随检测主体
注册进跟踪器，供相似度匹配、热图保活、人脸 ID 互换三处换挡。

## 2. 数据结构

### 2.1 检测主体（数组，stride 0x498，≤6 条，计数 u32 @ +0x24C0）

数组由 `AdamFrManager::loadDetectionResult`（FUN_002a4148）填充；HumanCross 在原数组上就地写结果。
与交叉相关的字段（其余见 AF_LOGIC.md §七/§十一）：

| 偏移 | 类型 | 官方名（由下游日志/消费方证实） |
|---|---|---|
| +0x394..0x39A | 4×u16 | 第 3 个候选框 rect0（注册时复制到 track+0x2220） |
| +0x39C | byte | 候选 1 有效标志（→ FUN_0087a43a 人脸信息生成用） |
| +0x3A0 | obj | rect provider A（vptr@+0x3A0，rect=+0x3A4）＝ **Body 框** |
| +0x3AC | byte | 候选 2 有效标志 |
| +0x3B0 | obj | rect provider B（rect=+0x3B4）＝ **Head 框** |
| +0x3BC..0x47B | 0xC0B | **本主体配对表**（8 条 × 24B，HumanCross 输出，见 2.2） |
| +0x47C | byte | **is_crossing**（任一配对存在 HH/HB/BH/BB 重叠位） |
| +0x47D | byte | **is_adjacent**（CrossJudge 命中或 AdjacentJudge 确认） |
| +0x47E | byte | **crossing_position**：1=前景遮挡者，2=背景（被跟主体） |
| +0x480 | u32 | **交叉起始时间戳**（仅 is_crossing 且 position==2 时复制到 track+0x2370） |
| +0x484 | u32 | **df 值 1**（FrontJudge 候选比较值，复制到 track+0x2374） |
| +0x488 | u32 | **df 值 2**（同上 → track+0x2378） |

Head/Body 命名由 CrossJudge 日志直接证实：`CrossJudge HH%d, HB%d, BH%d, BB%d` 四个参数依次是
(H,H)(H,B)(B,H)(B,B)，对应 i.rB×j.rB / i.rB×j.rA / i.rA×j.rB / i.rA×j.rA → **rB(+0x3B4)=Head、rA(+0x3A4)=Body**。

### 2.2 配对条目（24B，配对表内）

| 偏移 | 内容 |
|---|---|
| +0x00 | id1（主体 i 的 id） |
| +0x04 | id2（主体 j 的 id） |
| +0x08 | u32 flags：bit0=HH、bit1=HB、bit2=BH、bit3=BB（本次直接重叠位）；**bit4=0x10=确认位**（CrossJudge 或 AdjacentJudge 通过） |
| +0x0C | int：provider A 跨主体比较值（i.A.obj.vt+0x44(j.A.obj)） |
| +0x10 | int：provider B 跨主体比较值 |
| +0x14 | byte（0） |
| +0x15 | byte：id1 一侧的 crossing_position |
| +0x16 | byte：id2 一侧的 crossing_position |
| +0x17 | byte |

配对表存储：`FUN_002d77c4` 的 param_1 = **跨帧配对页存储**（每页 0xC0=8 条；外层第 i 个主体
读写第 i 页；判第 k 个配对前把第 k 页拷到栈上搜索）。因主体顺序逐帧确定，第 k 页恰是上一帧
该配对条目所在页 → 已在交叉中的配对直接复用旧条目（保持前后关系），新配对才现算。
外层结束时第 i 页拷回主体 i 的 +0x3BC。

### 2.3 track 侧镜像（REGISTER_TRACKED，FUN_0087a1ae）

| track 偏移 | ← det 偏移 | 官方名 |
|---|---|---|
| +0x22AC(0xC0B) | +0x3BC | 配对表整体复制 |
| +0x236C | +0x47C | is_crossing |
| +0x236D | +0x47D | is_adjacent |
| +0x236E | +0x47E | crossing_position |
| +0x2370 | +0x480 | 交叉时间戳（仅当 is_crossing && position==2 时写入） |
| +0x2374 | +0x484 | df 值 1 |
| +0x2378 | +0x488 | df 值 2 |
| +0x2220 | +0x394 | rect0 |

另有 track+0x8DB = 独立的 is_crossed 标志（CalcCoef trk 行第一个布尔，写入点未逐行）。

## 3. 主判定 FUN_002d77c4 逐段

```
参数: (pair_pages, subject_array[6], <unused>, ctx_rect, ctx_time)
ctx_rect.vt+0x344()  → CrossJudge 用的矩形查询（构造 query 对象传给 provider+0x3c）
ctx_rect.vt+0x348()  → AdjacentJudge 用的第二矩形查询（疑似放大/预测框）
ctx_time.vt+0x20()   → 时间戳（交叉起始时刻来源）
单例 FUN_008834d6.vt+0x33c() → IoMin 阈值(百分比)
```

外层 i = 0..5（计数 @+0x24C0 封顶）：
1. 栈上载入配对页 param_1[i*0xC0]；输出指针指向同一页首。
2. 内层 j = 0..count-1，id_i == id_j 跳过（自身）。
3. **第 k 个有效配对**（k = 本次外层已产出条目数）：
   - **旧条目命中**（在栈上页中按 (id_i,id_j) 或 (id_j,id_i) 对称搜索）：
     原样复制 24B 到输出；并 `0x47C |= (flags&~0x10)!=0`、`0x47D |= flags>>4&1`、
     `0x47E = 我的角色字节(id1==我?+0x15:+0x16)`、`+0x480 = (0x47C? ctx_time.vt+0x20() : 0)`。
   - **未命中（新配对）** → 走 §4/§5 判定，写新条目：
     `{id_i, id_j, flags, cmpA, cmpB, 0, pos_i, pos_j}`，其中
     cmpA = i.providerA.vt+0x44(j.providerA)，cmpB = i.providerB.vt+0x44(j.providerB)。
4. 外层收尾：输出页 → 主体 i +0x3BC；然后**终裁**：
   - `0x47C == 0` → `0x47E = 1`（无交叉，视为前景）；
   - 否则遍历自己 +0x3BC 的 8 条，取 (flags & ~0x10) != 0 的条目
     （即**只有直接重叠的配对参与终裁，adjacent-only 不影响**），
     `0x47E = AND(我的角色 == 1)` —— **在所有交叉对里都是前景才置 1**。

## 4. CrossJudge（直接重叠，HH/HB/BH/BB）

对每对 (i,j)：

```
q = ctx_rect.vt+0x344()                    // 矩形查询
iH = i.providerB.getRect(q);  iB = i.providerA.getRect(q)
jH = j.providerB.getRect(q);  jB = j.providerA.getRect(q)
HH = overlap(iH, jH, thr);  HB = overlap(iH, jB, thr)
BH = overlap(iB, jH, thr);  BB = overlap(iB, jB, thr)      // FUN_00870a98
log("[HumanCross]CrossJudge HH%d, HB%d, BH%d, BB%d", HH, HB, BH, BB)
flags = HH | HB<<1 | BH<<2 | BB<<3
if (flags != 0):
    0x47C |= 1;  0x47D = 1
    (pos_i, pos_j) = FrontJudge(i, j, flags)               // §6
    flags |= 0x10                                          // 确认位
else:
    AdjacentJudge（§5）
```

**重叠原语 FUN_00870a98(rectA, rectB, thr)**：
`inter = 交叠矩形; inter!=0 && (inter面积×100 ≥ A面积×thr || inter面积×100 ≥ B面积×thr)`
＝ **IoMin（交/较小框面积）≥ thr%**，与部位判定的 IoMin 判据同族（REPORT_priority_judgment.md §5）。
矩形 = {vptr, x@+4, y@+6, w@+8, h@+10}（u16），面积 = w*h。

## 5. AdjacentJudge（相邻确认）

```
q2 = ctx_rect.vt+0x348()                   // 第二矩形查询
同法算 4 个重叠（日志 [HumanCross]AdjacentJudge HH%d, HB%d, BH%d, BB%d）
if ((HH|HB|BH|BB) == 1):                   // 仅 HH=1 时
    flags = 0x10;  0x47D = 1
```

即：直接框不重叠时，用第二套查询矩形（疑似扩展/预测框）再测；**只有 HH（头×头）命中才确认 adjacent**，
flags 只置确认位 0x10、不置低位 → adjacent 不改变 crossing_position 终裁，只作为下游
（CalcCoef、热图过滤器）的独立信号。

## 6. FrontJudge FUN_002d8084（前后判定）

输入：主体 i、主体 j、flags（4 个重叠位）、ctx_mode。输出两字节 crossing_position。

**每主体比较值选取**（i 用掩码 0x3/0xC，j 用 0x5/0xA —— 因为位归属按"我的 Head 框参与"划分）：

```
i: myH_bits = flags & 0x3 (HH|HB);  myB_bits = flags & 0xC (BH|BB)
j: myH_bits = flags & 0x5 (HH|BH);  myB_bits = flags & 0xA (HB|BB)

per subject:
  if (myH_bits):  val = (+0x39C ? +0x484 : +0x488)       // Head 位命中 → df 值 1（若有效）
  elif (myB_bits && +0x3AC): val = +0x488                 // 仅 Body 位 → df 值 2
  else:           val = +0x484
  mode = ctx_mode.vt+0x36c():
    case 1/4: val = (+0x39C ? +0x484 : +0x488)            // 强制 Head 候选
    case 2/3: val = (+0x3AC ? +0x488 : +0x484)            // 强制 Body 候选
```

**比较与角色**：

```
if (val_i == INT_MIN || val_j == INT_MIN):  pos_i = pos_j = 0   // 无有效 df → 不判
else:
  log("[HumanCross]FrontJudge itr_df:%d ref_df:%d", val_i, val_j)
  val_i < val_j ? (pos_i, pos_j) = (2, 1) : (pos_i, pos_j) = (1, 2)
```

**语义（已被消费方证实）**：df = 散焦量（见 §8 证据）。**更糊（df 大）的脸 = 前景遮挡者 = 1；
更清晰（df 小）的 = 被跟踪的后景主体 = 2**。物理机理：AF 隔着走进画面的人对焦在被跟者身上，
遮挡者不在焦面上故 df 大。角色 2 的官方措辞见 §8④："my face is in background"。

## 7. 结果聚合总结（每主体每帧）

| 字段 | 值 | 条件 |
|---|---|---|
| is_crossing (+0x47C) | 1 | 任一配对 HH/HB/BH/BB 直接重叠 |
| is_adjacent (+0x47D) | 1 | CrossJudge 命中，或 AdjacentJudge（扩展框 HH）命中 |
| crossing_position (+0x47E) | 1 | 无交叉，或所有直接重叠对中都是 df 大的一方 |
| crossing_position (+0x47E) | 2 | 所有直接重叠对中都是 df 小的一方（= 被跟后景） |
| crossing_position (+0x47E) | 0 | 有确认对但 df 无效（INT_MIN） |
| 时间戳 (+0x480) | ctx.vt+0x20() | is_crossing 时记录（帧计数/时刻） |

## 8. 下游消费（全部已验证）

### ① calcSimilarityCoef（FUN_002df380，src/similarity_coef_calculator.cpp）

检测↔跟踪相似度矩阵逐对计算，日志：
`[CalcCoef] det:%x, is_crossing:%d, is_adjacent:%d` / `[CalcCoef] trk:%x, is_crossed:%d, is_adjacent:%d, crossing_position:%d`。
det.is_crossing(0x47C)、trk.is_adjacent(+0x236D)、det.is_adjacent(0x47D)、trk.crossing_position(+0x236E)、
trk.is_crossed(+0x8DB) 任一命中 → 相关系数改用另一组配置 getter（单例 vt+0x360/0x364，正常路径用
vt+0x350/0x354）并换基准值 —— **交叉期间换用防串号的匹配系数**，避免两人交叉时 ID 互换。

### ② 关键点热图过滤器（FUN_0012f258）

逐格处理姿态热图：`trk+0x236D == 0 && det+0x47D == 0` → 正常阈值清零；
交叉/相邻主体 → 若 `当前时刻 - trk+0x2370(交叉时间戳)` 在窗口内（(Δ/2000)<0x3E9 量级）则**保留原值不清零**。
＝ **交叉期间后景人物的热图保活**，保证遮挡中关键点继续输出、跟踪不丢。

### ③ REGISTER_TRACKED（FUN_0087a1ae）

见 §2.3：整套交叉状态 + 配对表 + df 值随新 track 注册复制。track+0x2370 仅在
`is_crossing && crossing_position==2` 时写入 —— **只给后景者记"进入背景"时刻**。

### ④ isFaceSwapPermittedByCross（FUN_002dea8c，src/regist_face_judger.cpp）

人脸注册/ID 判定：`trk.is_crossing_other(+0x2F8) && crossing_position(+0x300)==2` →
放行人脸 ID 互换，日志 **"isFaceSwapPermittedByCross is_crossing_other is true and my face is in background."**
（证实 position==2 = 脸在后景）；另有 `crt:%d last:%d e:%u[ms] t:%u[ms] isp:%d` 时间窗版本
（Δ/2000，与热图过滤器同款换算）。配套 `judgeSwapFace`（FUN_002dec0c，"FRC_algo swap_ID"）
执行 ID 交换并清空旧注册框。

### ⑤ 状态打包（FUN_00246044 case 2）

把 +0x47E 等状态字节打进对外状态块（调试/上报面）。

### df 值来源证据

- `[DefocusFace]PreFaceIsInLockOnRange id:%d min_df:%d`、`[DefocusFace]Min reliable DF FaceID:%d min_df:%d`、
  `[DefocusFace]Min Average DF FaceID:%d min_ave_df:%d`、`num_no_err:%d num_reliable:%d num_lockon:%d sum_df_abs:%d`
  —— FC 内 df = 每脸散焦量（DefocusFace 子系统产出），FrontJudge 日志 `itr_df/ref_df` 同名同义。

## 9. 不确定项（不臆测）

1. **df 值 1/2（+0x484/+0x488）的写入方**：两值在检测主体上被 HumanCross 读取、注册时镜像到
   track+0x2374/0x2378，但 cpapp 内未见直接赋值语句（疑似由检测后处理经指针/批量拷贝填充，
   或来自 Adam 检测记录 0xfc 模板未散布区）。"df=散焦量"由日志命名链证实，单位/符号未逐行验证
   （若为带符号 df，"大者=前景"的方向依赖符号约定；|df| 解释下结论不变）。
2. **ctx_rect.vt+0x344/+0x348 两套矩形查询的具体差异**（疑为原始框 vs 扩展/预测框）：实现位于
   运行时配置区，无法从静态二进制取值；AdjacentJudge 仅在 HH 位生效这一点是二进制实证。
3. **mode vt+0x36c 的 1/2/3/4 枚举语义**：仅确认 1/4 → 强制 Head 候选 df，2/3 → 强制 Body 候选 df。
4. **配对页存储 param_1 的宿主**（页数、清零时机）：逐帧复用逻辑已由"页号=产出序号"的搜索方式推定，
   宿主对象与生命周期未定位（注册点 thunk FUN_0087e692 经 vtable 引用，磁盘上无 4B 直址/movw-movt 对）。
5. provider vt+0x44（跨主体比较值 cmpA/cmpB）的返回含义（疑为框间距离/重叠度量）未展开；
   条目内该值当前未见下游读取。
6. 主体数组容量两处不一致：加载器 ≤8（0x24C0 计数），HumanCross 外层/内层硬界 6 条（+0x930 int 封顶）。

## 10. 与既有笔记的关系

- 细化 AF_LOGIC.md §十一 的 HumanCross 一行与 §十六 全流水合成中的"交叉仲裁"环节；
- 修正 §十一 中"关键点 9B 元组 @+0x38c-0x3bc"：+0x38C..0x3BC 实为 **3 组 flag+rect 候选框**
  （+0x394/+0x3A4/+0x3B4，flag 在各框前 8 字节），关键点元组在 +0x10..0xE8（18×12B，/1.25 归一化）；
- 与 REPORT_priority_judgment.md 的 IoMin 判据同族（FUN_00870a98 vs chk 接口虚表）；
- 为 priority_defocus_subject_selector（DefocusFace 族，收尾清单第 3 项）提供 df 语义前置。
