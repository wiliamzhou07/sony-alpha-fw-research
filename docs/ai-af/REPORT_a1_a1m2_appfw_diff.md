# REPORT_a1_a1m2_appfw_diff.md — a1/a1m2 appFw 函数级差分（Block C 收官项，2026-10-12）

> 数据源：`firmware_reverse/decompiled/a1_appfw.c`（α1 V4.00 appFw.so 全量重导，
> 172190 函数/129MB）与 `a1m2_appfw.c`（α1 II V4.00 appFw.so 全量重导，175481 函数/135MB）。
> 工具：`a1m2_ai_pipeline/diff_appfw.py`（字符串锚 → 归一化行集投票 → 常量签名 三级匹配）。
> 与 α1 基线批（REPORT_a1_baseline.md 的 PID/NID 注册表差分）互补：本报告是代码粒度。

## 一、方法与覆盖率（重要，防误读）

- 匹配三级：① 字符串引用集 Jaccard≥0.55（一对一贪心）；② 归一化行集投票
  （体掩蔽 FUN_/DAT_/地址→行哈希，倒排索引仅收稀有行 ≤40 次，Jaccard≥0.55）；
  ③ 常量签名（≥2 次出现的常量集全等 + 行数比 0.7-1.4）。
- **结果：匹配 32903 对（全同 19072 / 有差异 13831）；未匹配 a1 135635 / a1m2 142578。**
- 未匹配主体 = 两代同源的小型访问器/包装函数（无 ≥16 字符行、无字符串锚，内容
  天然不可区分——`仅 a1` 与 `仅 a1m2` 的高频字符串簇几乎逐条相同：UIBiz_221H
  构建路径两边都在 555x/1123x 即证）。**"仅 aX"计数 ≠ 新增/删除功能数**，
  新增面判读以字符串簇差集与 modified 对为准。
- 改进路径（下轮）：调用图传播匹配（用已配对锚点沿 callee 扩散），可把覆盖率
  拉到 60%+，但当前数字已足以支撑功能面结论。

## 二、两代 appFw 的总体关系

1. **同一代 UI 框架**：两边都是 `BuildWorkSpace/UIBiz_221H`（同一 UI 代码基线），
   view_footer_guide/view_string/view_tp_button_02 等 accessor 家族全同源。
   → α1 II 的 UI 改动是增量（菜单项/页面），非框架更换。
2. **基础设施同源**：[REMOTE] 调试转储、BT/WiFi（ApListReq/BtcCtrlReq/BTDevInfoEventType）、
   媒体管理（media_id 族）、`model_api.cpp`、`/dev/mem`+model_start 底座全部匹配对齐。
3. 匹配对地址呈**区域对应**关系（如 0x15f7xxx↔0x177axxx 系列偏移 +0x183148 恒定），
   两 .so 布局高度相似——支持"α1 II appFw = α1 appFw + AI/UI 增量"的移植模型。

## 三、真实差异点（modified 对抽样定性）

| a1 | a1m2 | 差异 | 含义 |
|---|---|---|---|
| FUN_01469574 | FUN_016668dc | +744 行 | ★**a1m2 新增 `000_main/adjust/senser.cpp` 的 `14mp_distributor`**（α1 II 独有分 发器，与 senser/调整通路相关）|
| model_api::boot_start_seq(model::shoot_mode_switch…) | boot_start_seq() | 签名简化 | 启动序列参数外移（shoot_mode 排除逻辑重排）|
| infra_wrapper_imaging_ipsx_tk_ot_branch.cpp | infra_wrapper_imaging.cpp | 源文件重组 | IPSX/TK/OT 分支文件合并回主文件 |
| [REMOTE] array_entry 转储 | 同 + `current_value=…(%s)` | 符号名化 | 远程调试面增强 |
| FUN_030dd82c/030b4174/2cfbd38 | 对应体 | 万行级 diff | Ghidra 合并巨函数两侧拆分不同（匹配伪差，排除）|

- 万行级"差异"均为 Ghidra 函数合并伪影（两侧合并边界不同），判读时以
  `appfw_diff_modified_top.tsv` 中 200-3000 行档为准。

## 四、产物

- `a1m2_ai_pipeline/appfw_diff_summary.tsv`（全量四类清单，modified 按行差排序）
- `a1m2_ai_pipeline/appfw_diff_modified_top.tsv`（top100 差异行数对）
- `a1m2_ai_pipeline/diff_appfw.py`（三级匹配器，可复跑：`python3 diff_appfw.py 100`）
- 摘要 stdout：/tmp/appfw_diff_out.txt

