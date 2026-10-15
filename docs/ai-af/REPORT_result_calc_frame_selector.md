分析完成。以下为完整报告。

---

# α1 II AI 对焦 post 层：结果计算 / 置信度 / 滞回 / 跨帧选择 逆向报告

**方法与佐证来源**：所有函数来自 `<workspace>/firmware_reverse/decompiled/a1m2_cpapp.c`(Ghidra ARM32/Thumb-2,无符号)；所有格式串、浮点/整型常量均从 `copro/cpapp-b.bin` 原始字节读出(**文件偏移 = 虚拟地址 − 0x108000**,已用 `process/post/result_calculator.cpp` 字符串 @0x01051dd1↔file 0xf49dd1 校准，函数序言 push 已验证)。日志宏为 `FUN_002bf488(level, ?, 行号, 文件名, 格式串, ...)`。

---

## 1. process/post/result_calculator.cpp (0x306178–0x308588)

### 1.1 FUN_00306178 — `isSameSubjectInPredictedArea`(OutOfFaceArea / eye_dist_over)

**输入**:(this, rec_new, rec_old);记录字段:`+0x4c` u16 eye_dist、`+0x50/+0x52` u16 pos.x/y、`+0x54/+0x56` 目标重力点 x/y。
**输出**：1 = 同一主体仍在预测区域内；0 = 丢弃。

伪代码：
```
scale_a = cfg(obj1).vt[0xa0]();  scale_b = cfg(obj2).vt[0xa4]()   // 两配置系数,为 0 直接返回 0
d = |rec_new.eye_dist(0x4c) - rec_old.eye_dist(0x4c)|            // u16 差
if (d < scale_a * rec_new.eye_dist) {                            // 眼距变化容差内
    half = (int)(2 * rec_new.eye_dist * scale_b) >> 1            // = eye_dist * scale_b
    box  = [pos.x-half, pos.x+half) × [pos.y-half, pos.y+half)   // 以旧位置为中心的预测框
    if (rec_old.gravity(0x54,0x56) ∈ box) return 1
    else → 日志 "(OutOfFaceArea) org frame : x:%d y:%d w:%d h:%d target gravity : x:%d y:%d" (行 0x3f2)
} else → 日志 "(eye_dist_over) src_dist:%d targ_..." (行 0x3e3)
return 0
```
即**双重几何门**：①新旧眼距相对变化超过 `scale_a` 倍 → 丢；②旧结果重力点跑出“以新记录位置为中心、半宽=新眼距×scale_b”的预测框 → 丢。`scale_a/scale_b` 为运行时配置(无静态值，存疑标量)。调用方 `FUN_00306df8` 用它判定 best 与当前是否“同一目标仍在原处”。

### 1.2 FUN_00306334 — `cbDetectedDiffers`(1st_id/prio_id/cb_detected)

**输入**:(ctx, `*p1st` u8, `*prio` u8)。**输出**：1 = “1stCB 与 prioCB 都检出且二者 id 不同”。
```
日志 "cb_detected(%d, 1st:%d prio:%d)"   (ctx+0x1254 为主开关)
if (ctx->0x1254 == 0) return 0
if (p1st != 0 && prio != 0) {
    日志 "1st_id:0x%04X prio_id:0x%04X"
    return !FUN_00895694(p1st, prio)     // 两 CB 结构不相等 → 1
}
return 0
```
调用点在 FUN_008973fa 内(`FUN_00306334(param_1, param_1+0xa0, param_3)`)。FUN_00895694 内部未展开(存疑：精确比较哪些字段)。

### 1.3 FUN_003063f8 — `drop_by_beta`

**输入**:(this, records_base, idx, [beta 64-bit 低/高在 param_5/param_6]);记录 stride **200** 字节，字段 `+0x08` 锁、`+0x0c` id、`+0x54` u16 beta、`+0xb1` part。
**阈值**：按 part 从配置取两个 64-bit 值，经 `FUN_00897004` 定标(值×scale>>24÷rate)得 `beta_high`、`beta_low`。
**判定(已用 capstone 反汇编 0x3064f0–0x306506 确认，非推测)**：
```
drop ⟺ (u16)rec.beta < beta_low  ||  rec.beta > beta_high     // 仅保留 [low, high] 带内
```
丢时：日志 `"beta high:%d low:%d"`(行 0x440)→ `"drop_by_beta(%d, %d)"`(行 0x44b,参数 beta、id)→ `FUN_00897080(0x80000, rec+8, …)` 给记录置 **0x80000** 丢弃位 → 全局计数器 **`_DAT_0198bdd0`(u16)++**。

### 1.4 FUN_00306598 — `drop_by_eye_dist`

记录同上(stride 200)。
```
thr_ok = cfg.vt[0xc0](part)==1;  cur = FUN_00892170(ctx,0)      // 当前眼距 (float)
if (cur == -1.0) 不丢
drop ⟺ (float)rec.eye_dist(u16 @+0x54) > cur + k*cur          // k = cfg.vt[0xcc]()
```
丢时：日志 `"drop_by_eye_dist(%d, %d)"`(行 0x475)→ 置 **0x100000** 位 → 计数器 **`_DAT_0198bdd2`(u16)++**。语义：记录保存的眼距远大于当前眼距(目标显著变小/远离，超容差 `k`)→ 丢。

### 1.5 FUN_003066d8 — `preferOldNewBy43Type`(old/new 4:3 对比)

**输入**：old、new 两条 prio-frame 记录(`+0x08` f32 score、`+0x10` u32 type)。
```
t = type & 0xff0
若 old.type ∈ {0x160, 0x170, 0x180, 0x260} → return false (保旧)
若 new.type ∈ {0x160, 0x170, 0x180, 0x260} → return true  (用新)
否则 return old.score <= new.score
```
这四个 type 值(掩码后)构成一个“特殊/优先类型”集合——使对应方向的比较被短路。枚举具体含义(0x16/0x17/0x18/0x26 对应何部位/形态)**未证实**，仅确认该集合与“4:3”日志串 `old:%d new:%d old(4:3)? new(4:3)?` 关联。0x170 亦出现在 XRI(FUN_0030d424:`(type & 0xfffffff0) == 0x170`)作为豁免条件，说明该集合是“宽高比/类型特判”组。

### 1.6 FUN_003067ac — `isPriorBetterThanCurrent`(center/score 比较器)

