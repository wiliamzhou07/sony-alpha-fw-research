# REPORT_no_adam_feasibility.md — "α1 → 无 Adam 管线的 α1 II" 四项验证（2026-10-12）

> 用户问题：α1 能否改造成"没有 Adam 管线的 α1 II"（路线甲 = α1 II cpapp 整体上机 + Adam
> 打桩；路线乙 = α1 cpapp 为底定向嫁接）。本报告 = 四项离线验证结果 + 打桩工作量清单。
> 结论先行：**四项全部给出有利答案，路线甲的可行性显著高于此前估计**——因为 α1 II 的
> cpapp 自带完整的"Adam 缺席"降级设计。

## 验证 1：Aed2 引擎活/死判定 → ★活代码，且是双引擎可选架构★

**证据链**（a1m2_cpapp）：
- 懒加载单例 ×2：Aed2（FUN_00284f44 构造，字典 `/usr/sabin/aed2_dic1/2_bin` + s2f 表）；
  **Aed 一代（FUN_00284894 构造，字典 `/usr/sabin/aed_dic1/2_bin` = α1 原生同款）**
- **双引擎选择器**：`common/driver/keypoint_driver.cpp` FUN_008897ba/FUN_008897ba：
  配置对象（0x143ebe8，tuning 单例）vtable+0xdc 查询 **==1 → Aed2，否则 → Aed 一代**，
  选中的实例写 ctx+0xc
- 两个构造器都把字典路径存 +0x28/+0x2a —— 引擎按需装载字典，α1 II 固件树两套字典都在
- **Adam 的角色 = 提案源不是检测器**：`[AED] StartAdamSetInitialRegion` 是 CP 把检测区域
  发给 Adam；眼部检测执行器是 MINNA Aed/Aed2（与 STAPLE/HumanCross 同层）

**判定**：AED 眼检测在 a1m2 cpapp 中无 Adam 也能跑（Aed 一代 = α1 现役引擎）。打桩点不在
检测器，在**提案供给**（见清单 #3）。

## 验证 2：interchip 消息面 diff → ★传输/协议类同集，差异集中在 PID/NID 注册面★

- 传输层：UDIF 内核核心四件（icdt/mcmn_drv/osal_uipc/osal_ulogio）**.text 逐字节一致**
  （并行会话 kmod 双级普查实证）；FC 消息队列 0x90060197 两台都有（a1=7 处/a1m2=8 处引用）
- 协议类常量两台同集：0x2003(a1=11/a1m2=13)、0x200d(199/201)、0x8003(6/4)；
  0x2103 广播仅 AP 侧；result_sender.cpp 两台都有（a1m2 增 copyRawAnimalDataQVGA 动物载荷）
- **真实差异面 = 并行会话的 PID/NID 差分**（a1_appfw_pid_nid_diff.tsv）：
  仅 a1m2 45 条（其中 **A 级 12 条 AI 对焦族必须补**）、**NID 0x20a4-0x20ae 族 13 条重编号
  冲突**（换 cpapp 必须做 ID 映射层）、未定位源端点 0xd2fc0991 一枚
- avcam 接收契约跨代稳定（mcMsgIf 双重分派逐分支同构，REPORT_interchip_protocol.md §二点六）

**判定**：换 cpapp 不需要动传输层；需要 PID 映射层 + α1 appFw 补 A 级 12 族注册。

## 验证 3：XHD 恒空时的降级路径 → ★优雅降级，无死循环风险★

**置信度仲裁**（track_setting.cpp FUN_00314df8，三值 {0=矛盾推翻,1=高,2=弱}）：
- **XHD 有效但 id 与跟踪链表矛盾 → return 0**（FUN_0089236c 查 id 成员）
- **XHD 无结果（bVar1=false, param_2=0）→ 恒为 1 或 2**（按 XED 侧标志 +0xf8/param_3），
  **永不为 0** → 不会触发"confidence==0 → StartInit 重初始化"死循环
- XHD 有效但 tracking 中矛盾（param_2==1 且无 XHD）→ 错误日志（非致命，继续）+ 2
- 佐证：FoundStatus=(aed==3)?2:(stpl==2)?3:(aed==1)?1:0 **不含 XHD 项**；优先级部位表
  XHD 全败 → 回落 XED 分支（REPORT_priority_judgment 的表逻辑）

