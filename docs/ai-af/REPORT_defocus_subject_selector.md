# REPORT_defocus_subject_selector.md — PriorityDefocusSubjectSelector 景虚化优先主体选择（2026-10-11）

> 收尾清单第 3 项。`src/priority_defocus_subject_selector.cpp`（`Camera::FC::HUMAN_MOT::ALG::
> PriorityDefocusSubjectSelector`）全函数逆向。文件内全部函数落在 0x2DBF58–0x2DD6F4
> （21 处文件断言串引用）+ 注册 thunk 0x8730BA 区。与 `priority_defocus_face_selector.cpp`
> （FC 层 DataMonFace 版，`ImportAttributeResultPriorityFace`）为姊妹模块。

## 1. 职责一句话

**电影录制（Movie LockOn/Subject）与 AfAssist 场景下，用 ZPD 散焦数据（Mario）从人脸列表中
选出"景深上最合适"的优先脸，并把它提升为主主体链表头部**——即景虚化/电影模式下的主体仲裁，
与对焦部位判定（REPORT_priority_judgment.md）相互独立。

## 2. 官方符号与函数清单

| 函数 | 地址 | 官方名（符号串） |
|---|---|---|
| FUN_002dbf58 | 4146B | `expandAfOverlapArea(Frame&, const Frame&, u8 bbox_type, const FC_PICTURE_INFO&, const Alg::AfPointOverlapFaceExpandAreaParam&, const bool)` |
| FUN_002dc2cc | 4562B | **replacePriorityFace**（13 个日志出口） |
| FUN_002dc5c8 | 4023B | **judgePriorityFaceInLockOn** |
| FUN_002dc8c4 | 2224B | curr_top 应用（私有） |
| FUN_002dca34 | 388B | AfAssist 判定 —— **桩：到达即 abort** |
| FUN_002dcd44 | 1029B | PreTopFaceID（私有） |
| FUN_002dcdd8 | 388B | 兜底选择 —— **桩：到达即 abort** |
| FUN_002dd568 | 2088B | SelectDfAreaInfo 记录构造 |
| FUN_002dd6f4 | 674B | 链表溢出搬移（私有） |
| （符号） | — | `isLockOnRectangle(const Alg::SelectDfAreaInfo&, u8, LOCK_ON_RECTANGLE_JUDGE_TYPE)`、`getMinAverageDefocusFace(const SelectDfAreaInfo (&)[24])`、`getMinReliableDefocusFace(const SelectDfAreaInfo (&)[24])` |
| （日志） | — | `[DefocusFace]No DfSelectTargetFace In Af Select Valid` + `[LockOn]SelectAreaIsValid:4 all=%d num=%d`；`…In Af Assit Running` + `[AfAs]InAfAssitRunning:4 all=%d num=%d` |

## 3. 数据源：Mario（ZPD/DFE 散焦引擎代号）

- `ZpdMarioSequenceData::SetRecognitionData`、`ZpdMarioSeqInvoke/Error`（LC 任务域）
- `Camera::DFECore::CorrMarioPgGetter / CorrMarioPgaGetter`（DFE=散焦估计核，Pg/Pga=相关算子）
- Exif：`LC: [Exif] Makernote(Mario Debug Data) is not completed.`（调试数据进 Makernote）
- 依赖检查日志：`[DefocusFace]Mario Detect Not available`、`[DefocusKeypoint]Mario Detect Not available`、
  `TrackletUpdater::zpdResultValidateForTrack mario ng`、`[Keypoint]Not Mario/Af Align.`
- **Mario = ZPD（相位检测）→ DFE 散焦解算管线的引擎名**。DefocusFace 的 df/min_df 全部源于此。

选择器持有的三个提供者（FUN_002dc2cc 的 param_1[1..3]）：
- `param_1[1]` 设置/帧上下文（vt+0xA0=模式查询、vt+0xB0、vt+0xE0=取帧、vt+0xC8=AfAssist 运行标志）
- `param_1[2]` **Mario/DfSelect 提供者**：vt+0xC=Mario 可用性、vt+0x10=Movie LockOn/Subject 模式、
  vt+0x20=区域内 df 判定（返回 min_df）、vt+0x1C=区域候选选择