**输入**:(this, src, dst, use43)。`+0x08` f32 score;`FUN_00896d40` 取某坐标(单轴)。
```
if (src.score == 0) return true                        // src 无分 → 换
sx = axis(src); dx = axis(dst)
if (dx < sx * 0.9035) {                                 // DAT_00306914 = 0.9035 (0x3F674BC7)
    if (mode().vt[0x4c]()->val != 0x15) return true
    return FUN_00891e68(ctx) == 0
}
if (sx * 1.1025 < dx) return false                      // DAT_00306918 = 1.1025 (0x3F8D1EB8)
if (!use43) return dst.score >= src.score
// use43==1: 与 1.5 相同的 {0x160,0x170,0x180,0x260} 特判短路,否则 score 比较
// 日志 "src:%d dst:%d src(4:3)? dst(4:3)?" (行 0x515)
```
**常数表**：0.9035(约 -9.65% 单轴死区下限)、1.1025(约 +10.25% 上限)——构成单轴位置的滞回带，防止两目标接近时来回抖动。`0x15` 为某模式枚举(含义未证实)。

### 1.7 FUN_00306d48 — `af_overlap_by_af_area`

```
if (*rec == 0) return 0
return FUN_00897222(rec+0x2c)   // rec+0x2c 处 {cx@+8,cy@+a,w@+c,h@+e} 矩形与当前 AF 区域求交→bool
```
命中时日志 `"af_overlap_by_af_area lx:%3.1f ly:..."`(行 0x668)。

### 1.8 FUN_00306df8 — `isUpdateWithTrackingForced`

**输入**:(this, best, status)。**输出**：1 = 允许“强制用跟踪结果更新”。
```
if (FUN_00891d4e(ctx) == 1) {                       // 某 state
    p = vtable+0x48();  if (FUN_0086174e(p) == 0) → "best is expired" (0x675) → return 0
    if (FUN_00306d48(p, best) == 1) → "best is expired, af overlap" (0x67a) → return 0
}
if (FUN_00891d3e(ctx) == 4)     → "verifying" (0x682) → return 0
if (status == 0)                → "best is invalid" (0x688) → return 0
// status != 0:
thr = cfg.vt[0xc](best.part@0x730)                   // prio 分数门限
if (best.score(+8) < thr)       → "prior score(%4.3f) is NOT HIGH" (0x695) → return 0
cur = FUN_00891b78(ctx)                              // 当前记录
if (FUN_00306178(this, best, cur) == 1) → "same ..." (0x69e) → 走更新路径
else {
    if (FUN_0089630e()==0 && vtable+0x174()!=0)
        pick = FUN_008971b6(this, cur, best, prio_part)   // 按 AF-overlap+part 择优
    else {
        if (FUN_003067ac(this, cur, best, 0)) cur = best  // 分数/位置比较择优
        pick = cur
    }
    if (FUN_00897354(pick, best) != 1) return 1       // 与 best 非同一结果 → 强制
    → "prior ..." (0x6b1) / "prior is nearest" (0x6bf) → return 0
}
```
`FUN_00897354` = 逐字段相等比较(id@+4、score@+8、+0x60/+0x64/+0x74/+0x78/+0x88/+0x8c 等)——判定两条记录是否“同一份结果”。

### 1.9 FUN_00307034 — `[startCalc]` 调试打印(A/H/S)

`param_2==1`:循环 5 个 part 记录(stride 0x148),打印 `"[startCalc][H(%d)=%d S(%d)=%d] (%d, %d, %d, %d),(%d, %d)(%s id=%d)"`,其中 `%s` 为 **"o"/"x"** 单字符字面量(0x30729c="o"、0x3072a0="x",由 `*(rec+0x210)` 选择)——o=该 part 有跟踪，x=无。`param_2==0`:打印 `"[startCalc][A=%d,S=%d] (%3.1f, %3.1f)..."`。纯日志，无逻辑。

### 1.10 FUN_00307348 — `getFoundStatus` 主流程(FoundStatus 状态机)

**FoundStatus 计算**(字符串佐证:`Camera::FC::Keypoint::FoundStatus Camera::FC::Keypoint::ResultCalculator::getFoundStatus(AedConfidence, StapleConfidence)`):
```
aed = FUN_00891abc(ctx)          // AedConfidence ∈ {0,1,3}(2 会触发 assert)
stpl = FUN_00891b24(ctx,&b)      // StapleConfidence ∈ {0,1,2}
FoundStatus = (aed==3) ? 2 : (stpl==2) ? 3 : (aed==1) ? 1 : 0
```
**状态表**：

| FoundStatus | 含义(由映射反推) |
|---|---|
| 0 | 未确立(无 AED、无 staple 稳定) |
| 1 | AedConfidence==1(低置信检出) |
| 2 | AedConfidence==3(高置信检出，XED 主导) |
| 3 | StapleConfidence==2(stable 跟踪稳态) |

**主流程**：拷贝 5 个 part 记录 → 逐个 `FUN_0030780c` 打印 → `FUN_00896530(this+0x20, this+0x98)`(其中含字符串 `set_SecondAedConfidence(AED_CONF_...)`、`id:%d set_score_to_0 valid_to_...`)→ 取 prio 记录、算 FoundStatus → `FUN_00306df8(isUpdateWithTrackingForced)` → `FUN_008973fa(this, rec, 1)`(见 §1.11 后注)算出 AedConfidence 并 `FUN_00891aae(ctx, st)` 写回 → 状态机收尾：
```
if (AedConfidence==3 && FUN_008921be(ctx,0)==1)
    "[ResultCalc] Cancel TrackingCanc[el...]" (行 0x89a) → FUN_008921aa(ctx,0,0) 清除
if (FUN_008921be(ctx,0)==1)
    "[ResultCalc] increment TrackingCancelByDfValidRatio dds counter!" (行 0x89f)
    *(s16*)(FUN_008854a2() + 0x1e2) += 1
```
即：** TrackingCancelByDfValidRatio 计数器每帧递增，AedConfidence==3(高置信)时清零**——一个“丢焦保护”滞回计数器。

**FUN_008973fa(关键连接件，0x89 区)**:`stpl_conf = judge_score(当前 XHD 记录)`(对应字符串 `KeypointXhdResult::getJudgeScore/isIOUJudgeScore`),按 part 取两个门限 t8=vt[+8]、t_c=vt[+0xc]:
```
AedConfidence = (t_c <= stpl_conf) ? 3 : (t8 <= stpl_conf) ? 1 : 0
```
并前置条件：记录 score≥门限且(模式==2 时经 FUN_008971b6/FUN_003067ac+FUN_00897354 与当前 best 同目标)才更新置信。这就是 **staple 判分→AedConfidence 的阈值化**。

