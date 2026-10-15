# REPORT_interchip_protocol.md — AP↔CP 芯片间协议全栈（Block B 第七项，2026-10-11）

> 数据源：re_assets kmod 符号表（icdt.ko/pci_ep_cp.ko/mcmn_drv.ko/pcie-if.ko/pcieatu.ko）、
> 新反编译 a1m2_interchip.c / a1m2_icdt.c / a1m2_pci_ep_cp.c、kernel_symbols/a1m2_kallsyms.txt。

## 一、协议栈分层（全实证）

```
[CP 侧 cpapp (TOMCO RTOS)]                [AP 侧 Linux]
  FC::Keypoint result_sender ──┐            appFw/avcam (用户态)
  AdamDriver (0x1700/0x210)    │              ↓ osal_* 消息
                               ▼            libInfraInterchipDatatrans.so (8KB 桩)
        ═══ UDIF 总线 (内核态, 两端同构) ═══
  udif_platform / udif_device / udif_driver 框架 + 7 种传输后端
  ├─ udif_pcie / udif_pcidma  ← pci_ep_cp.ko (udif_pci_ep_cp 驱动实例, PCIe EP)
  ├─ udif_gpio / udif_ddrc / udif_fusb_otg / udif_hwtimer / udif_wdt (其它通道)
  icdt.ko = interchip_transfer_async 内核 API + proc + cache_ctrl
  mcmn_drv.ko / pcie-if.ko / pcieatu.ko = PCIe ATU/链路管理
```

## 二、关键事实

1. **UDIF = 内核内建的芯片间通信框架**（vmlinux kallsyms 193 个 udif_* 符号）：
   platform_register / driver_register / 设备模型 / kmalloc 池 / proc 接口，传输后端
   `__boottime___udif_init_{gpio,pcidma,udif_ddrc,fusb_otg,hwtimer,pcie,wdt}`。
   **PCIe 只是其中一种后端**——还有 GPIO/DDR 控制器/USB-OTG/HW 定时器/看门狗通道
   （对应 HARDWARE_ARCHITECTURE.md 的 5×PCIe + 其它物理互联）。
2. **用户态桩 libInfraInterchipDatatrans.so（8KB，两台 MD5 相同）**：
   - `interchip_transfer_async(msg)`：osal_valloc_msg_wait(邮箱 0x2820746) → 拷贝
     5×u64 {回调fn, arg0, arg1, w2, 0x30} → osal_snd_sync_msg；返回 puVar2[5]（结果码 5=失败）。
   - 接收线程 `icdt_u_rcv`（osal_create_waitable_thread，优先级 0x7f/栈 0x282）：
     `osal_rcv_msg_tmo(0x282078f)` 循环 → `fn(arg0, arg1)` 回调 → osal_free_msg。
   - 即：**用户态 interchip = OSAL 邮箱回调分发器，真正的跨芯片传输在内核 UDIF**。
3. **icdt.ko（54 函数）**：内核 API `interchip_transfer_async`、`logrec/cpp_logrec`、
   measure_start/measure_end（传输耗时测量）、`__udif_cache_ctrl`（DMA 缓存维护）、
   `__udif_kmalloc/kfree`（UDIF 内存池）、proc 接口 icdt_proc_{init,exit}。
4. **pci_ep_cp.ko**：极薄（udif_pci_ep_cp 设备实例 + init/cleanup）——PCIe EP 传输的
   UDIF 驱动注册。
5. **消息 ID 族（0x170B/0x210/0x1700 等）**：产生/消费在两端应用层（cpapp 的 FC/AdamDriver
   ↔ AP 的 avcam/appFw），UDIF 层不解析（含 cache_ctrl/拷贝/回调分发）。
   → **协议兼容性结论**：两台相机 libInfraInterchipDatatrans.so 逐字节相同 + UDIF 为
   同版本内核内建 ⇒ 应用层消息 ID 即兼容性契约；换 cpapp 固件时的协议风险在应用层
   消息版本而非传输层。
6. **消息 ID 全表**（0x1700 资源请求/0x210 STAPLE 应答/0x170B 主体结果……）待 Block C
   avcam/appFw 侧接收 handler 枚举后成表（接收端分发 switch 在 avcam）。

## 二点五、消息 ID/服务端口首表（Block C-1，2026-10-11 深夜，a1m2_appfw.c 98420 函数就绪后）

**★名称修正★："0x170B 主体结果"系误名**——0x170B 从头到尾都是 **0x170 字节 Buffer** 的简称
（result_sender 的 FC 消息缓冲大小）；主体结果包是 FC 队列上的 type 9/10 消息（AF_LOGIC §十）。
"0x1700 资源请求/0x210 STAPLE 应答"经本次反编译验证为真。

