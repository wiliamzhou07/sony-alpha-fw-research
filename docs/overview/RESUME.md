# 任务恢复手册（2026-08-28 挂起时点）

> 目标：解包 BODYDATA.DAT（α1 II Ver.4.00，1.19GB）与 BODYDATA (1).DAT（α1 Ver.4.00，798MB），
> 对比 α1 与 α1 II 硬件差异。主路径 = 从 α1 相机提取 gen5 AES 密钥 → 本机解包。

## ✅ 已完成（全部到位）
1. **固件解析**：UFU/FDAT 容器解码、头部完全解析（model/version/USB 描述符/分区表）、
   DEND CRC 验证通过（两文件均官方原始）。
   - 工具：`<workspace>/unpack_ufu.py`（inspect ✓ / unpack ✓ 彩排通过）
   - 密钥提取：`extract_key.py`（从二进制扫 16/24/32B 常量 + ustaR@257 黄金判据，彩排通过）
   - 结论：gen5 密钥为真随机秘密（306+ 派生候选全部排除；判据修正后已重测），必须从相机侧获取。
2. **密钥提取平台（虚拟机）已 100% 就绪**：
   - VM：`~/Virtual Machines.localized/pmca-a2.vmwarevm/`（Ubuntu 24.04 aarch64，正式安装完成，
     磁盘 pmca-a2-disk1.vmdk 3.4GB）
   - SSH：`ssh -i ~/pmca-a1/id_ed25519 ubuntu@192.168.166.129`
     （⚠️ .130 是手工静态 IP，仅运行时有效；若虚拟机重启过：`cat /var/db/vmware/vmnet-dhcpd-vmnet8.leases | grep -A5 pmca-a1`
     找新 IP；或让用户看 `ip a`）
   - 已装：git/curl/python3.12-venv/pip/libusb + `~/pmca/Sony-PMCA-RE` + `~/pmca-venv`；
     自检 `PMCA_READY` 标记在 `~/pmca/ready.flag`
   - 网络：guest 直连 NAT 不通（vmnet8 宿主接口缺失）。**外网走宿主机代理隧道**：
     - 宿主代理：`python3 ~/pmca-a1/proxy.py 8888`（HTTP CONNECT+转发，勿在 guest 内直连 8888）
     - 隧道：`ssh -R 8888:127.0.0.1:8888 -N ubuntu@192.168.166.129`（需重登时重开）
     - guest 内 apt 已配 `/etc/apt/apt.conf.d/99proxy`；pip 用
       `--proxy http://127.0.0.1:8888 -i https://pypi.tuna.tsinghua.edu.cn/simple`
3. **相机侧资料**（证据链）：同代 FX3/α7IV/α7C2 服务模式已实测可用（PMCA #504、#582、#459）；
   senser 流程 = `serviceshell` 远程切换，非按键进入；红名单（push/tweak/bk w/...）见手册。

## ⏳ 待办（相机到场后）
1. 相机：MENU → 设置 → USB 连接 → **大容量存储** → 关机 → USB 线连 Mac → 开机
   （确认 PID 0x0D1A：`ioreg -p IOUSB -l | grep ILCE-1`）
2. 虚拟机运行时把 USB 交给 guest（VMware 菜单 虚拟机→设置→USB 和蓝牙→ILCE-1；
   vmx 已预置 `usb.autoConnect.device0 = "54c:d1a"`，插上可能自动接管）
3. guest 内（SSH 执行）：
   `cd ~/pmca && sudo ~/pmca-venv/bin/python pmca-console.py info -d libusb`
   → 预期 `Sony DSC ... mass storage mode`
4. `sudo ~/pmca-venv/bin/python pmca-console.py serviceshell`
   → `platform shell >` 后只读白名单：`info` / `shell`（uname, cat /proc/mounts,
   find / -name "*updatertalk*" -o -name "sauu"）/ `pull <路径> ~/libupdatertalk.so`
   （或 dd 更新分区 64MB 后 pull）
5. 拿到文件 → 宿主 `extract_key.py` → `unpack_ufu.py unpack --key2 <hex>` → 对比分析。

## 关键文件清单
- `Sony Software/`：`unpack_ufu.py`、`extract_key.py`、`KEY_HUNT_LOG.md`（完整攻防记录）、
  `SENSER_GUIDE.md`（v3 白名单/红线/流程）、`COMMUNITY_ASK.md`（求助帖草稿）、
  `PARALLELS_UBUNTU_GUIDE.md`（虚拟机教程，内容已按 VMware 修正）
- `~/pmca-a1/`：`id_ed25519`（SSH 密钥，勿丢）、`proxy.py`、`build-ova/`、`ubuntu-24.04.4-live-server-arm64.iso`
- 虚拟化：VMware Fusion 26.0.0（宿主已装）；pmca-a2 VM + seed.iso（cidata）

## 恢复动作（若进程/会话丢失）
1. `pgrep -f proxy.py` 无 → `nohup python3 ~/pmca-a1/proxy.py 8888 &`
2. 隧道无 → 重开 `ssh -R`（见上）；guest 不通 → 先 `vmrun list` / 找 DHCP 新 IP
3. VM 没开 → `vmrun start ~/Virtual\ Machines.localized/pmca-a2.vmwarevm/pmca-a2.vmx`
4. 相机提密钥受阻 → 发 `COMMUNITY_ASK.md` 到 fwtool #45 / personal-view；或换社区路线

## 2026-08-28 续轮体检（无相机可做的全部做完）
- VM 运行中 / SSH OK / PMCA_READY / USB OK / 代理+隧道存活 —— 全部绿
- guest 干跑验证：`info -d libusb` → "No devices found"（链路完好，安全失败预期）
- guest 已预置：`~/pmca/run_info.sh`（预检）、`~/pmca/STEPS.md`（相机到场白名单操作序列）
- 社区复查：fwtool #45 无新回复、无 gen5 密钥公开进展 → 相机路径不变
- 剩余唯一待办：相机到场 → 走 STEPS.md

## 2026-08-28 Round2: 全自动提取管线验证
- 逆向确认 pmca shell/interactive.py: 相机终端由 stdin 管道驱动（stdin_loop→相机shell）
- guest 已配 NOPASSWD（仅 pmca python 路径）→ 无密码全自动
- `~/pmca/auto_extract.sh`（发现阶段）+ STEPS.md 提取阶段/兜底 全部落地并通过无相机冒烟
- 相机到场 → 单条命令即提取，无需人工交互