### 1.11 FUN_0030780c — 结果打印

`"%s id:%d, res:%d, cx:%d, cy:%d, w:%d, h:%d, r:%d sc:%4.3f el:%2.1fx%2.1f er:%2.1fx%2.1f n:%2.1fx%2.1f r:%2.1f y:%2.1f"`,记录字段 `+0x0c` res、`+0x10` id、`+0x14/+0x16` cx/cy、`+0x18/+0x1a` w/h、`+0x1c` r(s16)。tag 默认 `"result"`(0x3078d0),getFoundStatus 传 **`"prio"`**(0x3077d0)。

### 1.12 FUN_00307af0 — `1stCb_part` cancel 应用

```
flags[5] = vtable+0x18(this+0x94)             // 1stCb 指定的 part 位图
for p in 0..4: if flags[p]: 
    c = FUN_0089222e(ctx, p)                  // 读该 part 当前 cancel 态
    日志 "1stCb part:%d prev_cancel:%s"  ("o"/"x" @0x307ba4/0x307ba8)
    FUN_008921ee(ctx, c, p)                   // 写回
ok = FUN_00307bcc(this)                        // EYE-not-included 校验
FUN_00891aae(ctx, ok ? 3 : 0)                  // 直接把 AedConfidence 置 3 或 0
return ok
```

### 1.13 FUN_00307bcc — `updateXedFromPrio + eyeIncludedCheck`("EYE not included in part")

```
if (prio 存在 && part 匹配 *(cur+0x730) == prio.part(0xa9)):
    FUN_0030960c(&out, this+0x1120, prio, 1)          // 从 XED 历史生成结果
    拷入记录 +0x2c..+0x54(res/id/cx/cy/w/h/r/score/eye 位置等)
    if (FUN_00306178(this, rec, prio) == 1):          // §1.1 预测框内
        for part 1..4:
            if part 有效且 part 映射(+0x350 表)非 -1 且
               FUN_0089f6ec(this+0x8a8, prio, entry) == 0:      // FrameSelector 校验失败
                "[WARN]... EYE not included in part %d" (行 0x9b1) → return 0
        FUN_00891b84 / FUN_00892024(prio 落库)
        return 1
return 0
```
`this+0x8a8` 即 **FrameSelector 实例**(与 §5 同一对象)，`FUN_0089f6ec` 为“眼睛包含在 part 框内”检查(内部未展开，存疑)。

### 1.14 FUN_00307d5c — `ResultCalc`(staple_confidence 主入口)

帧级编排：
```
FUN_0030bb58(this+0x8a8, mode!=0, FUN_0089630e())   // FrameSelector 初始化(§5.1)
FUN_00897f94(prev_flags)                             // 上一帧 part 标志
FUN_00307348(this)                                   // getFoundStatus(§1.10)
FUN_00897db8(this)
FUN_0030c3c8(this+0x8a8)                             // ScoreAndFrame pickup(§5.4)
FUN_0030c304(this+0x8a8)                             // updateBest(§5.5)
FUN_00302b40 / FUN_003049e8(this+0x998, +0x894, +0x98, +0x888)   // result_converter/sender
[debug] FUN_00307034 A/H/S
part = switch(mode){0:+0xa9, 1:+0x269, 2:+0x3b1, 3:+0x4f9, 4:+0x641} → *(rec+0x730)
prev/cur part 位图逐个比较:
    cancel = (prev[p]==0 && cur[p]!=0) ? 1 : (valid[p]==0 ? FUN_0089222e(ctx,p) : 0)
    日志 "part:%d cancel:%s tracking:%d prev:%d cur:%d" ("o"/"x" @0x308068/0x30806c)
    FUN_008921ee(ctx, cancel, p)
FUN_00897e60 / FUN_00897c34
日志 "[ResultCalc] staple_confidence:%d %d" (行 0x9e5;FUN_00891b42 / FUN_00892198)
if (AedConfidence==3) FUN_002f4f9c(FUN_0088940e(), 0)
```

**结果被丢弃的全部条件汇总(§1)**:
1. OutOfFaceArea:旧结果重力点出预测框(半宽=眼距×scale_b)(FUN_00306178,日志行 0x3f2)
2. eye_dist_over:|新旧眼距差| ≥ scale_a×新眼距(FUN_00306178,行 0x3e3)
3. drop_by_beta:beta ∉ [beta_low, beta_high](FUN_003063f8,行 0x44b,flag 0x80000)
4. drop_by_eye_dist:rec.eye_dist > 当前眼距×(1+k)(FUN_00306598,行 0x475,flag 0x100000)
5. EYE not included in part(FUN_00307bcc,行 0x9b1)
6. isUpdateWithTrackingForced 的 5 个拒绝分支(1.8,均为"不强制更新"而非删记录)
7. 相关但在本段之外：FUN_008970e0 有 `"zDdrop_by_roll( %2.1f, %d ) limit(...)"`(roll 超限丢)，FUN_0089710e `"[EEP]D id:%d ret:%d exp:%1.3f dis..."`(期望眼距偏差检查)——同属 result_calculator.cpp 的丢弃链，细节未展开(存疑)。

**staple 置信度如何计算**：见 §2(FIR 加权)+ §1.10 FUN_008973fa 阈值化(≥t_c→3, ≥t8→1, 否则 0)+ StapleConfidence(FUN_00891b24,∈{0,1,2},2=稳态)。原始 staple 分数由 STAPLE 相关滤波跟踪质量(Adam 侧)产生，固件侧做 FIR 平滑与双门限量化。

---

## 2. result_hysteresis_calculator.cpp (0x308588–0x3088dc)

### 2.1 FUN_00308588 — `checkBufferClear`(时间滞回)

