# α1 II AI 对焦 · 优先级判定/主体类别→优先部位 完整逆向报告
## (FC::Keypoint · process/post/inclusion_checker.cpp 部位判定族 + best 维护)

> 固件: a1m2_cpapp.c (CP, ARM32, Ghidra 反编译, 基址 0x108000, 文件偏移 = 虚地址 − 0x108000)
> 分析对象: 0x302000–0x305000 区间 (inclusion_checker.cpp) + 0x88xxxx/0x89xxxx 辅助族 + ResultCalculator 调用方
> 本报告所有"反编译常数"均出自 a1m2_cpapp.c; 所有"二进制表"均直接从 copro/cpapp-b.bin dump 验证。
> 日志宏: FUN_002bf488(level, ?, 行号, 源文件串, 格式串, ...); 断言: FUN_00282508(文件, 行号, 函数名)。

---

## 0. 结论速览 (TL;DR)

- `InclusionChecker::judgmentInclusion` (FUN_00302b40) 按**主体类别**分发到 4 个部位判定函数:
  - 类别 1,2 → FUN_00302d90 (人/动物/鸟通用, 内部按 **XHD 子类 [0x5a]** 分 5 组: Eye/Head1/Head2/Body1/Body2)
  - 类别 3,4,5,8 → FUN_00302e08 judgmentInsectAndAirplane
  - 类别 6 → FUN_00302eb8 judgmentTrain
  - 类别 7 → FUN_00302fe4 judgmentCar
- **每类主体优先对焦哪个部位 = 一张静态字节表** (0xFF 结尾), 已全部 dump(§8):
  - Eye(子类0): `[1, 2, 4]`(+末尾 4→补判 3)
  - Head1(子类1): XED 扫描 + XHD `[2, 4]`(+4→补判 3)
  - Head2(子类2): XHD `1` → XED 扫描 → XHD `4`(+4→补判 3)
  - Body1(子类3): XHD `[4, 2, 1]`(4 失败即整体放弃) + XED 扫描
  - Body2(子类4): XHD `3` → XHD `[2, 1]` + XED 扫描
  - Insect/Airplane(3/4/5/8): 子类3→部位1, 其它→部位3 (单部位)
  - Train(6): 子类1→`[2,3]`, 子类2→`[3,1]`(无 ChangeBaseFrame), 子类3→`[0,2,1]`
  - Car(7): 子类1→`[3,2]`, 子类2→`[3,1]`, 子类3→`[1,2]`(无 ChangeBaseFrame; 部位3 全失败则截断)
- 候选帧接受判据 = **IoMin ≥ 运行时阈值**(vtable+0x13c) + **锚点包含检查**(FUN_00894a8a) + 得分/距离平局裁决; 无任何硬编码阈值常数——阈值全部来自运行时配置接口。
- best(=Prio result)维护: 每部位一份 XhdResult 拷贝(checker+0xE8+P*0x148), `updateBestResult`(FUN_003049e8) 每帧落地, `disableBestResult`(FUN_00304914) 失效; 最终输出 DROP[5]/INDEX[5] 交给 ResultCalculator/DebugDraw。

---

## 1. 调用链与对象全景

```
ResultCalculator (rc, process/post/result_calculator.cpp, FUN_00307d5c)
 ├─ rc+0x894  KeypointPriorityResult (kp_result):
 │             +0x00 类型(0=无,1=XED,2=XHD)  +0x04 数据对象指针  +0x08..0x0C req[5]  +0x0D 附加flag
 ├─ rc+0x98   XED 快照: +0x00 有效flag; +0x08 XED 行表(stride 0xC8); +0x3F0 行数
 │             (由 FUN_00307348 → FUN_00896ba2/FUN_00896bda 从历史环 rc+0x14→+0x988/+0x98C 生成)
 ├─ rc+0x888  帧上下文: +0x04 = XHD 帧表基址(行 stride 0x148, 行首字节=行有效flag)
 ├─ rc+0x998  InclusionChecker (this, 下称 chk)
 └─ 每帧: FUN_00302b40(chk, kp_result, xed_snapshot, frame_ctx)   // judgmentInclusion
          FUN_003049e8(chk, kp_result, xed_snapshot, frame_ctx)   // updateBestResult
```

- XED = 高置信跟踪结果 (XedResult, **stride/大小 0xC8**), 类别在 `[0xA9]`
- XHD = 次级结果 (XhdResult, **stride/大小 0x148**), 类别 `[0x59]`, 子类 `[0x5A]`, 优先帧下标 `[0x140]`(int8, -1 无)
- XHD 帧表每行即一个 XhdResult; XED 快照行即一个 XedResult。
- 断言串佐证: `../../FC/keypoint/param/internal/animal_data.h` (0x10517da)、
  `const Frame &Camera::FC::Keypoint::KeypointXhdResult::getPrioFrame() const` (0x1051855, 即 [0x140] 越界断言)。

### 1.1 InclusionChecker (chk) 字段(已验证的绝对地址)

| 偏移 | 含义 | 证据 |
|---|---|---|
| +0x10..0x14 | cur_idx[5]: 部位P当前 XHD 行下标 (0xFF=无) | FUN_00303120 `*(u8*)(P+chk+0x10)` |
| +0x15 | XED 选中的行下标 (0xFF=无), 亦是 part0 的 XED 结果 | FUN_003047b0/FUN_003035f0 |
| +0x16,0x17,0x18 | 状态标志: +0x17="XHD is verifying", +0x18="无 XED 结果" | FUN_00302d90/FUN_003041f8 |
| +0x758+P | flagA[P]: 本帧"CURRENT 已更新" | FUN_00303120 写 1 |
| +0x75D+P | flagB[P]: "该部位 BEST 可用" (init 1) | FUN_00302b40 init / 失败清 0 |
| +0x762 | 本帧 XED 数据可用 (bool) | FUN_00302b40 |
| +0x20 | chk 内 XED 结果拷贝槽 (0xC8 字节, = part0 的 XED best) | FUN_008954b0/FUN_00895694 |
| +0xE8+P*0x148 | 部位 P 的 XhdResult 拷贝 ("best XHD", 布局与 XHD 行完全一致) | FUN_0089555e / FUN_008951a0 |
| → 拷贝内 +0x00 | 存储行的首字(=有效性, FUN_008948cc 第3参) | FUN_008948cc(iVar7+200) |
| → 拷贝内 +0x7C+i*0x18 | 存储的子帧 Rect{vptr,x,y,w,h} | FUN_00304fd0 词偏移 0x5A |
| → 拷贝内 +0x140 | int8 存储的选中子帧下标 (绝对 = chk+0x228+P*0x148) | FUN_00303120/008951a0 |