- `param_1[3]` ZpdDensity 提供者：vt+0xC=getZpdDensityInfo、vt+0x10=getLcZpdResultInfo

## 4. replacePriorityFace 决策树（FUN_002dc2cc，日志行号实测）

```
out: selected=0(+4字节), id=0(+5), permit(+3)=1
① 主主体列表为空(*obj+0xD4==0) → "getListConst().empty skip main_subject_judge_permit :%d" (0x150) → 返回
② FUN_00873054() 取列表；非空时对列表置 +0x75=1
③ FUN_00878d70() 可判性 == 0 → "isAbleToJudgeFaceUsingDefocus false skip" (0x15a) → 返回
④ 跟踪模式标志(param_3+1)：
   !=0（跟踪中）：
     FUN_00873054(*obj)：列表空 或 状态+0x30 ∉ {1,2}
       → "Tracking for not faces main_subject_judge_permit:%d" (0x16b)，permit=0
     否则 → "Tracking for a face main_subject_judge_permit :%d" (0x165)，permit=1
   ==0（非跟踪）→ ⑤
⑤ ZpdDensityInfo == 0 → "get ZpdDensityInfo fail …" (0x17c) → 返回
⑥ getLcZpdResultInfo == 0 → "getLcZpdResultInfo false …" (0x187) → 返回
⑦ Mario 可用性(vt+0xC) == 0 → "Mario Detect Not available …" (0x18e) → 返回
⑧ Mario 模式(vt+0x10)==1（Movie LockOn/Subject）：
     judgePriorityFaceInLockOn(§5) != 1
       → "Fail to select priority Face in Movie lock-on/Subject" (0x19d)，permit=0，返回
     == 1 → curr_top(§6) → 收尾日志 (0x199)
   否则 vt+0xC8()==1（AfAssist 运行中）：
     FUN_002dca34 为**abort 桩** → 此路径本构建不可达（日志 0x1a5/0x1a8 "judgePriorityFaceInAfAssitRunning
     true …"、0x1b0 "Fail to select priority Face in Movie Af Assist …"）
     （配套日志 "[DefocusFace]No DfSelectTargetFace In Af Assit Running"/"[AfAs]InAfAssitRunning:4 all=%d num=%d"）
   否则 → "NotMovieLockon not movie af assist main_subject_judge_permit:%d" (0x1b7)，permit=1
```

## 5. judgePriorityFaceInLockOn（FUN_002dc5c8）

```
① 快速路径：主主体存在 && 录制标志(param_5+2) && 列表成员数(+0xC)∈{1,2}
     → "current top is tracking Face id:%d" (0x1d9)；selected=当前 top id；返回 1
     （≤2 张脸时无歧义，直接沿用当前主主体）
② PreTopFaceID(§5.1) 取上一帧优先脸 preTop；条件：存在 && +0x71(选中) &&
   (设置 vt+0xB0()!=0 || preTop+0x103!=0)，否则跳到 ③
   对 preTop 的三块候选区域依次尝试（每块：取 rect → 经 FUN_00872faE 以当前帧变换 →
   构造判定矩形 → 若 设置 vt+0xA0()!=0（跳过 df 判定的开关）或 Mario vt+0x20(矩形,…)==1（命中））：
     区域1: flag +0x170, rect +0x171 → "[DefocusFace]judgePriorityFaceInLockOn PreFaceIsInLockOnRange
            face id:%d min_df:%d" (0x1fa)   ← FACE 区
     区域2: flag +0x15B, rect +0x15C → "… PreFaceIsInLockOnRange head id:%d min_df:%d" (0x20e) ← HEAD 区
     区域3: flag +0x19A, rect +0x19B → "… PreFaceIsInLockOnRange body id:%d min_df:%d" (0x223) ← BODY 区
   任一命中 → selected=preTop.id；返回 1
   （＝上一帧优先脸只要其脸/头/躯干区域内仍出现散焦最优点，就保持选中）
③ 兜底：Mario vt+0x1C(矩形,…) == 1 → FUN_002dcdd8 —— **abort 桩**（本构建不可达）
   （兜底候选由 getMinAverageDefocusFace / getMinReliableDefocusFace 在 SelectDfAreaInfo[24] 里
   取 min df，日志 "is_realiable_lockon_rect:%d is_min_defocus_face_exist:%d
   select_defocus_abs_:%u, min_defocus:%u"；不可选 → "[DefocusFace]No DfSelectTargetFace
   In Af Select Valid" + "[LockOn]SelectAreaIsValid:4 all=%d num=%d"）
```

