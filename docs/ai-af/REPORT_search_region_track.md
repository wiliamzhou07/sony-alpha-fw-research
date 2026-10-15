# REPORT_search_region_track.md — α1 II AI 对焦：搜索参数 / 区域生成 / 深度搜索 / 跟踪状态机

分析对象：`a1m2_cpapp.c`(Ghidra 反编译，ARM32,基址 0x108000,对应 `copro/cpapp-b.bin`,平面映射 file_off = vaddr − 0x108000)。
子系统:`Camera::FC::Keypoint` 的 process/pre 层(resolver_search / xhd_search / generator / region_provider / search_controller / track)。
方法：逐函数反编译阅读 + 从固件二进制直接提取只读表(模式名表、part 优先级表、缩放级别表)+ 对 Ghidra 未生成函数的 10 个跟踪序列状态处理器用 capstone(Thumb)补充反汇编。所有字符串均以 `s_*_地址` 形式核实。

---

## 0. 总体架构一句话

`TrackSequencer`(10 状态机)驱动 → `TrackController/TkSet` 产生 Init/Train/Detect 请求与置信度裁决 → `SearchResolver`(resolver_search.cpp)按 **ModePattern(0-25)** 分配 5 个 part 搜索槽 → `ExecInfoCreator` 折算 ExecMode/Spec → `RegionProvider/SearchController` 产出 32 字节 `Region_Param` 数组 → generator 层按 SearchMode(0x00-0x17)的参数计算具体搜索区域(含 Z 纵深搜索与缩放级别表)。

---

## 1. 枚举与常数总表(证据：二进制数据表 + 断言串)

### 1.1 ModePattern(搜索模式，0-25)——表 `DAT_00d74cd0`(26 个字符串指针，文件偏移 0xC6CCD0)

| 值 | 名称 | 值 | 名称 |
|---|---|---|---|
| 0 | ALL | 13 | RELIABLE_ONLY_SHIFT_ALIGN |
| 1 | RELIABLE_SHIFT | 14 | RELIABLE_ONLY_XYZ_ALIGN |
| 2 | POTENTIAL | 15 | RELIABLE_ONLY_ALIGN |
| 3 | VERIFY | 16 | RELIABLE_ONLY_XYZ |
| 4 | VERIFY_FB | 17 | ALL_MARIO |
| 5 | RELIABLE | 18 | SLAVE_XYZ |
| 6 | ALL_ALIGN | 19 | SLAVE_XYZ_SPEED |
| 7 | RELIABLE_SHIFT_ALIGN | 20 | SLAVE_POTENTIAL |
| 8 | RELIABLE_XYZ_ALIGN | 21 | SLAVE_VERIFY |
| 9 | RELIABLE_ALIGN | 22 | SLAVE_VERIFY_FB |
| 10 | RELIABLE_XYZ | 23 | SLAVE_RELIABLE |
| 11 | RELIABLE_SECOND | 24 | SLAVE_RELIABLE_XYZ |
| 12 | RELIABLE_ONLY | 25 | SLAVE_RELIABLE_SECOND |

佐证:`FUN_0030f7a0/FUN_0030fa00` 用 `if (pattern < 0x1a) name = DAT_00d74cd0[pattern] else "unknown_pattern"`。
命名规律：**XYZ 后缀 = 启用 Z(纵深)搜索；ALIGN 后缀 = 需要对齐(中心锁定)变体；ONLY = 只搜可靠区(不带 potential 扩展区)；SLAVE_ 前缀 = 从(次级)实例专用**。≥18 的 5 个 SLAVE_* 与 "MARIO"(17,亦见 XHD_MARIO)是 UI/特殊路径。

### 1.2 XHD 模式(0-12)——表 `PTR_s_XHD_ALL_00d7a610`(9 个具名 + 4 个无名)

| 值 | 名称 | 值 | 名称 |
|---|---|---|---|
| 0 | XHD_ALL | 7 | XHD_MARIO |
| 1 | XHD_AF_ALIGN | 8 | XHD_TRACKING_ALIGN |
| 2 | XHD_RELIBLE_AF_ALIGN | 9 | (无名) |
| 3 | XHD_RELIABLE_MARIO | 10 | (无名) |
| 4 | XHD_RELIABLE_ALL | 11 | (无名) |
| 5 | XHD_RELIABLE_XY | 12 | (无名) |
| 6 | XHD_RELIABLE_ONLY | | |

佐证:`FUN_0030facc`:`if (uVar2 < 9) name = PTR_s_XHD_ALL[uVar2] else "unknown_xhd_pattern"`,但 `FUN_003104dc` 可产生 9-12(表项为 NULL,运行日志打 "unknown_xhd_pattern")。

### 1.3 SearchMode(0x00-0x17)与参数存储偏移(Settings 对象内)

来自 `FUN_0030dbd4`/`FUN_0030e360` 的 builder/executable switch 与各 getter 的断言串(`Camera::FC::Keypoint::Setting::SearchParams::getXxx(const SearchMode&)`):

| SearchMode | 参数类型(getter 名佐证) | Settings 内偏移 | builder 动作(FUN_0030dbd4) |
|---|---|---|---|
| 0x00, 0x17 | 非法 | — | assert(行 0x225/0x28a) |
| 0x01,0x0F,0x10,0x11 | 小参数(FUN_008a0c0e) | +0x10(+0x14 vector) | 存 1 字节到 mode+0x10 |
| 0x02 | (builder 侧 assert 0x1d0;getter 侧 getAllSearchParam 要求 ==2,FUN_00310bc8) | AllSearchParam:+0xa8 起 | assert |
| 0x03 | (builder assert 0x1d5) | — | assert |
| 0x04 | getXySearchParam(FUN_00311f40) | +0x16d0: u8,+0x16d8,+0x16e0[0x70] | FUN_0030d844→+0x16e0 |
| 0x05/06/07 | AlignSearchParam 族(FUN_008a10d0) | +0x16e0 同上 | FUN_008a10d0→+0x16e0 |
| 0x08 | getZSearchParam(XyzSearchParam,FUN_00311590) | +0x1750: u8,+0x1758,+0x1760[0x70] | FUN_0030d844→+0x1760 |
| 0x09/0x0B | FUN_008a0fa4:含 4×0x148 的槽结构 | +0x860(+0x868) | 存+循环构造 |
| 0x0A | getSecondSearchParam(FUN_00311614) | +0x110: u8,+0x118 box | FUN_008a0f14→+0x120 |
| 0x0C/0x0E | FUN_008a0fa4(同 9/0xB 家族，另一份) | +0xFA0(+0xFA8) | 存+循环构造 |
| 0x12-0x15 | getZVariableSearchParam(FUN_00311b9c,4 份) | +0x17d0/+0x1800/+0x1830/+0x1860 | FUN_0030d764/FUN_0030d570 |
| 0x14(特记) | **XhdTrackingAlignParam**(构造时打日志 `[XhdTrackingAlignParam]x=%d,y=%d`) | +0x1840 | 常数构造(见 §3.1) |
| 0x16 | getXhdXySearchParam(FUN_003119f4) | +0x1890: 2×u32,+0x1898[0x80],+0x1918 u8,+0x191c | FUN_0030d644→FUN_008a114e(+0x10) |

即 **SearchMode 是“用哪套搜索参数”的索引**，与 ModePattern(0-25,“搜索怎么走”)正交；由 `ExecInfoCreator`(§3.4)折算执行规格。

### 1.4 DetectionTarget / ExecIndex / ExecMode(FUN_0030e9b0 / 0030ea54 / 0030eaec)

- **DetectionTarget**:`FUN_0030e9b0(t)` — `t-1 < 6`(即 **1..6 合法**);`t==0` → 日志 `invalid target detection...%d`(行 0x2e)后 abort;其他 → `ERROR: unkown targer... %d`(行 0x43)abort。
- **ExecIndex**(FUN_0030ea54):入参 (x=槽状态， mode=ResolverMode, exec_index, target)。
  - 当 `mode ∈ {0xF,0x12..0x17}`(位掩码 0xF9>> (mode-0xF) &1,即 {0xF,0x12,0x13,0x14,0x15,0x16,0x17}):`target 1/2/3 → 2;4 → 3;5 → 4;6 → 5`;其余 target → "Unknown DetectionTarget"(行 0xd7)abort。
  - 否则:`exec_index < 2` 原样返回；≥2 → "Unknown ExecIndex"(行 0xe6)abort。
  - 函数末尾返回 **8 = UNKNOWN/错误哨兵**。
  - ⇒ ExecIndex 枚举：0、1(直通)，2/3/4/5(由 target 映射)，8(unknown)。