### 1.2 XhdResult / XedResult 内部布局(两表已对齐验证)

| 偏移(XHD) | 含义 | 证据 |
|---|---|---|
| +0x00 | u32 行标志/word0 (XED 行=有效flag) | FUN_0030378c 行过滤, FUN_002f1cc8 |
| +0x08..0x25 | Frame 头对象 0x1E 字节(FUN_0083db36 拷贝单位, FUN_008958ec 逐字段比较) | FUN_0089555e |
| +0x30,+0x32 | short 中心x,y(由选中子帧回填) | FUN_00303120 回写 |
| +0x34,+0x36 | short cx,cy; +0x38,+0x3A ushort w,h (XED 行=主框) | FUN_0030378c/FUN_00894f3c |
| +0x4C,+0x4E | short 中心副本 | FUN_00303120 回写 |
| +0x59 / +0xA9 | 类别 (XHD/XED) | judgmentInclusion |
| +0x5A | 子类 | 各 judgment 函数 |
| +0x60,+0x64 / +0x74,+0x78 / +0x88,+0x8C | 锚点 P1/P2/P3 (float x,y) —— **XedResult 形状对象专用** | FUN_00894a8a |
| +0x70 | u8 子帧数 n | FUN_00303350 循环上界 |
| +0x78+i*0x18 | 子帧 i: +0x78 f32 score; +0x7C Rect{vptr,x,y,w,h}; +0x88 u8 附加flag | FUN_00303350/00894d4e |
| +0x140 | int8 优先帧(选中子帧)下标 | getPrioFrame 断言 |
| stride | XHD=0x148, XED=0xC8 | 帧表/快照 |

注: 锚点读取只发生在 **XedResult 形状**对象上(XED obj / XED 行 / chk+0x20 拷贝); XHD 行的 +0x78 起是子帧数组, 两者不冲突。

---

## 2. FUN_00302b40 — InclusionChecker::judgmentInclusion (总入口)

字符串: `InclusionChecker::judgmentInclusion() IN : type = %d` (0x302D0C)

```c
void judgmentInclusion(chk, kp_result, xed_snap, frame_ctx) {
  log("... IN : type = %d", kp_result[0]);
  chk->0x15 = 0xFF; chk->0x16 = chk->0x17 = chk->0x18 = 0;
  for P in 0..4 { chk->flagA[P](0x758+P) = 0; chk->flagB[P](0x75D+P) = 1; }

  if (kp_result->type == 0) { log("[WARNNING] KeypointPriorityResult unknown type"); return; }
  data = *(kp_result+4);
  if (type == 1) {                       // XED
      if (kp_result[0xD] != 0 && !best_frame_query(kp_result[0xD])) goto invalid;
      cls = data[0xA9];
  } else {                               // XHD (type==2)
      if (data == NULL || data[0x140] == -1) goto invalid;   // getPrioFrame 断言保护
      cls = data[0x59];
  }
  if (vtable_0x178(chk->obj8, cls) == 0) {   // 类别≠当前 AF 目标类别
      log("[WARNNING] Target mismutch (%d:%d)", vtable_0x44(chk->obj8) /*当前目标*/, cls);
      return;
  }
  switch (cls) {
    case 1: case 2:            judgment_1_2(chk, kp_result, xed_snap, frame_ctx); break;
    case 3: case 4: case 5: case 8:
                               judgmentInsectAndAirplane(chk, data, kp_result+8, frame_ctx); break;
    case 6:                    judgmentTrain(chk, data, kp_result+8, frame_ctx); break;
    case 7:                    judgmentCar(chk, data, kp_result+8, frame_ctx); break;
    default: log("[WARNNING] default case : target = %d", cls);
  }
  chk->0x16 = 1;   // 本帧执行过判定
  return;
invalid:
  log("[WARNNING] Xed or Xhd data is invaild (type:%d)", cls);
}
```
- 第3参在各 judgment 内被用作 **req[P] 字节数组**(注意: 类 3–8 传的是 `kp_result+8`, 类 1/2 内部同);req 语义见 §5.1。
- `vtable_0x178(obj, cls)`: "cls 是否为当前启用目标类别"; `vtable_0x44()`: 当前目标类别。两者为 chk+8 接口对象(chk 构造时由 FUN_0088e4b8 单例 0x143EBE8 注入)的虚表槽,实现不在反编译覆盖区(见 §11 不确定项)。

---

## 3. 类别 1/2 — FUN_00302d90 (Human/Animal/Bird 通用分发 → 5 个部位组)

FUN_00302d90 自身无入口日志;内部路径日志 = `judgmentAnimalBirdPrioPartEye()` (0x3041A4)。

```c
void judgment_1_2(chk, kp_result, xed_snap, frame_ctx) {
  if (kp_result->type == 1) goto EYE;            // XED 一律走 Eye 组
  switch (xhd->subclass /*[0x5A]*/) {
    case 0: goto EYE;
    case 1: judgmentAnimalBirdPrioPartHead1(); break;
    case 2: judgmentAnimalBirdPrioPartHead2(); break;
    case 3: judgmentAnimalBirdPrioPartBody1(); break;
    case 4: judgmentAnimalBirdPrioPartBody2(); break;
  }
  return;
EYE:
  if (judgmentCaclResultStatus(2) == 1) {        // 见 §6.6; 失败分支 ↓
      ... Eye 组流程 (§4.1) ...
  } else {
      log("--- XHD is verifying"); chk->0x17 = 1;
  }
}
```

### 4.1 Eye 组 (LAB_00304010, 部位表 DAT_003041dc = `01 02 04 FF`)