**状态**(this,两个 FirCalculatorType 各 0x10 字节:`+0x10` u64 last_time、`+0x18` bool "非 Cancel"、`+0x1a` s16 clear_count、`+0x1c` bool flag;数据区按 type×39000 字节索引)。
```
valid = FUN_00892198(ctx,1);  aed = FUN_00891abc()
if (FUN_00899748(valid, &last_time, aed!=3, 0) == 1):      // 首次/超时重置
    last_time = now_us;  日志 "[ResultHysteresisCalculator] time..." (行 0x59)
if (!(valid && aed==3) && last_time != 0):
    timeout = cfg.vt[0xd4](part_key)                        // 64-bit 门限(us)
    if (timeout <= now_us - last_time):                     // 缓冲清空
        clear_count(++@+0x1a)
        日志 "[ResultHysteresisCalculator] buffer clear(%d)!! claer count:%d usec:%d eye_lost_time:%d" (行 0x6d)
        ring_count(+0x9854)=0; hdr(+8)=0; last_time=0
        if (!FUN_00892198(ctx,1)) flag(+0x1c)=1
*(bool*)(type_entry+0x18) = (aed != 3)
```
**参数**：超时门限为配置值(无静态常数)；AedConfidence==3(高置信)期间不清缓冲——即“眼睛丢失后保持 N µs 再清 FIR 历史”。

### 2.2 FUN_00308728 — `calculateFirFilter(type, target)`

**环形缓冲**：20 槽(0x14),槽 stride **0x740**,count@`+0x9850`,写指针@`+0x9854`;槽内有效标志@`+0x750`;**type 0 读 u16 staple 置信 @槽+0x7a4,type 1 读 f32 xed 分数 @槽+0xa044**。
```
w[10] = cfg.vt[0xc8](...)                      // FIR 权重表(最多 10 抽头,配置)
n     = cfg.vt[0xc4]()                          // 实际抽头数
for i in 0..n-1:
    slot = (count - min(i, count-1) + 20) % 20  // 由新到旧
    if slot 有效: sum_w += w[i]; sum_x += sample(slot) * w[i]
FUN_0089215a(this+0xc, type, sum_x / sum_w)     // 存平滑后分数
```
**规则**：对最近 n 帧的置信度做 FIR 加权平均(权重递减，具体数值为配置)；缓冲由 §2.1 的超时逻辑整体清零，形成“时间+缓冲”双重滞回。

---

## 3. xedxhd/adam_callback_procedure.cpp + adam_result_maker.cpp (0x30a0c0–0x30b8d0)

### 3.1 FUN_0030a0c0 — `Adam1stCallback`
```
if (cfg(this+0x18).vt[0x1a0]() == 1) → FUN_002be698(handle,1,file,0x45)   // 仅通知
else:
    det = cfg(this+4).vt[0x18]() ; *(this+0x3c) = det
    if (det == 0) → FUN_002be698(...,0x54)          // 无检出通知
    else          → worker(this+8).vt[0x30](handle, *(this+0x24))   // 派发推理作业
    cfg(this+0xc).vt[0x14]()
    日志 ">>> Adam1stCallback det:%d handle:0x%04X" (行 0x5c)
```
### 3.2 FUN_0030a190 — `Adam2ndCallback`(收到什么数据)
```
日志 ">>> Adam2ndCallback handle:0x%04X" (行 0x61)
cfg(+4).vt[0xc]();  worker(+8).vt[0x30](handle, buf)          // 取推理输出
ip_flags = {0};  FUN_0030a360(this, &ip_flags)                 // update_ip
cfg(+0xc).vt[0xc](&ip_flags)                                   // 应用 IP 更新
cfg(+4).vt[0x1c](*(this+0x3c)); cfg(+4).vt[0x20](+0x34, +0x24, +0x28)
if (FUN_0089c9da(this)==1) → 单例.vt[0x30]() + FUN_002bef4c(x, 0xc)   // 超时 0xc 的信号
info = FUN_008926aa(*(this+0x10))                              // 图像信息(0x30 字节):
   [0],[1]&0xFFFFFF00, +0x10..0x14, u16@+0x18/+0x1a/+0x1c/+0x1e/+0x20, u8@+0x22, [9],[10], u8@+0x2c/+0x2d, [12]
   (对应 result_manager 日志 "adam image info id:0x%X cnt:%d prop:%d bol:%d handle:0x%X id:0x%X")
...信号量/管线推进(cfg(+0x1c).vt[0x38/0x3c], uVar7 = cfg(+0x18).vt[0x70]→u16@+6)
*(this+0x3c) = 0
```
即 **2nd 回调拿到：推理输出缓冲句柄、IP 更新表、帧图像信息(id/cnt/prop/bol/handle)**，随后触发 post 管线。

### 3.3 FUN_0030a360 — `update_ip`
```
if (*(u16*)(this+0x2c) >= 2) return          // 只处理前 2 帧的 IP 表
base = *(this+0x38) + cnt*5                   // 每帧 5 字节: [count, (id,pad)*]
for each id:
    if (2 <= id <= 5):  flags[1]=flags[2]=flags[3]=1; flags[4]=1
    elif (id < 2):      flags[0]=1
    日志 "update_ip %d up:%d %d %d %d %d" (行 0xbd)
```
### 3.4 FUN_0030a418 / FUN_0030a49c — `ResultMaker::invalid_beta / invalid_Focal`
```
v = get64(cfg this+0x30 /*beta*/);  if (v==0) → "[ResultMaker] invalid_beta prev..." 取缓存 *(this+0x60)
else 缓存并返回 v                    // Focal 同型(get64(this+0x48), 缓存 +0x68, 行 0x42d/0x43c)
```
beta/focal 均为 u64,持久化于 ResultMaker 对象，配置失效时沿用旧值。

### 3.5 FUN_0030ac8c — ResultMaker XED dump("ResultMaker S:/E: XedResult")

本函数是 **dump/校验打印**(`"[ResultMaker S:  XedResult num=%d"` 开头、`"[ResultMaker(E)] num"` 结尾)，从中可完整还原两个结构：

**Adam 原始 XED 帧缓冲**(base=*(this+4),环式:`+0x2744` 帧索引、`+0x2748` num,帧 stride **0xd14**,帧内 `+0xd1c` 人脸数，脸 stride **0x344**):

| 偏移(脸基址) | 字段 |
|---|---|
| +0xd24 | id u32 |
| +0xd28/+0xd2a/+0xd2c/+0xd2e | cx/cy/w/h u16 |
| +0xd30 | roll s16 |
| +0xd40 | class u32 |
| +0xd44/+0xd48/+0xd4c | score / pitch / yaw f32 |
| +0xd50/+0xd51/+0xd52 | visibility eL/eR/nose u8 |
| +0xd58 → +0xd5c | eye_L_num u32 → 关键点数组 {f32 score, s16 x, s16 y}×n |
| +0xe5c → +0xe60 | eye_R_num → 数组 |
| +0xf60 → +0xf64 | nose_num → 数组 |