- **ExecMode**(FUN_0030eaec):读 `*param_3`(模式字)：
  - `0`:若 `vtable+0x1b0(this+4) != 0`(判为主/从实例的谓词，本报告记作 **isSlave()**,存疑见 §9)→ 返回 0,否则返回默认 `param_4`。
  - `1`:若 `param_3[1] >= 1 && param_3[5](byte) >= 1 && !isSlave()`:若 `mode ∈ {0xF,0x12..0x17}` 且 `param_3[2]`(CallbackFixType)`==2` → 返回 1;`==1` → 落到返回 0;其他 → "Strange Xhd CallbackFixType"(行 0x10a)abort。
  - `2` → 返回 0。
  - 其他 → "Unknown ExecMode"(行 299=0x12B)abort。
  - ⇒ ExecMode 枚举 {0,1,2};**CallbackFixType:{1,2} 合法**。

### 1.5 part / 槽 体系

- **part 编号 0-4**(AED 5 槽)。`FUN_00314c8c`(TkSet conf)的表 `PTR_DAT_00d74d38`:`part 1,2 → "head";3,4 → "body";0/其他 → "none"`(默认表 DAT_00314db4 = "none")。
- **跟踪槽(TrackSlot)0-2 与 part 的映射**(FUN_00316254):slot0 → {part0},slot1 → {part1, part2}(head),slot2 → {part3, part4}(body)。
- **XHD 使能优先级表** `DAT_01057313`(文件偏移 0xF4F313,3 行×5 字节，0xFF 结尾):仅第 0 行有效 = `[4, 3]` — 即 **XHD FoundEnable 只看 part4、part3(body)是否检出**。
- AED 状态对象(FUN_008919fe 单例索引，stride 0x10F8):`+4+part*4` = 每 part 检出状态(`==3` 视为 found),`+0x18+part*4` = 每 part LH 状态(`==2` 视为 LHEnable);`+0`(FUN_00891abc)= 总状态;`+0x10BC`(d3e)= 子状态;`+0x10D8`(e48)= 场景态;`+0x10E0`(e58)、`+0xFD8`(21e0)、`+0x884`(fe0)= 各标志;`+0x10C4`(d4e)= XYZ/纵深标志。

### 1.6 AllSearch BuilderType(FUN_00310d00)

`switch(type)`:0→`FUN_008bd98a`,1→`FUN_008bdce6`,2→`FUN_008bdeae`,3→`FUN_008bdef0`(四个均返回 vtable 指针 0x11e8c48 等的构建器类)，结果存 `AllSearchRegularRegionBuilder+0x2EBC`;其他 → `[AED][build] Unknown builder type %d`(行 0x4E)abort。四个具体构建器差异未进一步命名(见 §9)。

---

## 2. Block 1 — resolver_search.cpp / xhd_search.cpp(0x30dbd4-0x310b00)

### 2.1 FUN_0030dbd4 / FUN_0030e360 —— Search 按 SearchMode 的 build / execute 分派

- 输入:`param_4` = Search 上下文;`param_4[0]`=使能，`param_4[4]`=SearchMode。FUN_0030dbd4 只做“把 Settings 对应偏移的参数搬进 Search 对象”；FUN_0030e360 同一 switch,末尾再调 `vtable+0x18c(obj@this+0xc, mode, this+0xc)` 真正执行，结果写 `param_4[0x1950..0x1952]`。
- SearchMode 0x14 分支(两个函数相同)构造 **XhdTrackingAlignParam** 常数块(地址 +0x1840):

```
[0x1840]=1; [0x1844]=0xB0(-80 有符号); [0x1845]=2; [0x1850..0x1853]=x,y(来自 param_2 指向结果的 +0xC/+0xE, u16)
[0x1854]=0x40,[0x1855]=0x01 → u16 320; [0x1856..0x1857] 同 → 320   (320×320 搜索框)
[0x185C..0x185F]=0xFF×4; [0x1868]=16; [0x1869]=32; [0x186D]=2
```
即：以上一帧跟踪中心 (x,y) 为中心、320×320 的对齐搜索框，附 -80/2、16/32、2 等步进/阈值常数(字段名不可恢复，见 §9)。

### 2.2 FUN_0030f204 —— AED 结果校验(内部名 `aed_result_is_incorrect`,佐证 0x0030f3b0)

```
通过 vtable+0x14(this+0x10) 取框 → vtable+0x90 取参数 → FUN_0088b658(...) 校验(眼点几何)
失败 → log(level 8, 行0x117) "aed_result_is_incorrect() ..." + 行0x11E "eye_r(%4.2f,%4.2f) eye_l(%4.2f,%4..."
返回 校验通过与否(bool)
```

### 2.3 FUN_0030f404 —— `getMasterPattern`(getMasterPattern 佐证 0x0030f63c)——XED 主模式决策

```
scoped trace("getMasterPattern", 行0x130)
if (vtable+0x154(this+0x10)==1 || vtable+0x1b4(this+0x10)==1) → pattern = 0 (ALL)
else:
  st   = FUN_00891abc()           // AED 总状态
  sub  = FUN_00891d3e()           // 子状态
  found= (st==3) || (FUN_00891b24(part)==2)     // bVar1: "已锁定/检出"
  FUN_008b9248(this)              // 向 vtable+0x10(this+4) 下发 (lock_range+0x5C,+0x70, box,4) —— 设定 lock-on 范围
  if (FUN_008921e0()==1)  → log(行0x150) "search_all: out of lock on range" → pattern = 0 (ALL)
  if (found):
      if (sub==4)            → pattern = vtable+400(0x190)(this+0x14)
      elif (FUN_00891fe0()==2) → pattern = 0x0B RELIABLE_SECOND
      else:
        xyz = FUN_008b92f8(this)        // vtable+0x1ac(this+0x14)==1 时取状态+0x10C4,否则 0 —— "Z(纵深)搜索使能"
        sc  = FUN_008b9202()            // 场景判别(见下)
        q1  = FUN_008b9298(this)        // vtable+0x18(this+4) 查询 → 1=ALIGN 族 / 2=ALL_MARIO 路径用
        对 (ALIGN Pair, NonAlign Pair) 各算一对:
          Pair_align  = xyz? {0x0E RELIABLE_ONLY_XYZ_ALIGN | 0x08 RELIABLE_XYZ_ALIGN} 基 0x0F/0x09
          Pair_plain  = xyz? {0x10 RELIABLE_ONLY_XYZ      | 0x0A RELIABLE_XYZ}      基 0x0C/0x05
        sc!=0 → 取 *_ONLY 变体;最后 q1==1 → 取 Pair_align 否则 Pair_plain
  else: // 未检出
      if (sc==0 || st==0): q1==2 → 0x11 ALL_MARIO; q1==1 → 0x06 ALL_ALIGN; else 0 ALL
      elif (sc!=1) assert(行0x174) ; else → 0x02 POTENTIAL
```

辅助函数语义(已反编译)：
- `FUN_008b9202()`:若 `FUN_00891eaa()`(存在 LH=2 的 part 且总状态≠3 且无 part found)→0;否则查两个全局 vtable(+0x48/+0x4c):`*B==0→0; *B==0x15(21)→1; *A==0→1; else 0`。**语义:场景/主体类别判别，1 时选择 RELIABLE_ONLY 族**。
- `FUN_008b92f8(this)`:**“Z/纵深搜索使能”**——`vtable+0x1ac(this+0x14)==1` 时返回 AED 状态 `+0x10C4`,否则 0。旁证:`FUN_0030f674` 中它决定 SLAVE_RELIABLE(0x17) vs SLAVE_RELIABLE_XYZ(0x18)。
- `FUN_008b9298(this)`:经 `vtable+0x18(this+4, box, out)` 查询返回值；**==1 → ALIGN 变体，==2 → ALL_MARIO 分支**(具体物理量未定，存疑 §9)。

### 2.4 FUN_0030f674 —— `transfer(mode, &out, &flag)`(佐证 `transfer(%d) mode_pattern %d` 行 0x2e)

```
sub  = FUN_00891d3e();  valid_xy = FUN_00892568(*mode)   // mode+0xC/0xE 两个 short != -1
lh2  = (FUN_00891abc()==3) || (FUN_00891b24(part)==2)
val  = FUN_00891fe0();  *flag_out = 1
xyz  = FUN_008b92f8(this)
pat  = xyz? 0x18 SLAVE_RELIABLE_XYZ : 0x17 SLAVE_RELIABLE
if (sub==4)        → pat = vtable+0x194(this+0x14)
elif (val==2)      → pat = 0x19 SLAVE_RELIABLE_SECOND
elif (valid_xy)    → 若 !(lh2 && mode[0]!=0) → pat = vtable+0x198(this+0x14)
elif (!lh2)        → pat = vtable+0x198
log "[transfer(%d) mode_pattern %d]"; FUN_008854a2/FUN_00885678(global, flag) 记录全局从模式
```