```c
  for (i = 0; ; i++) {                        // 依表序尝试 [1, 2, 4]
      if (i == 3) { log("--- no valid frame!!"); return; }
      part = DAT_003041dc[i];
      if (judgmentXEDAndXHD(chk, subj_data, &part, kp_req+part, frame_ctx) == 1) break;  // §5.2
  }
  base_rect = XHD行(cur_idx[part]) 选中子帧的 Rect;        // 以首个命中部位矩形为基准
  chosen = part;
  for (j = i+1; j < 3; j++) {                 // 剩余部位仍做 CURRENT/BEST 维护
      part2 = DAT_003041dc[j];
      judgmentFrameAndXHD(chk, &base_rect, &part2, kp_req+part2, frame_ctx);   // §5.1
      if (ChangeBaseFrame(chk, &part2, frame_ctx, &base_rect)) chosen = part2; // §6.5
  }
  if (chosen == 4) { part3 = 3; judgmentFrameAndXHD(chk, &base_rect, &part3, kp_req+3, frame_ctx); }
  destroy(base_rect);
```
语义: **部位优先序 = [1, 2, 4],首个在 CURRENT 中命中者胜出**;尾部部位仅作 best 维护;若最终基准落在部位 4,追加判定部位 3。

### 4.2 FUN_003041f8 — judgmentAnimalBirdPrioPartHead1 (子类1; 表 DAT_00304350 = `02 04 FF`)

```c
  entry = xhd + xhd->prio_idx*0x18;  base_rect = {entry+0x80..0x86};
  if (judgmentCaclResultStatus(1) == 1)  judgmentFrameAndXED(chk, &base_rect, &part=subclass, kp_req, xed_snap, frame_ctx); // XED 扫描先行
  else chk->0x18 = 1;                    // "无 XED 结果"
  for (i = 0; i < 2; i++) {              // XHD 部位 [2, 4]
      part = DAT_00304350[i];
      judgmentFrameAndXHD(chk, &base_rect, &part, kp_req+part, frame_ctx);
      if (ChangeBaseFrame(...)) chosen = part;
  }
  if (chosen == 4) { part3 = 3; judgmentFrameAndXHD(...); }
```

### 4.3 FUN_00304354 — judgmentAnimalBirdPrioPartHead2 (子类2)

```c
  base_rect = prio帧 Rect;
  part = 1;  judgmentFrameAndXHD(chk,&base,&part,kp_req+1,ctx);  if (ChangeBaseFrame) chosen=part;  // 先 XHD 部位1
  if (judgmentCaclResultStatus(1)) judgmentFrameAndXED(..., &chosen, ...); else chk->0x18 = 1;     // XED 扫描居中
  base_rect = prio帧 Rect (重取);
  part = 4;  judgmentFrameAndXHD(...);  if (ChangeBaseFrame) chosen = part;                        // 再 XHD 部位4
  if (chosen == 4) { part3 = 3; judgmentFrameAndXHD(...); }
```

### 4.4 FUN_003044f8 — judgmentAnimalBirdPrioPartBody1 (子类3; 表 DAT_0030464C = `04 02 01 FF`)

```c
  base_rect = prio帧 Rect;  chosen = subclass;
  for (i = 0; i < 3; i++) {              // [4, 2, 1]
      part = DAT_0030464C[i];
      judgmentFrameAndXHD(chk,&base,&part,kp_req+part,ctx);
      if (part == 4 && !chk->flagA[4] && !chk->flagB[4]) goto END;   // 部位4 当前/BEST 全失败 → 整组放弃
      if (ChangeBaseFrame(...)) chosen = part;
  }
  if (judgmentCaclResultStatus(1)) judgmentFrameAndXED(..., &chosen, ...); else chk->0x18 = 1;
END: destroy(base_rect);
```

### 4.5 FUN_00304650 — judgmentAnimalBirdPrioPartBody2 (子类4; 表 0x3047AC = `02 01 FF`)

```c
  base_rect = prio帧 Rect;  chosen = subclass;
  part = 3; judgmentFrameAndXHD(chk,&base,&part,kp_req+3,ctx);            // 先部位3
  for (两拍, 部位取自 0x3047AC: 2, 1) {
      judgmentFrameAndXHD(...); if (ChangeBaseFrame) chosen = part;
  }
  if (judgmentCaclResultStatus(1)) judgmentFrameAndXED(...); else chk->0x18 = 1;
```

---

## 5. 类别 3–8 — 单表/单部位判定

### 5.1 FUN_00302e08 — judgmentInsectAndAirplane (类 3/4/5/8)

字符串: `judgmentInsectAndAirplane() prio_part %d` (0x302E8C)
```c
  part = (xhd->subclass == 3) ? 1 : 3;
  entry = xhd + xhd->prio_idx*0x18;                    // getPrioFrame 断言
  judgmentFrameAndXHD(chk, &entry_rect(+0x7C), &part, kp_req+part, frame_ctx);   // 单部位, 无回退/无XED扫描
```

### 5.2 FUN_00302eb8 — judgmentTrain (类 6)

字符串: `judgmentTrain() prio_part %d` (0x302FB8);二进制表:

| 子类 | 表地址 | 内容 (dump) | ChangeBaseFrame? |
|---|---|---|---|
| 1 | 0x302FD8 | `02 03 FF` | 是 |
| 2 | 0x302FE0 | `03 01 FF` | **否** |
| 3 | 0x302FDC | `00 02 01 FF` | 是 |
| 其它 | — | 直接 return | — |

```c
  entry = xhd + prio_idx*0x18;  base = prio帧Rect;
  for (part in 表, 直到 0xFF) {
      judgmentFrameAndXHD(chk,&base,&part,kp_req+part,ctx);
      if (do_change) ChangeBaseFrame(chk,&part,ctx,&base);
  }
```

### 5.3 FUN_00302fe4 — judgmentCar (类 7)

字符串: `judgmentCar() prio_part %d` (0x3030F8);二进制表:

| 子类 | 表地址 | 内容 (dump) | ChangeBaseFrame? |
|---|---|---|---|
| 1 | 0x303114 | `03 02 FF` | 是 |
| 2 | 0x30311C | `03 01 FF` | 是 |
| 3 | 0x303118 | `01 02 FF` | **否** |
| 其它 | — | 直接 return | — |

Car 特有截断: 每次判完若 `part==3 且 !flagA[3] 且 !flagB[3]` → break(部位3彻底失败即停, 不再继续表尾)。

---