**功能退化（非崩溃）**：HumanCross 的 HB/BB 判定用 XHD 头/躯干框——无 XHD 后 HH（头-头）
仍可判，HB/BB 失效；27 关键点/骨架显示消失；XhdResolver 模式回落 XED/ALL 族。

## 验证 4：beta/focal 来源 → ★CP 从硬件 df+镜头校准换算，无 Adam 不死★

- **β 产生于 CP**：`adam_recognition_param_generator.cpp` FUN_002d38f0 ——
  FUN_002d5bdc 取 **df**（ZPD→DFE 硬件链，REPORT_cp_fw_pdaf_defocus.md）→
  FUN_00aaa0ea 查**镜头数据结构**（+0x128..+0x1b4 校准字段）做 df→β 换算 →
  BetaSmoother（FC::Keypoint::BetaSmoother RTTI）平滑 → "smoothed beta" →
  **作为参数发给 Adam**，Adam 结果环原样带回——Adam 只是 β 的中继，不是计算者
- **α1 原生就有 β**：a1_cpapp 字符串 `beta. high:%d low:%d` / `drop by beta:%d(%d)` 与
  a1m2 逐字相同；α1 差异 = 无 ConvertBeta8_24toDistance32（β→距离 32 换算，a1m2 新增，
  用于 tracklet 距离校验）——属"回移植一个函数"而非障碍
- **XYZ 纵深搜索输入存活**：β/df 来自硬件散焦链 + 镜头数据，Adam 缺席不影响

## 路线甲打桩工作量清单（按依赖序）

| # | 项 | 工作量 | 依据 |
|---|---|---|---|
| 1 | Adam BOOT fail-soft | **≈0（原生）** | BOOT_RDY_timeout→log→return（FUN_00152f24），状态 4/5 继续；bounded 等待 |
| 2 | Adam 结果缺失 | **≈0（原生）** | 序列节点超时 [0x17]=0x14 有界；XED/XHD 空 → 置信度 1/2（验证 3） |
| 3 | **提案源切换 Adam→IDT** | **核心工作量** | StartAdamSetInitialRegion 无应答 → 无检测区域。a1m2 cpapp 内 IDT 栈完整（NSX::Face 消息驱动+FDT 中断，REPORT_staple_reid_faceid §四），需确认/接通 IDT→FC 提案路径（α1 的 cpapp 本来就是这条路径，可对照 a1_cpapp 移植接线） |
| 4 | AED 引擎选择 | 小 | tuning 配置 vtable+0xdc ==1 选 Aed2（或 0 选 α1 原生 Aed 一代），两套字典都可搬 |
| 5 | PID/NID 映射层 | 中 | 13 条 NID 重编号冲突映射 + α1 appFw 补 A 级 12 族（DETECTION_SETTING/GET_DISPLAY_POSITION/FOLLOW_FOCUS 等，并行会话已分级） |
| 6 | 文件搬运 | 小 | cpapp-b.bin(a1m2 版)+aed2_dic(或 aed_dic)+scd_dic1/2/3+sabin 更新；libAiDictionary.so 按需 |
| 7 | tomco.txt | **≈0** | 无 Adam → 不需要 192MB AI carve-out，α1 内存图原样 |
| 8 | backup 机型码 | 待验证 | CX885xx vs CX899xx 是否被 CP 校验（写回前测） |
| 9 | 交付机制 | **共同前置** | rp2040 bootrom 串口引导 → eMMC 写入（签名墙不拦此路）+ 机身 CRC 校验点测绘（Block D4） |

**总评**：核心打桩只剩 #3（提案源切换）与 #5（PID 映射层），其余要么原生 fail-soft、要么
文件搬运。相比"完整 a1 II 移植"，路线甲避开了 ADAM 存在性/CP 内存/40MB 模型三大未知，
代价是失去姿态估计 AF（招牌功能）。产物 = Scd 分类引擎 + HumanCross/多人仲裁 + 新搜索
模式框架 + β/df 深度参与的 AF——"α1 II 的决策逻辑"。

## 遗留

1. #3 的深挖：a1m2 cpapp 里 IDT→FC 提案接线现状（FUN_0027d5dc 族到 KeypointDriver 的
   region 流）——决定 #3 是"接开关"还是"写胶水"。
2. 0x143ebe8 tuning 单例的 vtable+0xdc 默认值（BSS，运行时填充）——若可由 tuning 数据
   控制，#4 免打桩。
3. AdamSalvage 子系统在"boot 失败"后是否还会周期性重试上电（GPIO 抖动风险）。
4. backup 机型码校验（#8）。