### 2.5 FUN_0030f7a0 —— `Slave_Mode_Pattern(mode, flags)`(佐证 0x0030f890)

```
if (vtable+200(0xC8)(this+0x10)==1 && mode!=NULL)  → dump mode 的 9 个字段(0,4,0xC,0xE,0x18,0x1A,0x1C,0x1E,0x30)
pat = FUN_0030f674(...)
name = (pat<0x1A)? DAT_00d74cd0[pat] : "unknown_pattern"
log(行0x1C6) "Slave_Mode_Pattern %s %d"
if (!FUN_0030f204(this))  { flags[1]=0; pat = vtable+0x198(this+0x14); }   // AED 结果不正确 → 回退
*(this+0x18) = pat;  return pat
```

### 2.6 FUN_0030fa00 / FUN_0030facc —— XED 与 XHD 的主/从入口

- **FUN_0030fa00(this, isSlave, mode, flags)**:`isSlave==1` → `FUN_0030f7a0`,日志行 0x222 `"XED_Slave_Mode_Pattern %s %d"`;否则 → `FUN_0030f404`,行 0x226 `"XED_Master_Mode_Pattern %s %d"`。**⇒ Master = 用 getMasterPattern 的高置信(XED)主实例；Slave = 用 transfer/Slave_Mode_Pattern 的从实例**(模式名全为 SLAVE_*)。函数在文件中无直接调用点 ⇒ 经 vtable 调用(见 §9)。
- **FUN_0030facc(this, src, mode, flags)** —— XHD 模式:
  - `src==0`(主路径):`in = {FUN_008b9202(), FUN_008b9298(this), false}`;
  - `src!=0`:`in = {0, FUN_008b9298(this), (FUN_00892568(*mode) && *(int*)(*mode+4)!=3)}`;
  - `pat = FUN_00310554(this+0xC, &in, flags)`(XhdResolver.transNg);
  - 若 `vtable+0x154(this+0x10)!=0` → pat=0;
  - log(行 0x246)`"XHD_Master_Mode_Pattern %s %d"`(XHD 无 Slave 日志串)。

### 2.7 FUN_0030f8ac —— 资源校验(佐证 `active %d, max %d, assignable %d` 行 0x1F2)

```
active = param_2[5]; max = vtable+0x184(this+0x14); assignable 常量 = 5
log(行0x1F2) "active %d, max %d, assignable %d"
assert: 1 ≤ active ≤ 5(行500/0x1F5);active ≤ max(行0x1F6)
对 5 个槽(基址 param_2 + i*0x6568):
   槽+10(id, s8) != -1 而槽+0x14==0 → assert(行0x1FF)
   对 3 个子区标志(+0x1964, +0x32BC, +0x4C14):槽+0x14==0 而子区≠0 → assert(行0x205)
```
⇒ **搜索资源 = 5 个槽 × 0x6568 字节；active/max/assignable 三元组中 assignable 恒为 5**。

### 2.8 FUN_008ad028 —— `getModeInfo5…`(佐证 `getModeInfo5SA…` 0x0030f1c4)——按 ModePattern 填 5 槽

- 若 `vtable+0x188(this+8)==1`(简化路径):槽 id ← 表指针 `DAT_01727078[0]` 指向的 26×5 字节表(= &DAT_01057331,稀疏：多数模式 1-2 个槽)；基矩形 ← `DAT_01727090[0]`(=0x1726448,RAM),子矩形 ← `DAT_017270A8[0]`(=0x148ABC0,RAM)。
- 常规路径:id ← `DAT_017270C0[0]`(= &DAT_010573B3,26×5 富表)；基矩形 ← `DAT_017270D8[0]`(=0x148A5A8,RAM);子矩形 ← `DAT_017270F0[0]`(=0x1489360,RAM)。
- 每槽写入：id→slot+10;exec_mode(FUN_0030eaec)→slot+0x6568(即下一槽首，实为槽尾字段);exec_index(FUN_0030ea54)→slot+0x6569;基矩形 3×u32(from per-mode 表)→slot+0x14;再按 `FUN_008acf28` 的 3 个 9 字节子记录(各带使能位)写 slot+0x1964 / +0x32BC / +0x4C14(+第 4 记录 +0x6560);同一子记录的宽/高/标志写 slot+0x32B0/0x32B1、0x4C08/0x4C09、0x6560/0x6561。
- 富表(id B)&DAT_010573B3 按模式给出 5 槽的 part(0xFF=空)，例:
  - mode0 ALL → `[0,0,1,1,2]`;mode1 RELIABLE_SHIFT → `[2,3,0,1]`;mode2 POTENTIAL → `[0,0,0,1,1]`;
  - mode5 RELIABLE → `[2,3,0,1]`;mode12 RELIABLE_ONLY → `[0,1,0,1]`;mode17 ALL_MARIO → `[0,0,1,1,2]`;
  - mode18/19 SLAVE_XYZ(_SPEED) → `[0,1,2,3]`;mode20-24 → `[0,0,1,1]` / `[0,0,0,1]` / `[0,0,1,1]`;
  - 稀疏表(路径 A)&DAT_01057331:mode0 → `[0,0,0]`,mode1 → `[1,0]`,mode3/4 → `[0,0]`,mode12-16 → `[0,0]`,mode18/19 → `[0,1]`,mode25 → `[0,0,0,0]`。
- **RAM 表(0x1489360/0x148A5A8/0x1726448)不在固件文件内**，运行期由 `FUN_008acd04`(构造器)把 4 块 RAM 缓冲(0x19B63D4/0x19B8C74/0x19B969C/0x19BAAEC)与两套静态表指针(条目 0/1)装入指针槽 0x1727078-0x1727108(各 6 项)；运行期可整体切换(手动/自动/XHD 变体由 `FUN_008acf28` 的 base+0/+0xC/+0x18/+0x24/+0x30 选择)。

### 2.9 FUN_008b9e8a —— 搜索路径序列播放器(“SHIFT” 的实现体)

```
entry = table_base + cursor*0x28        // table_base = table_id*200 + *(state+0)   (200B/表 = 5 步×40B)
entry = {u16 dx(@+0,+1), u8 dy(@+2), payload[37](@+3)}
若替换模式(replacement==1):经全局 vtable+0x150 以 cursor 取“替换表项”(活体替换)
pos = *(u16*)(state+4) + dy;  clamp 到 max(param_4);  *(state+4) = pos
若 max ≤ pos 或 entry[0]==0 → state+2 = 1(序列结束)
out = {x=u16(dx), y=clamped dy, payload[0x25]}
```
⇒ **RELATIVE_SHIFT 类模式的“扫视轨迹”是一张每模式 5 步、步长 40 字节的记录表，逐帧播放**。(调用点 FUN_008acf28 → FUN_008b9e8a,日志 `[GetTable] is_auto %d is_xhd %d …` 行 0xB4。)

### 2.10 XhdResolver(FUN_00310288 / 0031034C / 0031041C / 003104DC / 00310554)

- **FUN_00310288 `[XhdResolver] FoundEnable`**(日志行 0x31 `[XhdResolver] FoundEnable Enable part %d`):按 `DAT_01057313` 的 3 行(实际有效第 1 行 = parts [4,3])检查 `FUN_00891ae0(state, part)==3`,命中则把 part 追加到输出表(param_2+6=计数,≤5)并返回 1;三行扫完返回 0。
- **FUN_0031034C `[XhdResolver] LHEnable`**(行 0x59):同结构,谓词换成 `FUN_00891b24(state,&part)==2`。
- **FUN_0031041C(状态计算)**:
```
sc = FUN_00891e48();  found = FUN_00310288(...);  lh = found? : FUN_0031034C(...)
if (sc==4 && (found||lh)) → ret 5
elif (sc==5 && found)     → ret (*prev==0)? 3 : 2
elif (lh && FUN_00891e58()!=0):
    if (FUN_00891e58()==0) → ret (*prev==0)?3:2
    elif (sc==5)           → ret 4
elif 无命中 → ret = prev[8](保持旧状态)
log(行0x93) "[XhdResolver] state ret %d"
```
- **FUN_003104DC(状态→XHD 模式)**(前提:全局 vtable+0x1B4()==0,否则恒返 1):

| state | → XHD pattern |
|---|---|
| 1 | 8 XHD_TRACKING_ALIGN |
| 2 | 6 XHD_RELIABLE_ONLY |
| 3 | p2[4]==2 → 4 XHD_RELIABLE_ALL;==1 → 2 XHD_RELIBLE_AF_ALIGN;else 4 |
| 4 | p2[8]!=0 → 10;+4==1 → 0xB;else (*p2==0 ? 0xC : 5 XHD_RELIABLE_XY) |
| 5 | 9 |
| default | +4==2 → 7 XHD_MARIO;==1 → 1 XHD_AF_ALIGN;else 0 XHD_ALL |