## 6. 判定原语(所有部位共用的机器)

### 6.1 req[P] 申请字节 (kp_result+8+P)

`FUN_00303120/FUN_00303a98` 入口 `(byte)(req-1) < 2` → bit0=CURRENT; `(req|2)==2` (即 2/3) → bit1=BEST。
**req=1 只更新 CURRENT;2 只更新/校验 BEST;3 两者;0 跳过该部位。**
(申请数组由 ResultCalculator 生成;ResultManager 状态换算见 FUN_00897F94: `state==2 || valid==3`。)

### 6.2 FUN_00303120 — judgmentFrameAndXHD (XHD 单部位判定)

字符串: `judgmentFrameAndXHD() : check_part:%d, apply_type:%d` (0x303310), `-CURRENT-`/`-BEST-`/` change array_index %d`
```c
  best_score = FLT_MAX(0x7F7FFFFF); base_valid = 0;
  FUN_00894C74(chk, part, &base_valid, &best_score);   // 从 chk/ResultManager 取基准 → 有效则 best_score=0
  if (req & 1) {                                        // ---- CURRENT ----
      log("-CURRENT-");
      row = xhd表[cur_idx[part]]  (cur_idx != 0xFF);
      if (vtable_0x178(chk->obj8, row->cls[0x59]) == 1) {       // 行类别 == 当前目标
          idx = select_XHD_row_entry(chk, ref_rect, part, row, &best_score, &best_IoMin, base_valid);  // FUN_00303350
          if (idx != 0xFF && idx < row->count[0x70]) {
              log(" change array_index %d", idx);
              row->prio_idx[0x140] = idx;                       // 选中该子帧
              row->0x30/32 = 子帧中心; row->0x34..0x3A = 子帧Rect; row->0x4C/4E = 中心副本;
              chk->flagA[part] = 1;
          }
      }
  }
  if ((req|2) == 2) {                                   // ---- BEST ----
      log("-BEST-");
      entry = chk最佳拷贝行(chk + part*0x148 + 0xE8 首字有效?);
      if (entry有效 && entry->prio_idx != -1)
          FUN_00894D4E(chk, ref_rect, part, &best_score, &best_IoMin, base_valid);   // §6.4
      else chk->flagB[part] = 0;
  }
  else-if 无 CURRENT 分支执行 → chk->flagB[part] = 0;      // (req 不含 2 时也会清 flagB——见反编译尾行)
```

### 6.3 FUN_00303350 — XHD 行内子帧选择器 (CURRENT 用)

```c
  if (row->count[0x70] == 0) return;
  for (j = 0; j < count; j++) {
      e   = row + j*0x18;                 // score@+0x78, Rect@+0x7C
      iom = IoMin(ref_rect, e.rect);      // FUN_002ce598
      if (iom < vtable_0x13c()) continue;         // ← IoMin 阈值(运行时)
      if (!base_valid) {                  // 无基准: 最大化 IoMin, 平局取 score 小者
          if (iom > best_IoMin || (iom == best_IoMin && e.score < best_score))
              { *out = j; best_IoMin = iom; best_score = e.score; }
      } else {                            // 有基准: 最小化 e.score, 平局取距参考点近者
          d = dist2(e.rect中心, 参考点);           // FUN_00894F3C, 初值 FLT_MAX
          if (e.score < best_score || (e.score == best_score && d < best_d))
              { *out = j; best_score = e.score; best_d = d; }
      }
  }
```
FUN_00303CE0 (judgmentXEDAndXHD 的 CURRENT 选择器) = 同上 + 每候选先过 **锚点包含检查** `FUN_00894A8A(entry, subj_data, part, e.rect) == 1`。
FUN_0030378C (judgmentFrameAndXED 的 XED 行选择器) = 扫描 XED 快照行(行首 flag→类别[0xA9]→锚点检查), 有基准时以 **IoU(基准Rect, 行Rect)** 最大化、平局取距离;无基准时以 IoMin(主体Rect, 行Rect) 最大化、平局取 `recalcScore(DIST)`。

### 6.4 FUN_00894D4E / FUN_00895070 / FUN_008951A0 — BEST 校验/回写

字符串(共): ` change current result INVALID` (0x105173D)
```c
  // FUN_00894D4E (judgmentFrameAndXHD 的 BEST 路径; chk 拷贝行 = chk + part*0x148, 词偏移 0x8A→字节 0x228)
  stored_rect = 拷贝行选中子帧 Rect;
  if (IoMin(stored_rect, ref_rect) < 阈值) { chk->flagB[part] = 0; return; }   // 基准漂移过大 → best 失效
  if (base_valid/*verifying*/) return;
  if (IoMin > best_IoMin || (== && recalcScore 更优))  → OK(保持)
  else { log(" change current result INVALID"); chk->flagA[part] = 0; }
  // FUN_00895070: 同型, 用于 judgmentFrameAndXED 的 part0(XED): 锚点检查失败 → flagB[0]=0;
  //               失败时 *out=0xFF 且 chk+0x1D6 清 0。
  // FUN_008951A0: 同型, 用于 judgmentXEDAndXHD 的 BEST 路径(拷贝行 = chk+0x20+P*0x148);
  //               锚点检查(FUN_00894A8A, 锚点取 XED obj)失败 → flagB[part]=0。
```

### 6.5 FUN_00303EE0 — ChangeBaseFrame (BEST/XHD)

字符串: `ChangeBaseFrame BEST:(%d)` (0x303FD8) / `ChangeBaseFrame XHD:(%d)` (0x303FF4)
```c
  P = *part;
  if (chk->flagA[P] == 1)        { log("ChangeBaseFrame XHD:(%d)");  rect = XHD行(cur_idx[P])选中子帧 Rect; }
  else if (chk->flagB[P] == 1)   { log("ChangeBaseFrame BEST:(%d)"); rect = chk最佳拷贝行(P)选中子帧 Rect; }
  else return 0;
  *out_rect = rect;  return 1;     // 供下一部位/下一帧的 IoMin/IoU 基准
```

### 6.6 FUN_00895428 — judgmentCaclResultStatus (XED/XHD 计算状态闸门)