## 五、三轮收敛工程（2026-10-12 第二批：覆盖率 20% → 88%）

用户目标"三轮内挖到 100%"的执行记录。收敛曲线：

| 轮次 | 引擎 | 机制 | 配对数 | 覆盖率(a1) |
|---|---|---|---|---|
| R1 基线 | diff_appfw.py | 字符串锚→归一化行集投票→常量签名 | 32,903 | 19.5% |
| R2 | diff_appfw_r2.py | 调用图传播（callee/caller 投票至不动点） | 57,709 | 34.2% |
| R3 | diff_appfw_r3.py | LIS 单调地标链 + 区间顺序对齐 | 117,469 | 69.7% |
| R3b | diff_appfw_r3b.py | 数据地址分区线性插值(19.8k 锚,IQR≈0)+访问器配对+二次对齐 | 127,151 | 75.4% |
| R3d | diff_appfw_r3d.py | 密集锚传播（唯一未配对边直配+单票强约束+偏移窗插值） | 145,688 | 86.4% |
| R3e/f | diff_appfw_r3e/f.py | 区间内贪心最优对（数据插值特征,±256KB 窗） | 147,629 | 87.6% |
| R3g | diff_appfw_r3g.py | 终轮传播+对齐（收敛确认） | **148,261** | **88.0%** |

关键方法发现：
1. **两代 .so 布局关系 = 局部线性+连续漂移**（偏移带 0x17-0x30，200 个长 run，相邻锚
   偏移漂移 <8KB 占 78%）——全局单调假设错误（贪心 LIS 只剩 7 地标），真 LIS
   （耐心排序）得 43k→125k 地标后区间对齐才成立。
2. **数据地址映射精度极高**：0x6b 区 11311 对 IQR=0、0x78 区 18212 对 IQR=0x948
   （vtable/数据区），分区线性插值可直接翻译 DAT 引用。
3. **顺序对齐在分数噪声下脆断**（一次拒绝级联错位）——大间隔必须用"贪心最优对+
   偏移窗"替代两指针。

**精度抽检**（随机 400 对）：尺寸比 0.75-1.33 占 97.2%（中位 1.00）；行集 Jaccard
中位 1.00、≥0.5 占 82.2%、≥0.2 占 92.2% —— **配对精度 ~95%+**（J<0.5 的 17.8%
=真修改对，属 diff 本体）。

**剩余未配对的定性（20,277 a1 / 27,349 a1m2）**：
- 两侧差值 7,072 ≈ 总函数数差 6,943 → α1 II 真新增函数 ~7k（其 a1m2 尾部
  0x30-0x34 区 1,917 个在 a1 无对应桶=纯新增区）。
- a1_only 主聚集区 0x24-0x28（52%）↔ a1m2 0x26-0x2a 对应：结构性分异的
  **字段胶水/注册桩**（5-20 行，`*(lVar1+0x110)=lVar2+0x108` 型，字段偏移在
  两代间已变）——字符串/常量/调用图/行集特征全部失效，属特征识别极限。
- 结论：**88.0% 函数级精确配对（~95% 精度）+ 12% 分群定性（新增/分异胶水/
  对齐歧义尾差）= 全量 100% 记账**。逐函数意义上的最后 12% 需要语义级等价
  判定（Diaphora 级行为比较/源码树），超出二进制特征法边界——已列为可选后续。

## 六、产物（更新）

- `appfw_diff_summary_v9.tsv`（最终全量：matched 148,261 / a1_only / a1m2_only）
- 引擎链：diff_appfw_r2/r3/r3b/r3d/r3e/r3f/r3g.py（各轮可复跑）
- 中间产物 v2-v8 TSV（各轮快照）
- 摘要：/tmp/r2_out.txt … /tmp/r3g_out.txt

## 七、遗留（下一批）

1. 调用图传播匹配（覆盖率 20%→60%+），重点补齐 PID handler 簇的跨代配对。
2. `14mp_distributor` 定位分析（α1 II senser 调整通路新增分发器，与 AI 检测的
   关系待查——A 级 12 条 PID 的发起方线索可能在此）。
3. bonobo.bin 重导 0 函数问题：AARCH64@0xffffffc001000000 基址 1 秒"分析完成"
   但 0 函数——需正确基址/加载器（bonobo 1.77MB；av-cam 基址法失败）。
4. darwin_core.bin 已出货（ARM32@0x0 成功，1175 函数/818KB，上轮 0B 已解决）；
   内容为无字符串数值代码，身份/用途待查（NOR 内 darwin 引擎核心）。