- **FUN_00310554 `transNg`**:log `[XhdResolver] transNg %d align %d …`(字段 *p2/p2[4]/p2[8])→ FUN_0031041C 求 state → FUN_003104DC 求模式 → `out[1] = *flags`。

### 2.11 FUN_0031005C / FUN_003105D8(xhd_search.cpp 辅助)

- FUN_0031005C:按某 pattern 字(1/3/5/0xB/0xC/0xD 有效,其余默认全 1.0f)从 `this+8` 对象的成组 vtable getter 取 **5 个 float**(×5 组)，默认 {1,1,1,1,1}——按模式取的尺度/权重参数(具体含义未定)。
- FUN_003105D8 `getSetting`(search_setting):先 `vtable+8(this+4, …)` 全局设置,再对 5 槽循环:`slot 掩码(param_3+6) bit i 置位` 才调 `vtable+8(this+8, …)` 构造该槽;`FUN_0088569c(global, param_3)` 收尾。

### 2.12 ExecInfoCreator(FUN_0031070C / FUN_00310980,execinfo)

- **FUN_0031070C**:由 {is_xhd(+4), has_xhd(+5), slot 掩码(+6), 类型(+0xC:5/6 特判), (+0x10)} 生成 **6×u16 Spec**:`FUN_008ba496(out, submode)` 默认 {1,1,3,1,1,1} 再经全局 provider 的 6 个 getter(vtable+0x1E4..0x1F8)填充；多路子模式(0..5、6/8、9/0xB、7)结果**逐元素取 max** 合并；日志 `input.is_disable_adam_peak is %s`("true"/"false")、`[ExecInfoCreator] Spec ps %d adam %d …`、`Spec xhd %d xh…`。
- **FUN_00310980**:输入 packed u32 `param_4 = {byte0=pattern, byte1, byte2, byte3}`;`state = byte1? 0 : (byte2? 2 : 1)` 存 +0x10;byte0 变化且 state 不变 → "ExecInfoCreator clear"(清 +0x14/+0x18/+0x1D);`FUN_008ba512(state_ctx, &input)` 求出 out_mode(0/1/2),据此读 +8/+0xA/+0xC/+0xE 得 xhd 两个 u16;日志 `[ExecInfoCreator] input exec_pat…`、`prev_mode %d prev_cnt %d`、`out_mode %d x…`。

---

## 3. Block 2 — generator/*(0x310b00-0x313000)

### 3.1 参数构造器(Setting::SearchParams::getXxx)

| 函数 | 断言串(getter 名) | 要求 SearchMode | 拷贝内容 |
|---|---|---|---|
| FUN_00310bc8 | getAllSearchParam | 2 | u8@0xA8,u32@0xAC,u16@0xB0,5×8B@0xB4,5×u32@0xDC,vec@0xF0 |
| FUN_00310c84 | (param_internal,type==1) | 1 | u8 + 5×0x20B(0x04..0xA0)+ u8@0xA4 |
| FUN_00310d00 | SetBuilderType(all_search_regular_region_builder.cpp) | — | 见 §1.6 |
| FUN_00310eac | getPotentialSearchParam | 0x0B | u8@0x850 + box@0x858(FUN_00889428) |
| FUN_00311528 | getReliableSearchParam | 0x0C | u8@0xF90 + box@0xF98 |
| FUN_00311590 | getZSearchParam | 0x08 | u8@0x1750 + obj@0x1758 + 0x70B@0x1760 |
| FUN_00311614 | getSecondSearchParam | 0x0A | u8@0x110 + box@0x118 |
| FUN_003119f4 | getXhdXySearchParam | 0x16 | 2×u32@0x1890 + 0x80B@0x1898 + u8@0x1918 + vec@0x191C |
| FUN_00311f40 | getXySearchParam | 0x04 | u8@0x16D0 + obj@0x16D8 + 0x70B@0x16E0 |

(`FUN_0083db68/FUN_008c46e2` = 定长拷贝;`FUN_00889428` = box 拷贝。)

### 3.2 FUN_00310f14 —— `calcScalingRegion`(region_generate_utility.cpp,佐证 `[AED][calcScalingRegion]`)

```
cx = (s16)ofs[+4] + u16@region+4 ; cy = (s16)ofs[+6] + s16@region+10   // 中心 = 基准中心 + 偏移
if (cx|cy) < 0:  param_8==1 → assert "[AED][calcScalingRegion] cx < 0 or…" → 走兜底
if (scale 为 NaN/负) || framesz > 0x2EF(751) → 兜底
norm = (float)size(@region+8) * scale * (1<<level(@region+0)) / 640.0f     // 640 = DAT_003111a4
在 32 项表 DAT_016A3A38 中找第一个 threshold ≥ norm 的项 {threshold f32, shift u32, min_size u16}
if (flag==1): cx = ShiftRegion(cx, iVar8, shift, 1); cy = ShiftRegion(cy, iVar8, shift, 1)
cx' = cx * (1<<level) / (1<<entry.shift)   (取正、cx 强制偶数 &0xFFFE)
out = {shift, framesz, cx', cy', min_size, min_size, 0, valid=1, id=FUN_008be33a(...), 0,0}
成功路径要求 FUN_008be42e(this,&entry)==1,否则 log(行0x11C)"[AED][calcScalingRegion] invali…" 后兜底
兜底:out = 默认块 DAT_01735F80;out[1] = framesz - (framesz/max)*max + 400   (max = vtable+0x184)
```

**缩放级别表(运行期由 FUN_008be8ba 初始化，RAM 0x16A3A38,32 项 × {f32 threshold, u32 shift, u16 min_size})——全表：**

| threshold | shift(÷2^shift) | min_size | threshold | shift | min_size |
|---|---|---|---|---|---|
| 0.20 | 1 | 0x40(64) | 0.80 | 3 | 0x40 |
| 0.225 | 1 | 0x48(72) | 0.90 | 3 | 0x48 |
| 0.25 | 1 | 0x50(80) | 1.00 | 3 | 0x50 |
| 0.275 | 1 | 0x58(88) | 1.10 | 3 | 0x58 |
| 0.30 | 1 | 0x60(96) | 1.20 | 3 | 0x60 |
| 0.325 | 1 | 0x68(104) | 1.30 | 3 | 0x68 |
| 0.35 | 1 | 0x70(112) | 1.40 | 3 | 0x70 |
| 0.375 | 1 | 0x78(120) | 1.50 | 3 | 0x78 |
| 0.40 | 2 | 0x40 | 1.60 | 4 | 0x40 |
| 0.45 | 2 | 0x48 | 1.90 | 4 | 0x48 |
| 0.50 | 2 | 0x50 | 2.00 | 4 | 0x50 |
| 0.55 | 2 | 0x58 | 2.20 | 4 | 0x58 |
| 0.60 | 2 | 0x60 | 2.40 | 4 | 0x60 |
| 0.65 | 2 | 0x68 | 2.60 | 4 | 0x68 |
| 0.70 | 2 | 0x70 | 2.80 | 4 | 0x70 |
| 0.75 | 2 | 0x78 | 3.20 | 4 | 0x78 |

⇒ **金字塔级别 1-4(÷2/÷4/÷8/÷16),归一化尺寸(norm = size·zoom·level/640)跨过阈值即换级，并给出该级最小搜索框(64-120)**。

### 3.3 FUN_003111d8 —— `ShiftRegion`(佐证 `[ShiftRegion] %d ret %d cm %d p…` 行 100)

```
margin = size>>1;  if flag: margin = (size>>1) - (0x10 << shift)     // 再减 16<<shift
if (p < size)          → case1: ret = p>>1
elif (c < margin)      → case2: ret = margin
elif (p < margin+c)    → case3: ret = p - margin
else                   → case4: ret = c
```
(把位置 p 相对中心 c、半尺寸 margin 收进界内；case 号与各参量入日志。)

### 3.4 旋转与 FB 尺寸

- FUN_0031128C `setCameraRollAngle`(佐证 0x010541A6):`RotateMode`(vtable+0x74)→角度:`0→0, 1→+90(0x5A), 2→180(0xB4), 3→-90(0xFFA6)`,写入 CentralRegion+0x10;default assert(行 0x22A)。
- FUN_003113AC `getTargetZeroAngle`:同映射但 1→-90、3→+90(反向),int16 返回。
- FUN_003112D4 `getRotateCursorMax(rotate_mode)`(佐证 `[AED][getRotateMax] rotate_mode_e…`):mode 0→0;1-8→vtable+0xFC..0x11C 各 getter;9→1;10→vtable+0x11C;其他 assert+abort。**RotateMode 枚举 0-10**。
- FUN_00311420 `SIZE_FB`(佐证 `[SIZE_FB] before/after res %d cx %d cy %d`):`flag |= 0x10000`;把 cx(+2)/cy(+10)按 `|src_level - dst_level|` 左/右移(始终偶数)，再拷贝 dst 的 +0xC/+0xE,`res ← dst_level`。⇒ **区域尺寸跨分辨率级(FB=frame-buffer 级)的移位换算**。