字符串: `judgmentCaclResultStatus data_type = %d, xed_status = %d, xhd_status = %d` (0x1051790)
```c
  xed_status = *(ctx + 0x10BC);  xhd_status = *(ctx + 0x10D8);      // ctx = FUN_00891A98(0) = 0x14802F8
  data_type==2 → return (xhd_status == 5 || xed_status != 5);       // 放行 XHD 判定
  data_type==1 → return (xed_status == 5 || xhd_status != 5);       // 放行 XED 扫描
  其它 → true
```
即 **status==5 = "该路计算已完成/有结果"**;XHD 未完成且 XED 已完成 → 拒绝 XHD 判定("XHD is verifying");XED 未完成且 XHD 已完成 → 跳过 XED 扫描(chk+0x18=1)。

### 6.7 FUN_00894A8A — 锚点包含检查 (类名 InclusionChecker 的由来)

```c
bool anchor_incl(subj /*XedResult形状*/, part, rect /*x@+4,y@+6,w@+8,h@+10*/) {
  if (subj == NULL || *subj == 0) return false;
  m = rect.w * vtable_0x16c() * 0.5;                  // 边扩 = 宽度×比例×½ (比例=运行时)
  inP1 = (subj->ax1 ∈ [x-m, x+w+m]) && (subj->ay1 ∈ [y-m, y+h+m]);   // P1 = (+0x60,+0x64)
  inP2 = (subj->ax2 ∈ ...) && (subj->ay2 ∈ ...);                     // P2 = (+0x74,+0x78)
  if (part == 1) return inP1 || inP2;                 // 部位1(头部系)宽松
  return (subj->ax3 ∈ ...) && (subj->ay3 ∈ ...);      // 其余部位: 必须含 P3 (+0x88,+0x8C)
}
```
锚点即该类主体的"头/躯干关键点";部位 1 判头(命中任一头锚点即可), 其它部位必须罩住躯干锚点 P3。

### 6.8 度量函数

- **FUN_002CE598 = IoMin** = 交集面积 / min(面积A, 面积B), 截断 [0,1] (负/越界→0.0;DAT_002CE724=0.0)。
- **FUN_002CE40C = IoU** = 交集 / (A+B−交集), 截断 [0,1] (DAT_002CE594=0.0)。
- **FUN_003034F4 = recalcScore** (字符串 `recalcScore() IOU` / `recalcScore() DIST` / `return IOU %8.4f`):
  - flag==0 → **DIST**: FUN_00894F3C = 候选 Rect 中心到参考点(接口对象给出, 含 FUN_002CE728 归一化/取整与 FUN_008958A0 条件修正)的**距离平方**;
  - flag!=0 → **IOU**: FUN_00304FD0 = IoU(基准 Rect, 候选)。part==0 基准取 ResultManager 主框(FUN_008948CC(0,...));part>0 取 chk 拷贝行选中子帧。
- 平局裁决方向: DIST 越小越好 / IOU 越大越好(FUN_0030378C 内 `flag==0 → 新分<旧分才换, flag!=0 → 新分>旧分才换`)。

### 6.9 FUN_00894C74 / FUN_008948CC — 基准与 BEST 有效性

```c
FUN_00894C74(chk, part, &valid, &score):
  score = FLT_MAX; valid = 0;
  if (chk->0x762 /*XED 可用*/) {
      if (part == 0) valid = FUN_008948CC(chk, &0, 0);
      else           valid = FUN_008948CC(RM行(chk_copies+part*0x148), &part, 行[0xC8]);
      if (valid) score = 0;
  }
FUN_008948CC(row, part_ptr, entry0):
  expected = (part==0) ? RM->main_valid(ctx+0x00) : RM->part_valid(ctx+0x04+P*4);   // FUN_00891ABC/AE0
  if (part>0 && expected==0) expected = RM->state(ctx+0x18+P*4);                    // FUN_00891B24
  return expected != 0;
```
ResultManager 状态(单例 ctx = FUN_008919FE()): `+0x00` 主 best 有效性(FUN_00891AAE 写, 值 0/3), `+0x04+P*4` 部位 best 有效性(FUN_00891AC8), `+0x18+P*4` 部位次级状态(FUN_00891B08, 值 2), `+0x30` chk XED 拷贝头(FUN_00891B62 经 FUN_00885F00+FUN_0083DB36 共 0x2A 字节)。

---

## 7. best 维护族 (XED Use Prio result / XHD Use XhdData / disable / update)

### 7.1 FUN_003047B0 — (XED) 取 Prio 结果指针
字符串: ` [XED] Use Prio_result` (0x1051763) / ` [XED] Use XadData` (0x304824, 固件原始拼写)
```c
  if (kp->type == 1) return kp->data;                       // 直接用 XED 结果
  if (chk->0x15 == 0xFF || !chk->flagA[0]) return 0;        // 无 XED 候选
  return XED快照 + chk->0x15*0xC8 + 8;                      // 用快照中选中的 XED 行
```

### 7.2 FUN_00304838 — (XHD, 按部位) 取结果指针
字符串: ` [XHD(%d)] Use Prio_result` (0x3048F8) / ` [XHD(%d)] Use XhdData` (0x3048E0)
```c
  if (kp->type == 2) {
      if (xhd->subclass == P)            return kp->data;                    // 子类即该部位 → 用 Prio 结果
      if (chk->cur_idx[P]==0xFF || !chk->flagA[P]) return 0;
  } else {
      if (chk->cur_idx[P]==0xFF || !chk->flagA[P]) return 0;
  }
  return XHD表 + chk->cur_idx[P]*0x148;                                      // 否则用 XhdData(当前帧行)
```

### 7.3 FUN_00304914 — disableBestResult
字符串: `--- disableBestResult() IN : part_type %d` (0x3049BC)
```c
  if (P == 0) { 行清 0(chk+0x20 与 +0x730);  if (no_notify && !chk->0x18) { RM_set_main(0); RM_set_state0(0); } }
  else if (P < 5) { 拷贝行(P)[0xC8] = 0;  if (no_notify && !chk->0x17) { RM_set_part(P, 0); RM_set_state(P, 0); } }
```

### 7.4 FUN_003049E8 — updateBestResult (落盘 + DROP/INDEX 产出)
字符串: `InclusionChecker::updateBestResult() IN` (0x304F54), `+++PRIO CURRENT+++` (0x304F7C),
`DROP  : %3d, %3d, %3d, %3d, %3d` (0x304F90), `INDEX : %3d, %3d, %3d, %3d, %3d` (0x304FB0), ` no update BestResult` (0x105177A)