**FC 消息队列 0x90060197（CP 内，fc_lib_message.cpp 池/队列同一 ID）消息类型表（u16 首字段）**：

| type | 发送方（cpapp） | 含义 |
|---|---|---|
| 9/10 | process/post/result_sender.cpp FUN_0089a694 | **主体结果包**（0x170B buf，帧号+le/re/head/body 四组 id 对+QVGA 矩形） |
| 0x1700 | adam_process_manager.cpp | **Adam 资源请求** {0x1700, resource_id(DAT_011e8bcc), u32 param}（pose track 等） |
| 0x210 | fc_drv_staple.cpp ProcessStaple::api_sendMessage | **STAPLE 消息/应答**（+resource/+0x1e8/+0xf8 字段族） |
| 0xc80 | fc_api_callback.cpp（AdamProcessManager::AllocMessage 路径） | 8B {0xc80, handle} |
| 0xd80 | fc_feature_scalara_oneshot.cpp | {0xd80, param} oneshot 请求 |
| （完成端口对） | SendCompMsg/WaitCompMsg FUN_002bf008/002bf0b4 | 同步完成通知，同队列复用 |

**UIPC 服务端口/队列（osal_snd_msg/osal_snd_sync_direct 地址面）**：

| 地址 | 侧 | 身份（证据） |
|---|---|---|
| 0x90060197 | CP | FC 消息队列（上表宿主；池 ID=队列 ID） |
| 0x910040 | CP 服务 | **UTIMER**（appFw FUN_017832a0 handler 日志 "[UTIMER]ERR! Recv Unknwon UIPC Msg"；osal_snd_sync_direct(0x910040) 建链） |
| 0x910041 / 0x910042 | CP 服务 | avcam 重度使用（163/102 次）——codec/显示族服务（具体分派待下一批） |
| 0x80870935 | AP 队列 | **ADJ 工厂调整服务**（appFw FUN_01795624，"Adjust Command error!! ( command=0x%04x )"，DMM 4MB mmap /dev/mem） |
| 0x8087094e | AP 队列 | 文本调试台（appFw FUN_01796274，"set"/"exe" 命令，"not support : %s"） |
| 0x8057060a | AP 队列 | avcam HIF_Codec（imola2 编解码器控制，{0x2003,id,size,seq} 帧格式） |
| 0x805700f9/0x806800f3/0x806c00fc/0x80c2019f/0x8068xxxx 族 | AP 队列 | avcam 族（分派未枚举，下一批） |

appFw.so 导入面（nm -D 实证）：interchip_transfer_async + osal_{snd_msg,rcv_msg_tmo,
reg_msg_queue_cb,reg_sync_msg_queue_cb,snd_sync_direct,get_msg_src,...} 全经 libInfraSKD.so。
**avcam=编解码守护（imola2/SFMC/BGM），主体结果消费方不在 avcam**（原 B7 报告"接收端分发
switch 在 avcam"作废）——AP 侧消费在 appFw 的队列回调族（0x8087xxxx 已定位两个），全表下一批续。

## 二点六、AP 队列分派全表（Block C-3，2026-10-12 凌晨）

> 数据源：a1m2_avcam.c（av-cam 全量 47198→本文件）+ a1m2_appfw.c。★avcam 的 0x8068/0x8057
> 族分派枢纽已定位到函数级，原"分派未枚举"清空★。

### 6.1 avcam 接收架构（mcTsk.cpp / mcMsgIf.cpp，全实证）

```
avcam 内部 4 个"相机对象"任务槽（FUN_ffffffc0010a4398/0a4444/0a44e0/0a457c，槽 0-3，
  各自 FUN_ffffffc0010a5bb0(env,slot)+FUN_ffffffc0010a6b70(slot) 取上下文）
  └─ 每槽任务体 FUN_ffffffc0010a461c：recv 循环（FUN_ffffffc001097240 等待）
       消息拷 0x180B 到 ctx+0x1a8 → FUN_ffffffc0010a1ef4(分派枢纽, ctx+0x328 处
       8 槽模块表, msg, 源地址) 无限循环
```

**mcMsgIf 分派枢纽 FUN_ffffffc0010a1ef4（295 行，双重分派 = 源地址 × 消息首字）**：