### 3.5 FUN_0031167C / 00311750 / 003118A0 —— XedEstimateFrameSmoother(xed_estimate_frame_smoother.cpp)

- FUN_0031167C `smoothing(in)`:要求 in.w==in.h(方框，assert 0x28);`FUN_00311750` 判 IoU/尺寸一致，不一致 → `FUN_00670BA4(cur,0x13)`(重置);`vtable+0x200 >= 0` 时直接拷入;`FUN_003118A0` 做滤波;log `[XEFS] width %d > %d cx %d > %d cy %d > %d`;输出拷回。
- FUN_00311750 `[XEFS] is_iou_ok`:两框 (cx-w/2, cy-h/2, w, h) → `FUN_002CE40C` 算 IoU;`iou_ok = IoU > thr1(全局 vtable+0x134)` 且 `area_a < k*area_b && area_b < k*area_a`(k = vtable+0x210,双向尺寸比检查);log `[XEFS] is_iou_ok %d is_same_size…`。
- FUN_003118A0 平滑步(指数包络):
```
cur = 平滑尺寸(+0x14, u16);  if cur==0 → 直接拷贝新框
lo  = min(vt+0x14, vt+0x18); if lo==0 → lo = 4.0        // 分母下限
step_max = 128.0f / lo                                   // DAT_003119EC = 128.0
step = (cur >= step_max)? cur : step_max                 // 上行步长
step -= tbl/vt+0x204 / lo ;  up = step * vt+0x208 ; down = -(step * vt+0x20c(u32))
down_floor = DAT_003119F0 = 0.0f(若 up<=0 用 0)
+0x2C = cur + up ; +0x30 = cur + down
if (cur+down ≤ new_size && cur+up > new_size 之外成立才接受) → 把新框拷入状态(+8..+0x25)
```
⇒ **平滑器以当前尺寸为基准维护 [cur+down, cur+up] 接受窗口，新检测结果落窗内才更新状态**。

### 3.6 FUN_00311B9C —— `getZVariableSearchParam(mode)`(佐证 `[Keypoint] getZVariableSearchPara…`)

SearchMode 0x12/0x13/0x14/0x15 四份,分别取 Settings +0x17D0/+0x1800/+0x1830/+0x1860,布局均为:
`{u32@+0, u32@+4, 32B@+8, u16@+0x2C, u32@+0x28}`;非法 mode → assert+abort。**0x14 份即 XhdTrackingAlignParam(§2.1)**。

### 3.7 FUN_00311CE0 —— `XhdZAlignRegionGenerator::get(index)`(xhd_z_align_variable_size_region_generator.cpp)

```
cnt = vtable+0x10(this);  if (index >= cnt) → assert "[Keypoint] XhdZAlignRegionGenerat…"; index = cnt-1
base = max(u16@this+0x8C, u16@this+0x8E)
size = (base * u8 ratio_table[this+0xA0 + index]) >> 4        // 比例表定点 /16
return (u16)(size | size<<16)                                  // {width=size, height=size} 方框
```
⇒ **Z(纵深)搜索 = 以固定比例表(每步一项，/16 定点)对基准尺寸逐级缩放，每级一个方形搜索区域；index 即纵深假设步进**。与 `getZVariableSearchParam`(4 份模式参数)和 FUN_0031005C(每模式 5 个 float)共同构成 Z 搜索参数面。

### 3.8 FUN_00311E14 —— `XYSearchRegionGenerator::isPicInXYSearchArea(pic, type)`(xy_search_region_generator.cpp)

```
if (this+0x60==0 || this+0x61==0) → return true            // 功能关 → 全域允许
for part in 0..4:
    v = vtable+0x16C(this+8, part)                          // 每 part 数值
    q = (u64)(v * 2^40 / 10000.0f)                          // DAT_00311EC0=2^40, DAT_00311EC4=10000
    hi = q >> 32
    if (hi < *(u32*)(this+0x6C) || *(u32*)(this+0x6C) - hi < (q <= *(u32*)(this+0x68))):
        → 命中;按 XYSearchAreaType(0-4,default assert 行0x11B)查表返回 bool
未命中任何 part → return (type==0)
```
⇒ **判定给定画面/区域落入哪一 XY 搜索分区(类型 0-4)**;阈值在 +0x68/+0x6C,per-part 值经 2^40/10^4 定点换算。type 表内容因 Ghidra 跳表展平不可完整恢复(§9)。

---

## 4. Block 3 — region_provider + search_controller(0x312894-0x313139)

### 4.1 FUN_00312894 —— `RegionGenerateUtility::convertToInstanceNumber`(佐证 `[convertToInstanceNumber] invali…` 行 0xA8)

`target: 1→1, 2→2, 3→3, 4→4, -1/0→0, 其他 assert+abort`。**实例号 == part 号(1-4),0 表示无**。

### 4.2 FUN_003134DE / FUN_00313566 —— `isOverOptionInterrupt` / `isOverOptionInterrupted`

两者均为**纯虚调用兜底/非法枚举桩**(region_provider.cpp,行 0x261/0x26B):
- FUN_003134DE:assert "[isOverOptionInterrupt] invalid i…" → 返回 1。
- FUN_00313566:assert "[isOverOptionInterrupted] invali…" → 返回 0。
⇒ 存在“选项(用户 AF 区/对焦模式)越过即中断搜索”的机制，真实实现在派生类；桩只证明接口语义(§9)。

### 4.3 FUN_003135DC —— `RegionProvider::getRegion`(search_controller.cpp)

```
if (vtable+0x5C(this+8)==0) → FUN_0089255E/FUN_008925E6(复位 AED 结果)
构造请求 {flags(0,0,0,0x1F,0), 1, 0x1A(26), 0x0D(13), 0, 0xFF, 0xFFFFFFFF, param_5}
清空输出缓冲 DAT_014B2DD8 并对 5 槽(0x14B2DE0 起, stride 0x6568)调 FUN_008C3D06 清理
ret = vtable+8(this+0x14, &req, &buf, &flags, param_3, param_4)
FUN_0088684E/FUN_00887102(global, param_5)
cnt = vtable+8(this+0xC, &buf, &this->count)      // 第二个 provider 产出数量
cnt==0 → assert "[ERROR] get_region fail %d"(行0x8E)
若 vtable+0x98(this+8)==1:按 cnt 打 "region_id %d %d %d" / "%d %d" / "%d"
对每条 Region_Param(stride 0x20=32B):
    {u32@0, u32@4, s16@8, s16@A, s16@C, s16@E} 全 0 → assert "[ERROR] Region_Param is all_zero!!"(行0x97)
    vtable+0xA8(this+8, i)==1 → log "id %d ip %d indx %d res %d cx %d …"
       (Region_Param: res=u32@0, id=u32@4, cx/cy=s16@8/0xA, w/h=s16@0xC/0xE, s16@0x10, u8 ip@0x1C, u8 indx@0x1D)
*(this+4) = cnt;FUN_0088603A/0088604E/00886062(global+0x2908, 0x1A / 0x0D / 0xFFFFFFFF)
*out = cnt; out[1] = Region_Param 数组指针(this+0x1C)
```

### 4.4 FUN_003138FE —— `[AED] Not Match Search Result Nu…`

仅打日志(level 2,行 0xC3)——**AED 检出数量与搜索结果数量不一致的告警点**(无其他副作用)。

---

## 5. Block 4 — TrackController / TrackSetting / TrackSequencer / TrackTask

### 5.1 FUN_00313944 —— `TkCon::skip_request / overwrite_init_param`(track_request.cpp)

```
N = vtable+0x1E4(this->obj1)          // skip 周期;0xFF = 禁用
if (vtable+0x1B0(this->obj2)==0) → vtable+8 分支(反编译跳表丢失)
else:
  cnt = ++this[3]
  if (cnt % N == 0):  // skip 帧
      对 3 个请求槽(this 侧 stride 0x250,请求侧 stride 0x124,记录 {u16 id, u8 type@+2, payload@+8}):
          暂存 {id, type, payload} 到 this+0x18/0x1A/0x20(每槽 0x250),置 pending=1(this+0x10)
          请求记录 type ← 2;槽基字节 ← 1
      log "[TkCon]skip_request count %d i…"(行0x4E)
  else:  // 普通帧
      对 3 槽:若 请求 type!=0 且 pending:log "[TkCon]overwrite_init_param %d…"(行0x3C)
              用暂存 {id,type,payload} 覆写请求;清 pending
```
⇒ **skip_request 语义：每 N 帧(可配)把新的(重)初始化请求挂起，下一正常帧再覆写生效 —— 初始化请求节流**。