```c
  RM_prof_begin();
  if (kp->type == 0) {                                   // 本帧无结果 → 全清
      RM_publish(chk); RM_set_main(0); RM_set_part(1..4, 0); RM_set_state0(0); RM_set_state(1..4, 0); return;
  }
  if (!chk->0x16) {                                      // 本帧没跑过 judgmentInclusion
      log(" no update BestResult");
      for P in 0..4: if (!(RM_valid(P) || RM_state(P)) || 存储行 prio_idx == -1) { RM_set_part(P,0); RM_set_state(P,0); }
      return;
  }
  if (kp->type == 1) {                                   // ---- XED 帧 ----
      FUN_008954B0(chk, chk+0x20, xed_obj);              // XED 结果 → chk XED 槽(+0x20) (0x14+0x1E 字节)
      for P in 1..4 {
          p = FUN_00304838(chk, kp, xed_snap, P);
          if (!p) { if (!chk->flagB[P]) disableBestResult(chk, chk+0x20, P, 0); }
          else if (chk->cur_idx[P] < 5) FUN_0089555E(chk, chk+0x20, p, P);   // XHD 当前行 → 部位P 拷贝行
      }
  } else {                                               // ---- XHD 帧 ----
      p0 = FUN_003047B0(chk, kp, xed_snap);
      if (!p0) { if (!chk->flagB[0]) disableBestResult(chk, chk+0x20, 0, 0); } else FUN_008954B0(...);
      subj_rect = XHD prio帧 Rect;
      for P in 1..4 { 同上 XED 分支的 per-P 维护; }
  }
  // ---- DROP[0]/INDEX[0] (part0 = XED/脸) ----
  if ((type==1 && !FUN_00895694(chk+0x20, xed_obj))      // 存储的 XED best ≠ 本帧 XED → 失效
      || req[0]==0 || xed_snap->count==0 || chk->flagA[0]!=0)   DROP[0]=0, INDEX[0]=0xFF;
  else { DROP[0]=1; INDEX[0]=chk->0x15; }
  if (chk->0x763) DROP[0]=0;
  // ---- DROP[1..4]/INDEX[1..4] (XHD 部位) ----
  sub = (type==2) ? xhd->subclass : 0xFF;
  for i in 0..3  (P = i+1):
      if (P == sub && !FUN_008957A2(拷贝行(sub), xhd_obj)) {            // 存储行≠当前 XHD 对象
          log("+++PRIO CURRENT+++"); DROP[P]=0; INDEX[P]=0xFF;
      } else if (chk->cur_idx[P] > 4 || chk->flagA[P]) { DROP[P]=0; INDEX[P]=0xFF; }
        else { DROP[P]=1; INDEX[P] = XHD行(cur_idx[P])->prio_idx[0x140]; }
  if (kp[0xD]==0 && sub!=0xFF) DROP[sub]=0;
  FUN_002F1CC8(FUN_0088684E() /*DebugDrawIf*/, DROP, INDEX, xed_snap, frame_ctx);  // setDropInfo(调试/叠加层)
  log(DROP...); log(INDEX...);
  for P: if (DROP[P]) RM_prof_mark(2);
  if (!chk->0x20[0] && !chk->0x18) RM_set_main(0);
  for P in 1..4: if (!存储行有效(P) && !chk->0x17) RM_set_part(P, 0);
  FUN_00895810(chk, frame_ctx);          // XHD verifying 时按需重拷当前行→拷贝行, 行[0xC0]=verifying, 行[0x120]清
  RM_publish(chk);                        // FUN_00891B62 → ResultManager
```
配套比较器:
- FUN_00895694(存储 XED 槽, 新 XED obj): 逐字段比 (+4, +8 Float, FUN_008958EC 0x1E 字节头, 锚点 +0x60/64/74/78/88/8C, +0x94/98/9C Float, +0xA0 char, +0xA4 int, **+0xA9 类别**, +0xAA)。
- FUN_008957A2(存储 XHD 行, 新 XHD obj): 比 (+4, 头 0x1E 字节, +0x50, +0x54, **+0x59 类别, +0x5A 子类**, +0x70 子帧数, +0x140 prio idx)。
- FUN_008954B0(chk, chk+0x20, XED obj) = 拷 0xC 字节 + FUN_0083DB36(0x1E 字节) — XED 结果头快照。
- FUN_0089555E(chk, chk+0x20, XHD行, P): 拷贝行(P) = chk+0x20+P*0x148;行+0xC8 ← 源行[0x00..0x07], 行+0xCC ← 源[0x08..0x0B], FUN_0083DB36(行+0xD0, 源+0x08) (0x1E 字节) —— 即把 XHD 行头部 0x26 字节写进拷贝行 +0xC8 起 (= 绝对 chk+0xE8+P*0x148)。

### 7.5 FUN_002F1CC8 — DebugDrawIf::setDropInfo (仅显示层)
字符串域: `common/debug/debug_draw_if.cpp`, `setDropInfo(Aed:%d, is_valid:%d)` (0x2F229C)
- part0: 扫 XED 快照行, 取 score(row+8) 最大且 ≥ DAT_002F1F60 的行 → 输出框(chk_dbg+0x5D0)。
- part1..4: DROP[i] 且 INDEX≠0xFF → 拷贝 XHD 行;按 `row[0x58]>>16 & 0xFF`: 值 2 → 输出到槽 +0x5A8;值 3/4 → 槽 +0x5BC;其它不输出。

---

## 8. 静态表 dump(二进制直接读取, 文件偏移 = VA−0x108000)