**转换后 `KeypointXedResult` 环形数组**(base=*(this+0xc),`+0x988` 索引、`+0x98c` num;记录 stride **0xC8**,从 +0x340 起)：
`+0x00` valid、`+0x08` score f32、`+0x60/+0x64` elx/ely、`+0x74/+0x78` erx/ery、`+0x88/+0x8c` nx/ny(f32)、`+0xa4` image u32(打印 %04X)、`+0xa9` target、`+0xaa` part、`+0xb0` beta u64、`+0xb8` focal u64。日志:`"KeypointXedResult(%d) valid:%d target:%d part:%d image:%04X score:%4.3f elx:%3.1f ely:%3.1f erx:%3.1f ery:%3.1f nx:%3.1f ny:%3.1f beta:%llu focal:%llu"`。

### 3.6 FUN_0030b0c0 — ResultMaker XHD dump

**Adam 原始 XHD 缓冲**(base=*(this+8),`+0x1e80` 索引、`+0x1e84` num,目标 stride **0xa24**):`+0xa38` id u32、`+0xa3c..+0xa42` cx/cy/w/h u16、`+0xa44` roll s16、`+0xa54` num、`+0xa58` 数组(条目 16 字节：f32 score,s16 x1/y1/x2/y2,u8 type 等，日志 `"array(%d) score:%4.3f x:%d y:%d w:%d h:%d"`)。

**`KeypointXhdResult` 数组**(base=*(this+0x10),`+0x1ee8` 索引、`+0x1eec` num;外层 stride 0xa48,记录 stride **0x148**):`+0x18`? valid(+0xa60)、`+0xab4` image u32、`+0xab9` target、`+0xaba` part、`+0xac0` beta u64、`+0xac8` focal u64、`+0xad0` frame_array_num → 数组条目 24 字节(f32 score + x/y/w/h s16,日志同上)。日志:`"KeypointXhdResult(%d) valid:%d target:%d part:%d image:%04X beta:%llu focal:%llu"`。

**注**：真正的“生成”代码(Raw→KeypointXxxResult 的拷贝/换算)不在 dump 函数内，应在 `FUN_003099f8`/`FUN_003088dc`(result_manager/sender 一带)，本次未展开(存疑项)。

---

## 4. xedxhd/calculation_result_status.cpp (0x30b8d0–0x30bb58 + FUN_0089e142/FUN_0089e2c4)

**状态结构**(this):`+0x04` prev 结果、`+0x08` pre、`+0x0c` LH 锁存 bool(打印 o/x)、`+0x0e` H 计数、`+0x0f` M 计数、`+0x10` L 计数、`+0x11` LH 计数、`+0x12` V(verify 连续计数)、`+0x13` R 计数、`+0x14` M 使能 bool、`+0x15` Mmax、`+0x16` specMax、`+0x17` H 门限、`+0x18` L 上限、`+0x19` Rmax。全部由 `FUN_0089e142(this, type, part)` 按两套配置源(`this+0xd==0` → vt[0x74/0x78/0x7c/0x80/0x84/0x88/0x8c/0xdc],否则 vt[0x148..0x164])加载——**无静态数值，全部配置驱动**。

**返回值枚举(综合两函数)**：0=LOW/不稳，1=M 计数中，2=M 饱和(M≥5),4=VERIFYING,5=STABLE-HIGH。

### 4.1 FUN_0030b8d0 — `verify_out_now`
```
FUN_0089e142(this, xhd_status, part)                  // 载入阈值
pre = prev; this->pre = pre
if (specMax == 0):
    A = max(R, M);  B = max(H, stpl)                  // 合成判定
    ret = FUN_0030ba24(this, &A, &B)
else:
    if (M != 3 && stpl != 2): ret = FUN_0089e2c4(this, &xhd, &stpl, &verify)   // verify-in
    else:                     ret = FUN_0030b998(this, ...)                     // 豁免
prev = ret
日志 "[verify-out] now:%d pre:%d (o/x)" (行 0x43)
```
### 4.2 FUN_0030b998 — `verify_exemption_conf`
```
V(+0x12) = specMax;  if (prev != 5) prev = 4        // 强制进入 VERIFYING
conf = max(stpl==2 ? 3 : stpl, stpl_in)
ret = FUN_0089e2c4(this, &stpl, &conf, &local)
```
### 4.3 FUN_0089e2c4 — `verify_in`(核心阈值机，日志 `"verify-in V:%d specMax:%d, R:%d H:%d M:%d Mmax:%d L:%d LH:%d xhd:%d stpl:%d, verify:%d"`;Mmax 在日志里打字面量 5)
```
if (xhd==3 || stpl!=2) LH = 0
if (H < H_gate):                                     // 高稳定未建立
    if (xhd==3 || stpl==2): { H=H_gate; M=L=0; return 5 }         // 直接 STABLE
    if (xhd==1): { M++; V=R=L=0; return (M>=5) ? 2 : 1 }          // M 攀升
    if (xhd!=0) return 0
else:                                                // H 已达门限
    if (xhd!=3 && stpl==2) LH++
    if (M_en && LH >= Mmax) latch(+0xc) = 1                        // LH 锁存
    if (xhd==3 || stpl==2) { H=H_gate; M=L=0; return 5 }
    if (xhd==1) { M++; V=R=L=0; return 1 }
// xhd==0(丢)路径:
H=M=0; L = min(L+1, Lmax); V=0; return 0
// 高置信路径(在 H<H_gate 分支内 xhd==3 时):
if (prev==4 && verify==3):  V++;  return (V >= specMax) ? 5 : 4
else:                       R++;  return (R >= Rmax) ? (V=0, 0) : 4
```
**稳定性规则**：xhd==3 或 stpl==2 直接置稳(5);否则 xhd==1 时 M 计数爬升(5 帧饱和为 2);丢失时 L 计数(上限 Lmax)并归零 H/M;“VERIFYING(4)→STABLE(5)”需 verify 连续 3 次(V≥specMax),期间 R 次数超 Rmax 则放弃归 0;LH 为“stpl==2 连续”旁路锁存。

---