### 5.2 FUN_00314B7C —— `TrackController::xed_confidence` → {0,1,2}

```
if (kind==1 && xed_slot==NULL) → assert "[TrackController] xed_confidence…"(行0x253) → 2
if (xed==NULL) → kind? 0 : 2
a1=xed+0x24, a2=xed+0xDC, b1=xed_slot+0xA4, b2=xed_slot+0xAC
hit = FUN_0089236C(ctx+0xE24, b2, b1)      // 在 ctx+0x4C 的"已跟踪目标链表"里查 id(见 FUN_0089236C)
if (kind==1 && xed_slot!=NULL && b1!=0 && ((b2!=a2 || b1!=a1) | (p6&p5==1)) && hit)
    → return 0                              // XHD 与 XED 指认不同目标且在跟踪链表中 → 矛盾
return xed[0x30]? 1 : (flag? 2 : 2→顺序: 2;[0x30]→1;param_3→2)
```
⇒ **0 = 被矛盾证据推翻；1 = xed[0x30](高置信标志)置位；2 = 弱/无效**。

### 5.3 FUN_00314DF8 —— `TrackController::xhd_confidence` → {0,1,2}

同构：XED 槽有效标志 `xed[0x140]!=-1`;矛盾条件 = (xhd+0x54/0x5C 与 xhd_result+0x24/+0x154 不一致) && xed+0x54!=0 && `FUN_0089236C(...)!=0` → 0;否则 `param_3!=0 && xhd_result[0xF8]!=0` → 1,否则 2。断言行 0x27F。

### 5.4 FUN_00314C8C —— `TkSet::%s_conf set`(part→head/body 消息)

```
msg.id 0x200→0x201;val = FUN_008C505C(part)          // part 1,2→"head";3,4→"body";else "none"
FUN_00891A98(2)+FUN_008921EE(state,0,&val)            // 更新 AED 状态视图
若 set+0xF8 且条件 → msg.sub=1,payload ← set+8(0x28B)
log(行0xC5) "[TkSet] %s c…"
```

### 5.5 FUN_00314230 —— `TkSet::head_conf(h %d s %d pa…)` —— head 槽裁决

```
st = FUN_00891A98(2)
若 part1 状态==0:preferred = (set+0xE1D==1 && set+0xE1B && set+0xE1C) ? true
                  : (set+0x988 && !set+0x989 && set+0x990) ? (set+0x9A8==1) : false
同理对 part2(0xE1D==2)得 cStack = 1 或 2(选择 head part 1/2)
xhd_slot = FUN_00891B78(st) + 200 + part*0x148        // 该 part 的 XHD 结果槽
conf = FUN_00314DF8(set, part_found==3, flag, set+0x988, xhd_slot)
if (conf==0):FUN_00314EF8(tmp, xhd_slot)(xhd_result_not_matched 载荷)→ 附到消息
else:        payload ← set+0x990(0x28B)
part 状态写回 FUN_008921EE;若 旧part!=-1 且 旧part!=新part → assert "init_part_different… init_part…"(行0x205)
log(行0x20C) "[TkSet] head_conf h %d s %d pa…"(两组表 DAT_003145C0/C4 按 set+0xE1B/0xE1C 选择)
out msg = {0x201, part, val}
```

### 5.6 FUN_00314EF8 —— `xhd_result_not_(matched)` 载荷构造

断言行 0xE7 `[TrackController] xhd_result_not…`;从 XHD 结果(x+0x50 为选中下标，-1 → assert)取 `x[idx*6+0x20]/[+0x21]`(→ out+0x10/0x14)、`x[0x15]`→+0x1C、字节 0x5A/0x59→+0x18/+0x20、`x[0]/x[1]`→+0xF0/F4、+0xF8=拷贝 x+2。下标 -1 → out[0]=0(空载荷)。

### 5.7 FUN_00314960 —— `TkSet::slave_disable_body_set`

```
for i in 0..2: handler = 表 DAT_00E28F88[i*2](参数表 DAT_00E28F8C[i*2]>>1 选源)
               生成消息写入槽 i(基址 this+8+i*0x248):{u16 id@+0x58, u8 part@+0x5A, payload@+0x60}
若 槽0/槽1 的 id 高字节(this+0x61 / this+0x2A9)都不是 0x02:
    构造 {0x200→0x201, val=2}(log "[TkSet] slave_disable_body_set… 2" 行0x81)写入槽 2(this+0x4F0)
this+0x58 = 1(槽有效)
```
⇒ **从实例(body)禁用消息**；与 head/body 置信消息共用 0x02xx 消息族。

### 5.8 FUN_00315354 / FUN_00316E08 —— `TkCon::startInitTrainTimer / sendStartInitTrain`

两者尾部相同：取全局 vtable+0x30 得 timer id,`thunk_FUN_002BEF4C(id, 7)` —— **启动 type 7 定时器(Init-Train 超时)**。FUN_00315354 额外：从 `vtable+0xFC(this+0x18)` 对象 +0x194 取 id 参数;`this+0xECC` 分两条路径(全局 vtable+0x118==1 → vtable+0x18C(id),否则 vtable+0x188);结束清 +0xECD 标志。日志 `[TkCon]startInitTrainTimer IN…`(行 0x241)/`[TkCon]sendStartInitTrain IN…`(行 0x566)。

### 5.9 FUN_00315480 —— `TkCon::Init_start_img_type / RequestID`

```
清 3 个 400B 请求记录(this+0xEF8, stride 400);count=this+0xEE8=0
对 3 个请求槽(param_5 + i*0x88,记录头在 -0x7B):
  valid 且 sync_type==1 → abort(0x24)
  valid 且 sync_type==0:
     msg={1, ..., img_type=DAT_0031570C[tbl] (={1,2,2,3,3}), p1=rec[-3]∈1..8, p2=rec[-1], 3×u32}
     FUN_00315750(...) 填载荷(含 "init_prc not found by pr…" 查找 FUN_00852C10;5×{u32,u32,u32,u16})
     vtable+8(this+8, i, &msg, rec+0x10, param_2) 发送;成功 → count++(≤3)
     log(行0x2B0) "[TkCon]Init_start_img_type %d i…"
  FUN_008C5CCE(this,i) 更新槽;RequestID = this+0xE58[i](可清零)
  log(行0x2D7) "[TkCon]RequestID %d sync_type…"
return count(0-3)
```

### 5.10 FUN_00316254 —— `[TkCon] id %d part %d high %d`

slot≤2 才处理;`FUN_00891A98(1)` 后按 slot 写 part:slot0→{0},slot1→{1,2},slot2→{3,4}(顺序 FUN_00892252 两次);再 `FUN_00892252(state, rec+0x20, high)` 其中 `high = (rec[1]==0) & param_4`。⇒ **把跟踪槽 id/part/高置信标志写入状态**。

### 5.11 FUN_00316B80 —— `TkCon::xed_result_track / xhd_result_track`(track_controller.cpp)

```
type = rec[0]  // 0=XED, 1-2=XHD
XHD(type 1-2):FUN_00315EB0(this, msg=this+0x728+type*0x248+0x58, xed=this+0x728+type*0x18+8, rec)
   part=rec[0x189]; sel=rec[0x270](s8); sel!=-1 → 取 rec+sel*0x18+0x1B0/0x1B4(u32×2 = 区域)
   log(行0x530) "[TkCon]xhd_result_track(s vali…)"(valid 标记取 "o"/"x" @0x316DE4/DE8,来源 rec[0x130]/rec+0x30)
XED(type 0):FUN_00315B8C(this, this+0x780, this+0x730, rec)   // 断言 "[TkCon]xed_result_invalid…"(行0x3A8)当区域空
   part=rec[0x111]; id=*(rec+0x10C); cx/cy/w/h = f32@0xC8/0xCC/0xDC/0xE0
   log(行0x51F) "[TkCon]xed_result_track(s vali…)"
vtable+0x110(this+0x18, &to, part)                       // 取该 part 的超时
if (FUN_008C5F6E(this, msgslot, to|3, &a, &b)):          // 超时判定(下)
    rec[0x30..0x33] = {1,0,0,0};  log "tracking_elapsed_timeout…"(行0x541)
vtable+0x1C(this+4, slot, {1, (rec+0x30)==0, rec[0x60]})  // 通知
FUN_00316254(rec+0x30 的 id, slot, msgslot, (rec+0x30)==0)
清 rec[0x10C..0x10F] 与 rec[0x184..0x187]
```
- **FUN_008C5F6E(超时判定)**:`elapsed = vtable+0x18(this+0x18) - FUN_003161DC(rec)`;`timeout = (vtable+0x1C4(this+0x18)==1 ? obj+0x1E8 : obj+0x24)(…)` 返回 u64;`return elapsed >= timeout`。`FUN_003161DC`:part 类型 1-4 → u64@rec+0x230;类型 0 → u64@rec+0xF0;其他 assert "[TkCon]part_type invalid so f…"(行 0x401)。
⇒ **跟踪结果回填 + "tracking_elapsed_timeout" 判定：超时则结果标记 0x30=1(失效)**。