### 5.1 PreTopFaceID（FUN_002dcd44）

遍历主主体链表（obj+0xCC，同 judgeMainSubject 的链表），取第一个 **+0x74 标志**（优先脸候选）
置位的节点，并按类型 +0x28 校验：类型 1 → `FUN_002e5d70(*(node+0x24)+0xD8)`；
类型 2 → `FUN_002e5d70(*(node+0x20)+8)`；通过则日志 `"[DefocusFace]PreTopFaceID:%d"` 返回该记录。

## 6. curr_top 应用（FUN_002dc8c4）

若 selected id == 当前链表头 → `"curr_top: select_t…"`（已是 top）。
否则在链表中找该 id 的节点（同样做 +0x28 类型 1/2 校验），日志 `"curr_top:%d select:%d"`，
然后**把该节点搬到主主体链表头部**（长度 +0xD4 > 0xF 时先经 FUN_002dd6F4 从 +0xD0 溢出结构搬移；
摘链/头插后计数 -1，节点还池 +0xD8）。**＝景虚化选择的最终效果：df 最优者成为下一帧主主体。**

## 7. expandAfOverlapArea（FUN_002dbf58）

`Frame&` 输出 = AF 点重叠脸区域的扩张框：按 `bbox_type`（0–4，与 HumanCross/Keypoint 的
BboxType 同族）分别以 `AfPointOverlapFaceExpandAreaParam{ratio_x@+0, ratio_y@+1, flag@+2}` 的
**/16 定点比例**对画面（FC_PICTURE_INFO w/h @+8/+10）做四方向扩张，再 FUN_008507D8 裁剪到画面、
FUN_00872FAE 与当前帧变换矩形相交，输出 Frame。供 `isAfSelectPointOverlapFace
（"[DefocusFace] isAfSelectPointOverlapFace isInside=false bbox_type=%d"）`与
`isLockOnRectangle(SelectDfAreaInfo, bbox_type, LOCK_ON_RECTANGLE_JUDGE_TYPE)` 使用。

## 8. 与 HumanCross df 的关系

同一套 df（散焦量，Mario/ZPD 产出）在两处消费：
- **HumanCross FrontJudge**（REPORT_human_cross.md）：交叉时比较两脸 df，糊者=前景遮挡者；
- **本模块**：24 个 `SelectDfAreaInfo` 中取 min df（getMinAverage/MinReliable），最清晰者=优先主体。
方向相反但自洽：对焦主体应清晰（df 小），走进画面的遮挡者必然脱焦（df 大）。

## 9. 不确定项

1. FUN_002dca34 / FUN_002dcdd8 为 abort 桩 → AfAssist 路径与 df 兜底选择在本构建的实际执行体
   可能位于 FC 层姊妹文件（priority_defocus_face_selector.cpp，`[DefocusFace]Fail_to_select_prio…`
   系列日志在 0x29xxxx 区已见：isMovieLockOn/isMovieAfAssist/Mario_Detect_Not_av…），未展开。
2. `SelectDfAreaInfo` 记录完整布局只确认 {state@+0, rect@+0xC, type@+0x14}（构造器 FUN_002dd568
   两分支：vt+0xA0()==1 → type=2/rect+0x115；param_4==3 → type=3/rect+0x18F,flag+0x18E），
   df 数值字段的填充点未逐行。
3. preTop 三区域 rect 的产生方（+0x171/+0x15C/+0x19B 的写入者）未回溯；疑为跟踪框/预测框/搜索框。
4. 设置 vt+0xB0 / vt+0xA0 / vt+0xC8 的语义按调用点用法反推（录制判定/跳过 df 判定/AfAssist 运行中）。
5. replacePriorityFace 的调用方（虚表分发，磁盘无直址引用）未定位；推测在主主体判定流水线
   （与 HumanCross 同层）。