## 5. xedxhd/frame_selector.cpp (0x30bb58–0x30d4e0)

对象(this = 父+0x8a8)关键字段:`+0x14` mode、`+0x18..+0x2c` prio pos/rect、`+0xa0..+0xbd` af_area 矩形、`+0xc4` prio_id、`+0xc5` exist_prio 入参、`+0xc8` af_override、`+0xce..0xd2` apply[5]、`+0xc9..0xcd` processed[5]、`+0xd4` XED best 历史(记录 stride 200)、`+0xd8` XHD 数组头(+4 基址/+8 num,记录 stride 0x148)、`+0xe0` exist_prio_target、`+0xe8` af_select_pos、`+0xdc` 输出槽。

### 5.1 FUN_0030bb58 — init:`af_area_pos` / `af_select_pos` / `exist_prio_target`
```
mode = FUN_00892588() → +0x14;  +0xc5 = 入参2;  +0xc8 = 入参3;  +0xc7 = 0
if (mode==1): 拷贝 prio pos(+0x18/+0x1c/+0x24)+rect(+0x28)
memcpy 0x4a 字节配置 → +0x50; af_area(+0xa0..) = vt[0x48]+vt[0x14] 合成
+0xc0 = vt[0x44]();  +0xc4 = prio_id(若入参3!=0 则清 0)
for p in 0..4: apply[p]=2; processed[p]=0        // 2 = NOT_APPLIED 初值
exist_prio_target(+0xe0) = FUN_0089ea0c()        // prio_id 与当前记录 part(+0xa9/+0x269..) 或任一 XHD 记录 part(+0x59) 相符
if (FUN_0089eb12(this, cfg))                     // 需 vt[0x1dc]==0、vt[0x118]==1、vt[0x100]==1、cfg[0]&cfg[0x40]
    af_select_pos(+0xe8) = FUN_0030bd70()        // → 日志 "af_select_pos x:%d y:%d" (行 0x97)
else af_select_pos = (af_area.cx(+0xa8), af_area.cy(+0xaa))   // → "af_area_pos x:%d y:%d" (行 0x9b)
```
`FUN_0030bd70 getAfSelectPos`:调 `vt[0xc](this+0x10)` 取位；失败 → `"[getAfSelectPos] getPos failed..."` 并回退 af_area 中心。**af_select_pos 即“本帧 AF 基准点”**：优先用配置/上层给的选点位，否则用 AF 区域中心。

### 5.2 FUN_0030be00 — `cmpBest`(逐 part 决定 apply)
```
if (+0xc7 已处理过) return
flags[5] = FUN_0089eb56 逐 part 读(XHD 背景 search id 标志)
bg_active = any(flags[1..4])   (当 XHD 数组类型 (type&0xffffffe0)!=0x2c0 时才检查)
for each XHD record (stride 0x148, valid@+0):
    part = rec.part(+0x5a); arr_idx = rec.+0x140 (s8)
    if (bg_active):
        log "check_xhd_background_search_id %d %d %d cur_part %d"
        映射 part 类型:3..5→4, 6..7→7 (cur 与 rec 各做一次)
        IoU 距离 fVar11 = FUN_002ce40c(ctx, xed_rect(part), xhd_rect(arr_idx))   // IoU
        thr = vt[0x138]()
        if (xed 数组索引无效 || (同类 && thr < IoU)):
            apply 默认 2;若 FUN_0089ec80(this, rect)==1(XHD 框完全落在 AF 区域内)
            → apply = (同类型 && thr < IoU) ? 1 : 2
    else:
        cur_ov = FUN_0089ebd0(0, rec+0x28); best_ov = FUN_0089ebd0(xed, rec+0xf0)  // 与当前 AF 区域重叠
        log "af_ovelap_cur:%d best:%d"
        if (best_ov==0 && cur_ov==1):                       // 只压当前、不压 best
            if (exist_prio_target && prio_id != rec.part) skip
            if (mode==0 || af_override==0): FUN_0089ed6c(...) 命中 → apply = rec.+0x5b ? 1 : 2
            else: FUN_0089ee20(...) 命中 → 同上
        else apply = 1                                       // 直接采用
        processed[part] = 1
log "[cmpBest] apply:%d %d %d %d %d"
```
apply 语义：**1=采用该 best,2=不采用**(0 在 NearestXhdSameTarget 中亦出现)。

### 5.3 FUN_0030c304 — `updateBest`
```
log "[updateBest] num:%d confidence_u..%d %d %d %d"   (XHD num 与 +0xca..0xcd)
if (XHD num != 0): for i in 0..3:
    FUN_00891ac8(ctx, (this+0xca+i != 0) ? A : B, i+1)     // 把 apply 结论写入 per-part 状态
```
### 5.4 FUN_0030c3c8 — `ScoreAndFrame` pickup(跨帧“最佳帧”核心，字符串 `getPrioScoreFrame`)
```
base_pos = (mode && af_override) ? prio_pos(+0x24/+0x26) : af_select_pos(+0xe8)
log "base_pos x:%d y:%d" ; FUN_008860a6(glob+0x2908, base_pos)
// ① prio XED 候选(part 0):
if (part0 有效 && 状态门通过):
    dist2 = (base.x - rec.cx(+0x54))² + (base.y - rec.cy(+0x56))²
    prio_match = (prio_id != 0 && prio_id == rec.target(+0xa9)) && af_overlap(rec,+0x2c)
// ② XED 各 part 候选(循环上界 5 或 3,取决于 FUN_0089eecc/状态):
    for part: if apply[part]==1: 把 dist² 写入 xed rec 条目 +0x140、清 +0x150
              elif part 标志有效: dist² 竞争最小值;
                  仅当 (!prio_match || prio_id == rec.target(+0x121)) 才参与
                  维护:min_dist、is_best(local_98)、is_xed(local_b0=1)、best_idx
// ③ XHD 候选:
    for each XHD rec: 
        if (背景 search 模式 && rec.part>2 && 状态==1) skip
        if (!FUN_0089ef18(...)) XHD 记录作废(+0x148 头清 0)   // 与 XED 面框的 IoU/面积比不足
        elif (apply[rec.part] != 0):
            dist² = (base.x - rec.cx(+0x4c))² + (base.y - rec.cy(+0x4e))²
            if (rec.+0x5b == 0) dist² *= vt[0x1d4]()           // 惩罚系数
            仅当 (!prio_match || prio_id == rec.part(+0x59)) 参与;竞争最小
if (min == 0x7fffffff) log "pickup:non prio result"
else log "pickup:%s %s index:%d dist:%d"   // %s1 = is_xed ? "xed":"xhd", %s2 = is_best ? "best":"cur"
                                              // ("xed"/"xhd"/"best"/"cur" 为内联字面量 @0x30cbdc..)
输出 *(this+0xdc):type = is_xed ? 1 : 2;指针 = 
    is_xed ? (is_best ? *(this+0xd4)+idx*200+8 : cur_xed + idx*0x148 + 200/…) 
           : (is_best ? xhd_rec+idx*0x148 : cur_xed + idx*0x148)
    并拷贝 apply[0..4] → 输出+8..+0xc
log "prio_result:%s target:%d part:%d apply:%d %d %d %d %d"  // %s = "XED"/"XHD"/"NONE"
```
**结论**：跨帧“最佳帧”选择 = **以 af_select_pos(或 prio 位置)为基准点的最小平方距离竞争**，prio 匹配目标有参选豁免权；XED 历史帧(best,来自 +0xd4 的 200-stride 历史)与当前帧 XED、以及 XHD 检测同台竞争；非 prio 的 XHD 距离乘惩罚系数(vt[0x1d4]);XHD 框必须先过 `FUN_0089ef18`(与 XED 面框角点包含 + 面积比 > vt[0x168])。