### 5.12 TrackSequencer 10 状态机(核心交付)

分派器 **FUN_003179A8**:`state<10` → log `track_sequence_s %d` → `handler = PTR_LAB_00317A30_1_00E29258[state*2]`(表在文件偏移 0xD21258,已全部 dump)→ `handler(this+offset, param)` → log `track_sequence_e %d`;`state>=10` → 返回 4。**返回值:0=OK,2=可忽略(dispatchFromSequence 允许 0/2),4=非法状态**。

状态表(Ghidra 未生成函数体，以下由 capstone 反汇编 + 独有日志串命名，文件均为 `src/track_sequencer.cpp`):

| state | handler | 命名的成员函数(assert 串) | 关键日志/行为 |
|---|---|---|---|
| 0 | 0x317A30 | `execStartInit` | 校验 `request_id_`("[TrackSeq] invalid param request_id_:%d")与 unit_param x/y;查忙 → `"Init busy: %d"`;调 FUN_008C8600(StartInit,日志 `[TkSeq][StartInit] init_pos=(%d, %d) staple_exec_mode=%d type=%d`);入队失败 → "[TrackSeq] enque error";另调 FUN_00319CBC(setDf) |
| 1 | 0x317E28 | `execEndInit` | 处理 driver 消息("[TrackSeq] invalid drv_message param_mgr_id:%d");"[TrackSeq] pop stack failed";FUN_008C8956 "[TrackSeq] free unit handle" |
| 2 | 0x3180B4 | `execStartTrain` | `"Train busy %d"` / `"Train run %d"`;同样调 FUN_008C8600(StartInit)与 setDf |
| 3 | 0x31852C | `execEndTrain` | pop stack / drv_message / free unit handle |
| 4 | 0x3187A8 | `execStartDetection` | `"Track busy %d"` / `"Track run %d"`;FUN_008C9380/FUN_008C90F8(STAPLE 引擎调用) |
| 5 | 0x318C84 | `execEndDetection` | **`[TkSeq][EndDetection] staple_pos[0]=(%d, %d), staple_pos[1]=(%d, %d) type=%d`** —— 取回 STAPLE 两个单元的位置 |
| 6 | 0x3190D8 | `execCancel` | 极简:assert + FUN_008C7B06 |
| 7 | 0x8C857A | `execUpdateZpdResult`(另一模块,佐证 `TrackSequencer::SequenceError Ca…` @0x01055ED0) | ZPD 结果更新 |
| 8 | 0x319194 | `execBulkInitTrain`(佐证 0x01055AE7) | "Init busy"/"Train run %d"/"Train busy %d" 合并路径(批量 Init+Train) |
| 9 | 0x3197D4 | `execBulkDetection`(佐证 0x01055D59) | "Track run %d"/"Track busy %d"(批量检测) |

配套成员(字符串佐证):`startBulkInitTrain(BulkInitTrainParameters&)`(0x01055983)、`setDfParam(PrcInfo&, Alg::CameraImagerInfo&, TrackSetting::SettingData&)`(0x01055F38)、`makeStapleTrackSetting(...)`(0x01055900)。

- **FUN_008C8600 `TkSeq::StartInit`**:`init_type(set+0x1454)==1` 时 pos = (unit==2 ? u32@+0x64 : u16@+0x54) 否则 0xFFFF;`FUN_0082E81A(pos, unit)`(STAPLE 设初始位置);置位引擎状态 `*(base+unit+0x22710)=1`;依次 `FUN_0082E7D0(x,y)` / `FUN_0082E8A6(type,unit)` / `FUN_0082E860(＋0x1858,unit)` / `FUN_0082E8EC(+0x160C,0,unit)` / `FUN_0082E8EC(+0x16FC,1,unit)`。
- **FUN_00319CBC `setDfParam`**:PrcInfo(+0x178 检测类型 1→(＋0x180==0),2/3 原样,else 4)→ SettingData[0x17C];3 个 unit 记录(stride 0x48,含 2 个 std::string)拷至 +0x1504;CameraImagerInfo 经 param_4 vtable(+0x2C/+0x30/+0x34/+0x38/+0x40)填 0x61D/0x1876/0x187A/0x1879/0x61E;3 个 16B 区域 ← PrcInfo+0xE0;face 计数(PrcInfo+4)→[0x6C]、[100]=(count!=0)、[0x515]=1;`若 PrcInfo+0x1F`:log `track_sequence_s setDf %d 0x%04x` → `FUN_008C922A(...)`(应用)→ log `track_sequence_e setDf %d`。

### 5.13 FUN_0031A094 / 0031A1A8 / 0031A120 —— `TrackTask::dispatch / dispatchFromDriver / dispatchFromSequence`(src/track_task.cpp)

- dispatch:取消息负载(FUN_002BEE3C(msg,4));`type==1` → dispatchFromDriver;`type==0` → dispatchFromSequence;其他 → assert `[TrackTask] invalid message type`(行 0x58);最后 `FUN_0085303E(msg, 0x90060975)`(消息确认魔数)。
- dispatchFromDriver(payload 4B):state = payload[1] → `FUN_003179A8(this+4, state)`;非 0 → assert `[TrackTask] dispatchFromDriver e %d…`(行 0x76)。
- dispatchFromSequence(payload 8B):state + u32 参数 → 同分派;`(ret|2)!=2`(即 ret∉{0,2})→ assert `[TrackTask] dispatchFromSequence…`(行 0x69)。

---

## 6. 综合逻辑(合成)

### 6.1 搜索模式决策链

1. **XED(高置信)路径** `FUN_0030FA00`:
   - **Master**(主实例):`getMasterPattern` —— 先看 vtable+0x154/0x1B4 两个互斥条件(为 1 直接 ALL);`FUN_008921E0()==1`("out of lock on range",即目标跑出 lock-on 范围)→ **ALL**;未检出 → **ALL / ALL_ALIGN(q1==1)/ ALL_MARIO(q1==2)/ POTENTIAL(场景判别 sc==1 且已检出过)**;已检出 → **RELIABLE_SECOND(FUN_00891FE0()==2)或 RELIABLE(_ONLY) 家族**:XYZ 使能(FUN_008B92F8)决定带不带 XYZ,场景判别(FUN_008B9202)决定带不带 ONLY,q1(FUN_008B9298)==1 决定 ALIGN 变体，sub==4 走 vtable+0x190。
   - **Slave**(从实例):`transfer` —— 默认 **SLAVE_RELIABLE / SLAVE_RELIABLE_XYZ(xyz 使能)**;`FUN_00891FE0()==2` → **SLAVE_RELIABLE_SECOND**;sub==4 / 其他 → vtable+0x194/0x198;**AED 眼结果校验(FUN_0030F204)失败 → 强制回退 vtable+0x198 并清 flags[1]**。
2. **XHD(次级检测)路径** `FUN_0030FACC` → `XhdResolver.transNg`:状态机 {保持 prev → found(FoundEnable,只看 part3/4!)→ LH(LHEnable)} → 模式映射表(§2.10):跟踪对齐(1→XHD_TRACKING_ALIGN)、仅可靠区(2→XHD_RELIABLE_ONLY)、可靠+对齐(3→XHD_RELIABLE_ALL/XHD_RELIBLE_AF_ALIGN)、纵深层(4→5/0xB/0xC/10)、5→9、默认 XHD_ALL/XHD_AF_ALIGN/XHD_MARIO。
3. **ExecInfo 折算**(FUN_00310980/0031070C):packed pattern + xhd 标志字节 → out_mode {0,1,2} → 6×u16 Spec(多子模式取 max),供下游执行器消费。

### 6.2 区域生成链

