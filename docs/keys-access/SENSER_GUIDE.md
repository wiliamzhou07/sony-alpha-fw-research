# α1 (ILCE-1) 服务模式（senser）密钥提取操作手册 v3 —— 虚拟机路线（2026-08-27）

## 为什么是虚拟机（当天实测结论）
- 宿主机直连**失败**：macOS 26 的 USBMSC 内核驱动占用相机 MSC 接口，
  libusb 无法 detach（`[Errno 13] Access denied`）；且 Apple Silicon 不支持第三方 kext，
  索尼相机驱动的原生路径也不可行。
- **VMware Fusion / Parallels 有内核级 USB 仲裁**，能把相机 USB 从 macOS 完整接管
  （社区 issue #504 配方即 VMware on Mac M1；评论区 2025-04 也有 Parallels 成功案例）。
  QEMU 系（UTM）走 libusb，同样会被内核占用拦住。

## 主机侧资源（已就绪/下载中）
- `~/pmca-a1/ubuntu-24.04.4-live-server-arm64.iso`（3.06GB，后台下载中）
- `~/pmca-a1/vm/guest_setup.sh`（虚拟机内一键准备脚本）
- `~/pmca-a1/venv` + `~/pmca-a1/src/Sony-PMCA-RE-master`（宿主机对照用）
- 宿主机插着相机时已确认：`Sony | ILCE-1` (054c:0d1a)，MSC 接口（类 8）✓

## 步骤 1：装虚拟机软件（Parallels Desktop，brew cask）
```bash
export HOMEBREW_NO_AUTO_UPDATE=1
brew install --cask parallels
```
（VMware Fusion 的官方 cask 已下架、旧直链域名 DNS 也不通，不推荐折腾；
Parallels 试用版即可，有 14 天试用，USB 直通能力与社区成功案例一致。）

## 步骤 2：装 Ubuntu ARM 虚拟机（Parallels 自动安装）
1. 打开 Parallels Desktop → 文件 → 新建 → 选「安装 Windows 或其他操作系统(不经安装助手)」→
   **从镜像文件安装** → 选 `~/pmca-a1/ubuntu-24.04.4-live-server-arm64.iso`
2. 会提示 macOS 镜像 → 选 **Ubuntu（ARM）** 模板 → 4GB 内存 / 40GB 磁盘 / 2 核
3. 启动后按 Ubuntu 安装向导：选 Ubuntu Server、默认键盘、**勾选 OpenSSH Server**、
   创建用户名/密码 → 完成重启

## 步骤 3：虚拟机内准备（复制粘贴）
```bash
bash -c "$(curl -sL https://codeload.github.com/ma1co/Sony-PMCA-RE/tar.gz/refs/heads/master >/dev/null; echo '')" \
# 更简单：直接把 ~/pmca-a1/vm/guest_setup.sh 的内容粘贴进终端（或挂载共享目录执行）
```
（也支持手动：`apt install git python3-venv python3-pip python3-tk libusb-1.0-0` → clone PMCA → venv 装依赖；
不再复述：直接 `cat ~/pmca-a1/vm/guest_setup.sh` 的内容复制粘贴即可。）
自检：`lsusb | grep -i sony` 之后能看到 054c:0d1a。

## 步骤 4：连接相机（需要相机在场）
1. 相机：MENU → 设置 → USB 连接 → **大容量存储**；关机→连 Mac→开机。
2. Parallels：菜单 设备(Devices) → USB 和蓝牙 → 勾选 **ILCE-1**（相机即交给虚拟机）。
3. 虚拟机内：`lsusb | grep -iSony` 能看到 054c:0d1a。

## 步骤 5：零风险验证 → 服务模式 → 提取
```bash
cd ~/pmca/Sony-PMCA-RE
sudo ~/pmca-venv/bin/python pmca-console.py info -d libusb    # 预期: Sony DSC ... mass storage mode
sudo ~/pmca-venv/bin/python pmca-console.py serviceshell      # 预期: Switched → platform shell >
```
shell 内白名单（只读）：
```text
info
shell          # 相机终端：uname -a; cat /proc/mounts;
               #   find / -name "*updatertalk*" -o -name "sauu" -o -name "initrd*" 2>/dev/null
               #   ls -la /dev/ | grep -iE "nflash|mmc|mtd"
```
→ 找到 `libupdatertalk.so` → `Ctrl-D` 退出终端 → `pull <路径> ~/libupdatertalk.so`
（或：`dd if=/dev/... of=/tmp/upd.img bs=1M count=64` 再 pull）
→ 文件交给我 → `extract_key.py` 自动找密钥 → `unpack_ufu.py unpack --key2 <hex> ...` 完成解包。

## 红线
- 不执行：`push / tweak / bk w / bk patch / bk s / bk lock / bk unlock / install`
- 异常：Parallels 断开 USB → 相机扣电池重启 → 恢复正常（senser 模式可逆）
- 白名单外命令先问

## 已知成功参照
- FX3 / FX30（同代 BIONZ XR）on MacBook M1 Pro（VMware）+ 多人反馈成功：issue #504
- Parallels 成功案例（FX-30，2025-04）：同一 issue 评论区