### 5.5 FUN_0030cc14 / FUN_0030cd00 — `NearestXhdBaseInfo` / `NearestXhdAf`
```
基准备:BaseInfo 用 prio pos(+0x24/+0x26);Af 用 af_select_pos(+0xe8/+0xea)
for i in 0..num-1: d2 = (rect中心(x+w/2, y+h/2) - base)²  → 存 entry+0x78, entry+0x88=0
    取最小(初始 FLT_MAX @0x30ccdc / 0x30cdd4)
命中则 FUN_00894ce8(list);entry.+0x5b = FUN_0089f1ac(this, list)
    (FUN_0089f1ac = 该 XHD 与各 XED part 的包含/重叠优先裁决,返回 bool)
NearestXhdAf 另置 processed[rec.part] = 1
log "[NearestXhdBaseInfo] index=%d" / "[NearestXhdAf] index=%d"
```
### 5.6 FUN_0030cdf0 — `getNearestXhdSameTarget`(与上一帧连续性，prioIOU/size)
```
part = rec.part(+0x5a);映射到 XED part(0x148 记录 +0x208 数组索引);任一无效 → return 0
fMin = 0.0 (DAT_0030d13c);  bIdx = 0xff
for i in 0..rec.num(+0x70)-1:
    仅当 rec.target(+0x59) == xed_rec.target(+0x121) 且非 0:
        d = IoU距离 FUN_002ce40c(ctx, xhd_rect(entry), xed_rect(part)) → entry+0x78, entry+0x88=1
        size_ok = (scale*xed_w(+0x14c) <= xhd_w(+0x84)) && (xhd_h(+0x86) >= scale*xed_h(+0x14e))
                  失败 → "[NearestXhdSameTarget] size f..." 
        if (d < fMin && size_ok): fMin=d; bIdx=i
if (bIdx==0xff || fMin < prioIOU_thr(vt[0x134])):      // "[NearestXhdSameTarget] prioIOU ..."
    apply[part] = 0                                     // 与上一帧不是同一目标 → 不采用
else:
    FUN_00894ce8(rec); rec.+0x5b = 1
    apply[part] = (背景 search 检查) ? 0/1 ; processed[part] = 1
log "[NearestXhdSameTarget] index=%d"
```
### 5.7 FUN_0030d3c0 / FUN_0030d424 / FUN_0030d4e0 — `[XRI]`(xed_result_invalidater.cpp)
```
FUN_0030d3c0: type=rec.+0xa9; 1→FUN_0030d424, 2→FUN_0030d4e0, 其他→1(保留)
              log "[XRI] id:%d ret:%d"
FUN_0030d424(type1): xri_t = FUN_008a0a86();  is170 = (rec.type(+0x10)&0xfffffff0)==0x170
    case0/3: 若 FUN_008a0aba(eyeL) 或 FUN_008a0aba(eyeR) 判废 → ret=true
    case1: 仅 eyeL;case2: eyeR 结果取反；case4: ret=false
FUN_008a0aba(side): thr = vt[0x188/0x18c];豁免 thr = vt[0x194/0x198]
    eyeL: rec.+0x68 ≥ thr → 废;is170 且模式 → 用豁免阈值
    eyeR: rec.+0x7c 同理
FUN_0030d4e0(type2): case0: +0x68 < thrA 且 +0x7c < thrB → 废;case1: +0x68 < thrA → 废;
              case2: +0x7c < thrB → 废;case3/4: 保留。log "[XRI] type:%d"
```
即：type1 用“眼误差分≥上限判废”(is_170 类型享有更宽豁免阈值)；type2 用“置信<下限判废”。方向相反是因为 +0x68/+0x7c 在两种 type 下语义不同(误差 vs 置信)。

---

## 6. 合成：完整流水