1. ModePattern(0-25)→ `FUN_008AD028 getModeInfo5`:查 26×5 part-id 表(两套：手动/自动 × 常规/XHD 变体，由 `[GetTable]` base+0/+0xC/+0x18/+0x24/+0x30 选择)+ RAM 基矩形/子矩形表 → 填 5 个 0x6568B 槽(id、exec_mode/index、基矩形 + ≤3 个子矩形)。
2. `FUN_008B9E8A` 播放该模式的 **5 步 × 40B 扫视序列**(SHIFT 类运动的来源)。
3. SearchMode(0x00-0x17)选参数(getXxx 系列)→ generator 计算：
   - 尺度:`calcScalingRegion`(norm=size·zoom·level/640 → 级别 1-4 + min_size 64-120,中心按级别移位换算，ShiftRegion 收边)；
   - 旋转：RollAngle/RotateMode(0-10)映射 ±90/180;
   - 分辨率级间换算：SIZE_FB(纯移位)；
   - **Z 纵深**：getZVariableSearchParam(0x12-0x15 四份)+ XhdZAlignRegionGenerator(`size = max(base,alt)·ratio[idx]>>4` 方框)——对基准框按比例表逐级缩放，逐级(纵深假设)搜索；
   - XY 分区：isPicInXYSearchArea(per-part 值 2^40/10^4 定点 vs 阈值)决定分区类型 0-4;
   - XED 框平滑：XEFS(IoU+尺寸比门限 + [cur+down, cur+up] 接受窗口)。
4. `RegionProvider::getRegion` 汇总 → **Region_Param[32B]{res,id,cx,cy,w,h,…,ip,indx}** 数组(全零断言、`region_id` 日志、AED 数量不匹配告警)。

### 6.3 跟踪序列(TrackSequencer)

```
TrackTask.dispatch
  ├─ msg type 1 → dispatchFromDriver(state)──┐
  └─ msg type 0 → dispatchFromSequence(state)┤
                                             ▼
   track_sequence dispatch(state 0-9)
   0 execStartInit ──► 1 execEndInit ──► 2 execStartTrain ──► 3 execEndTrain
        ▲                (Init:STAPLE init_pos + staple_exec_mode)      │
        │                                                               ▼
        │            8 execBulkInitTrain(批量合并 Init+Train)   4 execStartDetection
        │                                                               │
        │        9 execBulkDetection(批量检测)      5 execEndDetection ◄─┘
        │                (取回 staple_pos[0..1],type)
        ├── 6 execCancel(取消)
        └── 7 execUpdateZpdResult(ZPD 结果更新)
   超时:sendStartInitTrain/startInitTrainTimer → type 7 定时器;
        FUN_008C5F6E 每帧比 elapsed>=timeout → 结果标记 tracking_elapsed_timeout(rec+0x30=1)
   重初始化:置信度矛盾(FUN_00314B7C/00314DF8 → 0)或 AED 结果不正确 → 走 StartInit 路径重建
```

置信度 → part 分配：head_conf 在 part1/2(head)间按状态与设置选择，xhd_confidence 矛盾时改发 `xhd_result_not_matched` 载荷;body 由 `slave_disable_body_set` 控制；每帧 `TkCon id/part/high` 把 {slot→part, high=(无超时)} 写入状态;`skip_request` 每 N 帧挂起新 Init 请求(节流)。

---

## 7. 关键结构体布局(实测偏移)

- **SearchResolver 槽(0x6568B)**:`+8/+9 u8`、`+10 s8 part_id(-1 无效)`、`+0x14 3×u32 基矩形`、子块 k(1..4)@`k*0x1958`:{使能 u8@+0/+1, 矩形 3×u32@+0xC}(绝对偏移 0x1964/0x32BC/0x4C14/0x6560,使能字节 0x32B0/0x4C08/0x6560);exec_mode@+0x6568(槽尾)。
- **Region_Param(32B)**:`u32 res@0, u32 id@4, s16 cx@8, s16 cy@0xA, s16 w@0xC, s16 h@0xE, s16 ?@0x10, u8 ip@0x1C, u8 indx@0x1D`。
- **请求记录(TrackTask 路径)**:小记录 0x88B{valid@0, sync_type@1, …, img_type 相关@尾部};大记录 0x248B{id u16@0x58, part u8@0x5A, payload@0x60}。
- **XED track 结果**：type@0,flags@0x30..0x33,part@0x60,f32 cx/cy/w/h@0xC8/0xCC/0xDC/0xE0,id@0x10C,part2@0x111,标志@0x130,附加 u32@0x184。
- **XHD track 结果**：id@0x24,pos@0x154,选中 idx@0x50,条目 idx×24B@+0x80 区，高置信@0xF8,id2@0x140,part@0x189,sel s8@0x270,条目 0x18B@0x1B0。
- **TkSeq SettingData(节选)**：unit[3]@+0x1504(stride 0x48),init_type@+0x1454,init_pos@+0x1464/0x1466,exec 标志@+0x1858,+0x160C/+0x16FC。

---

## 8. 与既有报告的衔接

- `REPORT_adam_sequencer_subject_eye_staple.md` 中的 ADAM 定序器是本层(FC::Keypoint)的下游消费者：此处产出的 Region_Param / XED/XHD 结果即其输入；STAPLE 两单元位置在 `execEndDetection` 汇出。
- 日志宏:`FUN_002BF488(level,?,line,file,fmt,…)`(INFO),`FUN_002BF360(line,file,fmt,…)`(ERROR,后随 FUN_008501D4/FUN_00294E08 = abort),`FUN_00282508(file,line,func)`(FC_ASSERT),`FUN_0085312E`(与 002BF488 同级的条件日志)。`FUN_002CA064/002CA0D8` = 作用域跟踪构造/析构(成员含使能字节 +0x128、行缓冲、游标；配合 `FUN_00851CB6()==1` 即 `(DAT_01738B3D&3)>>1` 全局详细跟踪开关)。

---

## 9. 不确定项(无证据不结论)

1. **Master/Slave 的最终定义**：证据仅支持“Master=getMasterPattern 的 XED 主实例，Slave=SLAVE_* 模式的从实例(与 body/次级目标绑定)”；两者由 `FUN_0030EAEC` 的 `vtable+0x1B0` 谓词区分，该虚函数具体返回什么(isSlave/isSecondary/isBodyTrack)无字符串佐证。FUN_0030FA00/FUN_0030FACC 在反编译输出中无直接调用点(经 vtable)。
2. **FUN_008B9298 / FUN_008B9202 的物理含义**：分别确定 ALIGN 变体/ALL_MARIO(值 1/2)与 RELIABLE_ONLY 族(非 0);FUN_008B9202 内部比较的两个全局 vtable getter(+0x48/+0x4C,0x15=21 的场景码)未命名。
3. **FUN_00851CB6 = `(DAT_01738B3D&3)>>1`** 同时充当“作用域跟踪开关”与 getMasterPattern 未检出分支的模式选择(1→ALL_ALIGN,==2 分支因取值域仅 {0,1} 应为死代码)；两用是否真实(而非反编译伪影)存疑。
4. **XHD pattern 9-12** 有值无名(名字表只有 9 项)；它们对应 state 4/5 的输出，具体行为未知。
5. **RAM 表内容**:0x1489360/0x148A5A8/0x1726448/0x148ABC0(per-mode 基矩形/子矩形)与 0x19Bxxxx 缓冲在固件文件之外(BSS/堆)，静态不可恢复；其初始化代码不在 cpapp 静态引用内(可能由驱动填充)。
6. **XhdTrackingAlignParam 字段命名**:−80、2、16、32、2 等常数为实测存储值，字段名(偏移量/阈值/步数)不可恢复。
7. **isPicInXYSearchArea 的 type 0-4 分区表**：Ghidra 跳表展平，每个 type 的真值不可恢复(仅知 type!=0 需命中某 part)。
8. **AllSearch BuilderType 0-3 四个构建器**的差异(四个 vtable 0x11E8C48 等)未逐一展开。
9. **isOverOptionInterrupt(ed) 的真实实现**：只有非法枚举桩;“选项中断”的确切触发条件未知。
10. **超时数值**:FUN_008C5F6E 的 timeout 来自对象(TrackController 内)的两个 getter(+0x24 / +0x1E8,由 vtable+0x1C4 标志选择)，具体秒数/帧数为运行期配置，静态未见常数。
11. **FUN_0030DBD4 case 0x02/0x03 的 assert**:builder 不支持这两个 SearchMode,但 getAllSearchParam 断言要求 SearchMode==2 —— 两条路径属于不同对象(builder vs 参数 getter),SearchMode 0x02 的实际使用者未定位。
12. **FUN_0089236C**:确认为"在 ctx+0x4C 链表中按 id 查找已跟踪目标"型操作，但返回值参与置信度裁决的精确含义(存在 vs 冲突)只有行为证据。
13. **FUN_0031005C 的 5-float 组**与 FUN_008BA496 的 6-u16 Spec:两者都按“子模式”从全局 provider 的 vtable 取值，provider 派生类的表在运行期，静态无名。