| VA | 字节 | 用途 |
|---|---|---|
| **0x3041DC** | `01 02 04 FF` | Animal/Bird Eye 组部位序 |
| 0x304350 | `02 04 FF` | Head1 组部位序 |
| 0x30464C | `04 02 01 FF` | Body1 组部位序 |
| 0x3047AC | `02 01 FF` | Body2 组部位序 |
| 0x302FD8 | `02 03 FF` | Train 子类1 |
| 0x302FDC | `00 02 01 FF` | Train 子类3 |
| 0x302FE0 | `03 01 FF` | Train 子类2 |
| 0x303114 | `03 02 FF` | Car 子类1 |
| 0x303118 | `01 02 FF` | Car 子类3 |
| 0x30311C | `03 01 FF` | Car 子类2 |
| 0x302410 | `02 00 00 00 │ 01 00 00 00 │ 00 00 00 00 │ 01 00 00 00 │ 00 00 00 00 │ 02 00 00 00` | estimate_region 可靠性(0–5)→档位映射 (FUN_003023DC: rel0→2, 1→1, 2→0, 3→1, 4→0, 5→2) |
| DAT_003034F0 / 00303A94 / 00303EDC | `0xFFFF7F7F` = **FLT_MAX** | 距离平局裁决初值 (三处选择器) |
| DAT_002F1F60 | (运行时) | setDropInfo XED score 阈值 |
| DAT_00302B3C / 002CE594 / 002CE724 | 0.0f | IoMin/IoU 退化值 / FUN_0030267C 常数 |

浮点阈值 **不在** flash 静态数据中: IoMin 接受阈值(vtable+0x13C)、锚点边扩比例(vtable+0x16C)为运行时配置 getter(实现位于未反编译区 0x8DCxxx/0x8E4xxx, 读 RAM 配置块 0x1F1DEE8+…, 见 §11)。

---

## 9. 完整决策树 (主体类别 → 子类 → 部位优先级 → best 维护)

```
judgmentInclusion(chk, kp, xed_snap, ctx)
│ kp.type==0 → 警告退出; XHD 无效([0x140]==-1) → 警告退出
│ 类别 ≠ 当前目标类别(vtable+0x178) → "Target mismutch" 退出
├─ cls 1/2 (人/动物/鸟, animal_data.h)
│   ├─ XED 帧 或 子类0 → [XHD 计算未完(XHD≠5 且 XED==5)? → "XHD is verifying", chk.0x17=1, 退出]
│   │     部位序 [1, 2, 4]: 逐个 judgmentXEDAndXHD (锚点检查+IoMin阈值+score/距离裁决)
│   │       首个 CURRENT 命中者 → 基准 Rect; 余下部位仅维护 BEST; 终选==4 → 补判 3
│   ├─ 子类1 Head1: [XED闸门(1): XED==5||XHD≠5 → judgmentFrameAndXED(部位=子类)] → XHD [2,4] → 终选4→补3
│   ├─ 子类2 Head2: XHD 1 → [XED闸门] → XHD 4 → 终选4→补3
│   ├─ 子类3 Body1: XHD [4,2,1], 部位4 当前/BEST 全失败 → 整组终止 → [XED闸门]
│   └─ 子类4 Body2: XHD 3 → XHD [2,1] → [XED闸门]
│   每个部位 P (req[P]≠0):
│     CURRENT: 行类别==目标 → 子帧选择{锚点检查(仅XEDAndXHD路径) → IoMin≥阈值(vt+0x13C)
│               → 无基准: IoMin↑, 平局 score↑小; 有基准: score↓小, 平局 距离↑小}
│               → 命中: 行.prio_idx=idx, 行中心/Rect 回填, flagA[P]=1
│     BEST:    拷贝行有效? → IoMin(存储Rect, 基准)≥阈值? → 是: 保持/平局裁决; 否: flagB[P]=0
│     ChangeBaseFrame: flagA→XHD 当前 Rect; elif flagB→拷贝行 Rect; 供下轮基准
├─ cls 3/4/5/8 (insect/airplane): 子类3→部位1, 其它→部位3 (单部位 judgmentFrameAndXHD)
├─ cls 6 (train): 子类1→[2,3](+CBF), 子类2→[3,1](无CBF), 子类3→[0,2,1](+CBF)
├─ cls 7 (car): 子类1→[3,2](+CBF), 子类2→[3,1](+CBF), 子类3→[1,2](无CBF; 部位3全失败→截断)
└─ updateBestResult (每帧):
    type==0 → 全清; 未判定 → 只做失效清理
    XED 帧: 存 XED→chk+0x20; 部位1..4: FUN_00304838 取数 → 无&flagB==0 → disable; 有&cur_idx<5 → 拷当前行
    XHD 帧: part0 走 FUN_003047B0(XED Prio/XadData); 部位1..4 同上
    DROP[0]/INDEX[0]: XED 槽与帧对象不一致 || req0==0 || 无XED行 || flagA[0] → 0/0xFF; 否则 1/chk.0x15
    DROP[P]/INDEX[P]: 子类部位存储行≠当前对象("+++PRIO CURRENT+++") || cur_idx>4 || flagA → 0/0xFF
                      否则 1 / 当前行的 prio_idx
    → DebugDrawIf::setDropInfo + ResultManager 发布(FUN_00891B62)
```

---

## 10. 字符串佐证清单(全部 0x30xxxx 区 + 相关)