| 源地址（param_4） | 分派 |
|---|---|
| 0x61003c / 0x9061003c | **内存共享通知**：word0 0x8021=share_async / 0x8023=free_async（dma-buf 式共享/释放，word1=ref/err，+6=cookie），异常打 "received_unexpected" |
| 0x7302f0 | DMA 消息（"MCMSGIF: received_dma_msg"，仅日志） |
| **0x80c2019f** | 四路扇出：param_1[3]/[4]/[5]/[2] 模块依次处理 |
| 0xc20219 | 同上（与 0x80c2019f 同分支，两个独立地址） |
| 0xd2fc0991 | 单路 → param_1[3] |
| 0x8057026d | codec 诊断消息（"received_codec_diag_msg"，仅日志） |
| 0x80570529 | 数据传输长包（"received_data_trans_lo…"，仅日志） |
| 0x818c04d5 | **HW 版本查询**：校验 +0x11 处 16B 版本串，回 {0x8003,0x8501,0x34,1} |
| 0x810b0768 | 0x2003/0x200d 路径上的特例（跳过 subtype 过滤） |
| （其它） | 落到消息首字分派 ↓ |

| 消息首字（word0，u16@msg+0） | 协议类 | 分派 |
|---|---|---|
| **0x1000** | 通用同步 RPC | FUN_ffffffc0010a2a44（应答码 0x102 路径）→ 对象指针修正后 FUN_ffffffc0010a95bc/0a2a74 |
| **0x2003** | codec（imola2） | word1 0x1303=错误通知(mcMsgErrorSender)；word1 0x201=**ExecMsg**（+8 处对象指针按 4 项范围表 DAT_…346ec8 修尖，+0x16==0x210 且 [5]==0 时清 +0x67 标志）→ FUN_ffffffc0010a95ac；word1 0x10c-0x10e→FUN_…1b854c(param_1[6])；0x10f-0x111→FUN_…1b3044(param_1[7]) |
| **0x200d** | codec 事件 | 默认扇出尾：FUN_…12d590([3])+FUN_…10cfe1c([5])+FUN_…0b9c04([2]) |
| **0x2103** | **六路广播** | [7]/[5]/[6]/[3]/[4]/[2] 全部模块依次处理 |
| **0x8003** | 系统查询 | word1 0x501=GET_HW_VERSION（存版本，回 0x8003/0x8501 帧） |
| 0x8021/0x8023 | 共享/释放异步 | 仅在 0x61003c 源下识别（见上） |

消息布局（codec 族）：`{u16 word0=协议类, u16 word1=消息 id, u32..., +8=对象指针, +0x16=u16 标志, payload}`；
msg 缓冲固定 0x180B/条。**0x2003 的 {magic,id,size,seq} 旧注记修正：word0=协议类而非"帧 magic"**。

**TSK_V_DNC（task_resource_dec_video.cpp）视频解码任务独立分派 FUN_ffffffc0012a74f4**
（消息布局不同：u16 type@msg+2，payload@+8；经 FUN_ffffffc00102f014 动态注册同步队列回调）：

| type | handler 职能（RcvINF 日志串实证） |
|---|---|
| 0x200 | INF_VIDEO_DEC_OPEN（channel_id/ip/sa_usecase） |
| 0x201 | INF_VIDEO_DEC_START（augi_buff_addr/index_num/picture_info_buff） |
| 0x202 | INF_VIDEO_DEC_CLOSE（power_save） |
| 0x203 | INF_VIDEO_DEC_STOP（vfc） |
| 0x204 | INF_VIDEO_DEC_CHANGE_SPEED（update_interval_vfc） |
| 0x207 | INF_VIDEO_DEC_RESET |
| 0x21a | INF_VIDEO_DEC_IMOLA_CREATE_CHANNEL |
| 0x21b | INF_VIDEO_DEC_IMOLA_REMOVE_CHANNEL |
| 0x221 | INF_VIDEO_DEC_IMOLA_FATAL_ERROR |

### 6.2 mcObjectCtrl.cpp 4 槽 × 18 地址路由表（FUN_ffffffc0010a65dc 构造，槽 0-3 实录）