```
Adam NPU(1st/2nd callback, §3.1/3.2)
  └─ Adam2ndCallback: 推理输出 + IP 更新表 + 帧图像信息(id/cnt/prop/bol/handle)
       └─ ResultMaker: invalid_beta/invalid_Focal 兜底(§3.4)
            Raw XED(0xd14/帧, 0x344/脸: id/cx/cy/w/h/roll/class/score/pitch/yaw/
            vis(eL,eR,nose)/eyeL·eyeR·nose 关键点{score,x,y})
            Raw XHD(0xa28/帧, 0xa24/目标: id/框/roll/num/数组{score,x1,y1,x2,y2,type})
            → KeypointXedResult(0xC8/条, beta u64, focal u64)/ KeypointXhdResult(0x148/条)
                 │
                 ▼
FrameSelector 初始化(§5.1): af_select_pos = 配置点 or AF 区域中心; exist_prio_target; apply[]=2
                 │
                 ▼
cmpBest(§5.2): 每个 part 决定 XHD best 是否采用(apply 1/2)
  ├─ 与当前 AF 区域重叠 FUN_0089ebd0;XHD 框须完整落在 AF 区域 FUN_0089ec80
  ├─ IoU FUN_002ce40c vs 门限 vt[0x138];背景 search id 映射(3..5→4, 6..7→7)
  └─ prio 目标 id 必须一致才允许改判
                 │
                 ▼
ResultCalc 主入口 FUN_00307d5c(§1.14)
  ├─ getFoundStatus(§1.10): FoundStatus = aed==3?2 : stpl==2?3 : aed==1?1 : 0
  │    └─ FUN_008973fa: staple_conf = XHD judge score;AedConfidence = ≥t_c?3 : ≥t8?1 : 0
  ├─ isUpdateWithTrackingForced(§1.8): 过期/AF重叠/verifying/invalid/分数不高/同目标 → 不强更
  ├─ drop 链(§1.3/1.4/1.1/1.13): beta∉[low,high](0x80000)、eye_dist 容差(0x100000)、
  │    OutOfFaceArea 预测框、eye_dist_over、EYE not included in part
  ├─ ScoreAndFrame pickup(§5.4): base = af_select_pos/prio_pos
  │    最小 dist² 竞争 {XED best 历史(200-stride), 当前 XED, XHD},prio 目标豁免,
  │    非 prio XHD 距离×惩罚系数;输出 {type XED/XHD, 记录指针, apply[]}
  ├─ Nearest*(§5.5/5.6): 与上一帧同一目标性校验(prioIOU 门限 vt[0x134] + 尺寸比 scale)→ apply=0 否决
  └─ XRI(§5.7): XED 结果按 type1(误差上限)/type2(置信下限)判废
                 │
                 ▼
ResultHysteresisCalculator(§2)
  ├─ 超时清缓冲:AedConfidence≠3 持续 > timeout(µs,配置)→ 20 槽环形历史清零,clear_count++
  └─ calculateFirFilter: 对 staple 置信(type0,u16@槽+0x7a4)或 xed 分(type1,f32@+0xa044)
       做 ≤10 抽头 FIR 加权平均 → FUN_0089215a 存回
                 │
                 ▼
verify 状态机(§4): H/M/L/LH/V/R 计数 + 配置门限
  xhd==3 或 stpl==2 → STABLE(5);M 5 帧饱和→2;verify 连续 specMax 次→5(否则 VERIFYING 4);
  丢失 L 计数(Lmax 封顶)→0;LH 锁存(+0xc)
                 │
                 ▼
TrackingCancelByDfValidRatio 计数器(§1.10): 每帧 ++(s16@FUN_008854a2()+0x1e2),AedConfidence==3 清零
                 │
                 ▼
result_converter / result_sender → AF 位置(af_select_pos → ScoreAndFrame 输出记录的中心)
```

**核心常数表(从二进制实测)**：

| 地址 | 值 | 用途 |
|---|---|---|
| 0x00306914 | 0.9035f | FUN_003067ac 位置死区下限(×0.9035) |
| 0x00306918 | 1.1025f | FUN_003067ac 位置死区上限(×1.1025) |
| 0x0030ccdc / 0x0030cdd4 | FLT_MAX | Nearest* 最小距离初始化 |
| 0x0030d13c | 0.0f | NearestXhdSameTarget 最小 IoU 距离初始化 |
| 0x0030d3bc | 800.0f | FUN_0030d2c0 最近点像素门限 |
| 0x002ce594 | 0.0f | FUN_002ce40c IoU 夹取默认值 |
| 0x0198bdd0 / 0x0198bdd2 | u16 计数器 | drop_by_beta / drop_by_eye_dist 统计 |
| 特判类型集合 | {0x160,0x170,0x180,0x260} | 4:3 型优先短路(FUN_003066d8/067ac);0x170 亦为 XRI 豁免条件 |
| 丢弃标志位 | 0x80000 / 0x100000 | 记录 flag 字段的 beta/eye_dist 丢弃位 |
| FIR 环形 | 20 槽 × 0x740 stride;u16@+0x7a4 / f32@+0xa044;count@+0x9850 | 滞回缓冲 |

---

## 7. 不确定项(未证实，不做臆测)

1. **配置类阈值全部为运行时值**：beta_high/low、eye_dist 容差 k、Out­OfFaceArea 的 scale_a/scale_b、FIR 权重表与抽头数、滞回 timeout、verify 的 specMax/H_gate/Mmax/Lmax/Rmax、prioIOU 门限、XRI 各阈值、`vt[0x1d4]` 惩罚系数——都经 vtable 从配置对象读取，静态二进制中无默认数值。
2. **枚举语义**：type 特判集合 {0x160,0x170,0x180,0x260} 对应的具体部位/比例；模式值 `0x15`(vtable+0x4c 解引用比较);FoundStatus 0–3 的官方命名;apply 的 0/1/2 完整含义(2=NOT_APPLIED 有初值佐证)。
3. **未展开函数**：FUN_00895694(cb 比较)、FUN_0089f6ec(eye-in-part)、FUN_0089f286/f49c/f542/f646(XHD vs XED part 裁决)、FUN_0089ed6c/ee20(cmpBest 命中判定)、FUN_008971b6 内的细节、Raw→KeypointXxxResult 的真正生成函数(应在 FUN_003099f8/FUN_003088dc)、drop_by_roll(FUN_008970e0)与 EEP(FUN_0089710e)的完整条件。
4. **FUN_00306178 的 +0x4c 字段**按日志串("src_dist/targ_dist")与用法解读为 eye_dist(u16),但无直接结构体定义佐证；两条 vtable(0xa0/0xa4,分属两个不同单例)返回的具体物理量(缩放/倍率)为推断。
5. **FUN_00306334 的确切用途**(“1st/prio CB 不一致检测”)基于调用点与日志推断；cb 对象结构未知。
6. FUN_003066d8/067ac 的调用方 FUN_008971b6/FUN_008973fa 位于 0x89 区(FUN_00896f20 附近)，该区域与 0x30 区函数互调，说明 Ghidra 把同一 C++ 子系统的热路径/Thunk 拆到了两个地址段；两段是否同一翻译单元无法从反编译输出确认。

**关键文件**：反编译源 `<workspace>/firmware_reverse/decompiled/a1m2_cpapp.c`;原始二进制 `<workspace>/a1m2_ai_pipeline/copro/cpapp-b.bin`(vaddr→file offset = −0x108000);提取工具 `<workspace>/a1m2_ai_pipeline/extract_fun.py` 与 `extract_fun_by_range.py`;函数索引 `cpapp_fun_index.tsv`。