| VA | 字符串 |
|---|---|
| 0x1051698 | `process/post/inclusion_checker.cpp` (日志源文件) |
| 0x302D0C | `InclusionChecker::judgmentInclusion() IN : type = %d` |
| 0x10516BB | ` [WARNNING] KeypointPriorityResult unknown type` |
| 0x10516EB | ` [WARNNING] Xed or Xhd data is invaild (type:%d)` |
| 0x302D44 | ` [WARNNING] Target mismutch (%d:%d)` |
| 0x302D68 | ` [WARNNING] default case : target = %d` |
| 0x302E8C | `judgmentInsectAndAirplane() prio_part %d` |
| 0x302FB8 | `judgmentTrain() prio_part %d` |
| 0x3030F8 | `judgmentCar() prio_part %d` |
| 0x303310 / 0x303754 / 0x303CAC | `judgmentFrameAndXHD() : check_part:%d, apply_type:%d` / `judgmentFrameAndXED() : …` / `judgmentXEDAndXHD() : …` |
| 0x105171C / 0x105175C | `-CURRENT-` / `-BEST-` |
| 0x1051726 | ` change array_index %d` |
| 0x105173D | ` change current result INVALID` |
| 0x3035B4 / 0x3035C8 / 0x3035DC | `recalcScore() IOU` / `recalcScore() DIST` / `return IOU %8.4f` |
| 0x303FD8 / 0x303FF4 | `ChangeBaseFrame BEST:(%d)` / `ChangeBaseFrame XHD:(%d)` |
| 0x3041A4 / 0x3041C4 / 0x3041E0 | `judgmentAnimalBirdPrioPartEye()` / `--- XHD is verifying` / `--- no valid frame!!` |
| 0x30432C / 0x3044D4 / 0x304628 / 0x304788 | `judgmentAnimalBirdPrioPartHead1()` / `…Head2()` / `…Body1()` / `…Body2()` |
| 0x1051790 | `judgmentCaclResultStatus data_type = %d, xed_status = %d, xhd_status = %d` |
| 0x1051763 / 0x304824 | ` [XED] Use Prio_result` / ` [XED] Use XadData` |
| 0x3048F8 / 0x3048E0 | ` [XHD(%d)] Use Prio_result` / ` [XHD(%d)] Use XhdData` |
| 0x3049BC | `--- disableBestResult() IN : part_type %d` |
| 0x304F54 / 0x105177A | `InclusionChecker::updateBestResult() IN` / ` no update BestResult` |
| 0x304F7C | `+++PRIO CURRENT+++` |
| 0x304F90 / 0x304FB0 | `DROP  : %3d, %3d, %3d, %3d, %3d` / `INDEX : %3d, %3d, %3d, %3d, %3d` |
| 0x10517DA / 0x1051855 | `../../FC/keypoint/param/internal/animal_data.h` / `const Frame &Camera::FC::Keypoint::KeypointXhdResult::getPrioFrame() const` |
| 0x10518A0 / 0x1051809 | 同族断言 `const bool …` / `const f32_t …` (子帧附加flag/score 访问) |
| 0x105177A 侧 | (assert 源) `process/post/result_calculator.cpp` 于 0x1051DD1 |

任务8(漏网检索)结论: `s_judgment*` 全集共 12 条(§上表已全覆盖),无遗漏的 PrioPart 判定函数。
另注: `src/priority_defocus_subject_selector.cpp`(0x1048B2C, DefocusFace replacePriorityFace/judgePriorityFaceIn, a1m2_cpapp.c 行 190913 起)属于**景虚化优先主体**子系统,与对焦部位判定无关,未展开。

---

## 11. 不确定项(不臆测,如实列出)

1. **IoMin 接受阈值与锚点边扩比例的具体数值**:由 chk+8 接口对象虚表 +0x13C/+0x16C getter 提供。该对象(FUN_0088E4B8→0x143EBE8 / FUN_0088EE58→0x143ED98)与配置块 0x1F1DEE8 均在 RAM(超出 cpapp-b.bin 文件范围 0x1355108),getter 实现位于未反编译的 0x8DCxxx/0x8E4xxx 区(手工反汇编确认其从 0x1F1DEE8+0x1848/0x1846/0x2CEC 等偏移读配置)。候选大虚表 0xE2A210/0xE2B0F8 的对应槽经验证是"读配置块"型 getter,但未能确认虚表与单例的绑定(构造器对 0x143EBE8 的写入在反编译文本中不可见)。
2. **vtable+0x178(类别匹配)与 +0x44(当前目标类别)的实现**:语义由调用点用法反推("Target mismutch" 日志两参数 = 当前目标 vs 主体类别),实现体同样在未覆盖区。
3. **XED/XHD 状态值的完整枚举**:仅确认 5 = "计算完成/有结果"(由失败分支日志语义反推);0–4/其它值含义未证。
4. **部位 ID 0–4 在各主体类别下的物理含义**(眼/头/躯干等):对类 1/2 由函数名(Eye/Head/Body)与 animal_data.h 断言强支持;对 train/car/insect 的 0–4 具体部位名取决于各类模型的关键点定义,固件内无字符串可证。
5. **chk 内 XHD 拷贝行的子帧数组写入方**:FUN_0089555E 只拷头部 0x26 字节;拷贝行 +0x7C 起子帧 Rect(chk+0x164+P*0x148+idx*0x18)被 FUN_00304FD0/FUN_008951A0 读取,其完整写入路径(可能在 result_manager.cpp / FUN_00891B62 上游)未逐行验证。
6. **FUN_0083DB36 拷贝长度**:反编译显示 0x1E 字节按字段拷贝;FUN_008954B0 场景下的总拷贝长度(0xC+0x1E)是否覆盖 XED 对象全部被比较字段(+0x60..0xAA)未验证——若不足,则 FUN_00895694 的部分比较项读取的是构造期缺省值。
7. **req[5] 的上游取值规则**:确认了位语义(1/2/3)与 ResultManager 状态的换算原型(FUN_00897F94),但 ResultCalculator 内把状态映射为 req 字节的最终赋值语句(可能位于 xedxhd/result_maker.cpp)未逐行追踪。
8. **Ghidra 参数错位风险**:FUN_00303350/FUN_0030378C/FUN_003035F0 的栈参数在反编译输出中存在寄存器/栈槽混淆(文中已按 FUN_00303CE0 的显式 8 参调用对齐还原);个别分支的比较方向已按"最大化 IoMin/IoU、最小化 DIST/score"复核,但 FUN_0030378C 无基准分支平局处的 `fVar13 >= fVar10` 细节仍可能有取反误差。
9. **chk+0x14/0x56(XED 基准中心/宽高)的写入方**(FUN_0030378C 读它们构造基准 Rect)——推断由 XED 命中路径(FUN_003035F0→FUN_00302074 构造)回写,未逐行确认。

---

## 12. 与既有笔记的关系

- 本文细化并部分修正 AF_LOGIC.md §四/§六: 类别 1/2 的内部子类分组(Eye/Head1/Head2/Body1/Body2 = XHD 子类 0–4)与各静态部位表为**新增确认**;`DAT_003041dc = [1,2,4]` 证实"3 部位迭代 + index 4 特殊处理"。
- REPORT_result_calc_frame_selector.md 中 `FUN_00302b40/FUN_003049e8(this+0x998, +0x894, +0x98, +0x888)` 的调用点, 本文给出四参的完整语义(kp_result / XED 快照 / 帧上下文)。
- 第3参 rc+0x98 **不是** "req 数组"而是 **XED 快照**(§1);req 数组在 kp_result+8 —— 修正早期猜测。