| # | 槽0 | 槽1 | 槽2 | 槽3 |
|---|---|---|---|---|
| 1 | 0x805700f9 | 0x805720f9 | **0x8057060a**(HIF) | 0x8057071f |
| 2 | 0x805700fa | 0x805720fa | 0x805700fa | 0x805700fa |
| 3 | 0x805702db | 0x805722db | 0x805702db | 0x805702db |
| 4 | 0x80570254 | 同槽0 | 同槽0 | 同槽0 |
| 5 | 0x80570271 | 0x80572271 | 0x80570271 | 0x80570271 |
| 6 | 0x806800f3 | 同 | 同 | 同 |
| 7 | 0x806800f5 | 同 | 同 | 同 |
| 8 | 0x8068015f | 同 | 同 | 同 |
| 9 | 0x806c00fc | 同 | 同 | 同 |
| 10 | 0x805702f8 | 0x805722f8 | 0x805702f8 | 0x805702f8 |
| 11 | 0x90b201aa | 同 | 同 | 同 |
| 12 | 0x80680113 | 同 | 同 | 同 |
| 13 | 0x8057010d | 0x8057210d | 0x8057010d | 0x8057010d |
| 14 | 0x8057010e | 0x8057210e | 0x8057010e | 0x8057010e |
| 15-18 | 0x805704d7-d8-d9-da | 0x805724d7-da | 同槽0 | 同槽0 |
| 尾 | 0x819c0506 + 小 id 0x1e,0x20,1,2,3,9,10,4,6,8,0x13,0x14,0,0,1 | 同左 | 同左 | 同左 |

**地址编码规律（实证）**：`0x8057_0XY9` 族低半字含**通道 nibble**（槽1 全表 = 槽0 表把
b13 位点亮：00f9→20f9/04d7→24d7）；槽 2/3 仅第 1 项换成各自 codec HIF 端点
（0x8057060a=槽2 = C-1 已证的 imola2 codec HIF，0x8057071f=槽3）；
0x806800f3/f5/015f/0113、0x806c00fc、0x90b201aa、0x819c0506 为全槽共享端点。
SFMC still_enc（FUN_ffffffc0011b9bfc，"STLENC: cannot_send_msg"）实测向 0x806800f3 发送。
0x8068 族 = avcam 自身编解码面（自槽任务间+对外），0x8057 族 = 按通道的采集/编码服务端点。

### 6.3 appFw 注册/发送面（全量，stdlib osal 直连）

| 队列地址 | 回调 | 身份（断言串实证） |
|---|---|---|
| 0x910040（UTIMER，sync 端口） | FUN_017832a0 | `App::start_utimer()`（000_main/app.cpp）：先 snd_sync_direct(0x910040) 握手拿队列句柄，再 reg_msg_queue_cb——**服务地址→动态队列句柄两段式** |
| 0x80870935 | FUN_01795624 | ADJ 工厂调整（C-1 已证） |
| 0x8087094e | FUN_01796274 | 文本调试台（C-1 已证） |
| **0x1050244** | FUN_01796c14 | **adjust::senser_cb**（000_main/adjust/senser.cpp；`*msg==0x20000002 && msg[5]==' '` 特判改写后转发 FUN_01796aac） |
| **0x2170625** | FUN_01796ce0 | **adjust::senser::biz_senser_cb**（{u8 type=1→回 8, +2 u16, +4 u32 size, payload ≤0x124}，等条件变量同步回包） |

appFw osal_snd_msg 目标：0x9088076b(×2)/0x61003c(×2)/0x8280074d/0x92900778；snd_sync_msg
0x8f013a；snd_sync_direct 0x910040/0x910042。0x1050244/0x2170625 = senser 通道的 AP 侧
接收端（与项目已知"senser 工厂调整通道"闭环）。

### 6.4 主体结果（type 9/10）无 AP 侧消费者 ★C-1 残留误判清正★

appFw+avcam 全量扫描：**无任何 0x90060197/FC 队列地址、无 9/10 型分派、无 FW:/LiroSeq 命中**。
结合 AF_LOGIC §十三"0x170B 结果包不离开 CP"+B2 投递链（result_sender→FC 队列→FW AF 序列
全在 CP），本扫描为**"CP 内闭环"的第三重独立实证**：主体结果经 CP 内 osal 队列
（0x90060197/UIPC 0x0197）直接进 CP 驻留的 FW AF 序列（LiroSeq），从不越过 UDIF。
C-1 原句"主体结果消费方在 appFw 队列回调族（0x8087xxxx 已定位两个）"作废——那两个回调
实为 ADJ/调试台（见 6.3），与主体结果无关。AP 侧真正跨芯片消费的只有 codec/显示族
（0x1000 RPC/0x2003/0x2103/0x8003，见 6.1）。

- A7C2 式"解密→改→写回"路径中，AP 侧（appFw/avcam/kmod/vmlinux）与 CP 侧（cpapp）可
  **独立替换**，UDIF 传输层无需动。
- 若只替换 CP 的 cpapp-b.bin（带 AI 栈），必须保证：应用层消息 ID 集合与 AP 侧版本一致
  （0x170B 发送方在 CP、接收方在 AP avcam）——α1 II 的 cpapp 对 α1 的 avcam 发新消息 ID
  时 AP 端会丢包/忽略（具体行为待 avcam 接收路径确认）。
