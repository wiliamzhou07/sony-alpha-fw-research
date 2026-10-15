# 零基础照做：VMware Fusion 装 Ubuntu 虚拟机（α1 密钥提取用）

> 前提：ISO 已就位并校验通过：
> `~/pmca-a1/ubuntu-24.04.4-live-server-arm64.iso`（3.06GB）

---

## 第 0 步：第一次打开 VMware Fusion（2 分钟）

1. 打开「VMware Fusion」（应用程序里）。
2. 首次会显示许可协议：
   - 新版 Fusion（13.x/26.x）个人使用免费 → 选择 **"免费供个人使用"** / "Use for personal use"；
   - 若要求登录 Broadcom 账号：注册一个免费账号登录即可；
   - 有"我同意许可条款"就勾上 → 继续。
3. 进入主界面（能看到「新建」按钮）就算成功。

---

## 第 1 步：新建虚拟机（5 分钟）

1. 菜单栏：**文件（File）→ 新建（New）**。
2. 出现"选择安装方式" → 选 **「从光盘或图像文件安装（Install from a disc or image）」**。
3. **继续** → 在文件选择框按 **⌘⇧G**，粘贴：
   ```
   ~/pmca-a1/ubuntu-24.04.4-live-server-arm64.iso
   ```
   回车选中 ISO → 继续。
4. 系统选 **Ubuntu（Ubuntu 64-bit ARM）**（VMware 会自动识别，没弹出来就手动选）。
5. 配置页：名称 `ubuntu`；**内存 4096MB；CPU 2；硬盘 40GB** → 「继续」。
6. 点 **「完成」** → 虚拟机启动，出现蓝色安装界面。

---

## 第 2 步：安装 Ubuntu（约 10 分钟，蓝底白字）

VM 窗口里：

1. 语言 → **中文(简体)** → 回车
2. 键盘布局 → 默认 → 回车
3. 网络 → 自动获取 → 回车
4. 镜像设置 → 默认 → 回车
5. 磁盘 → **使用整个磁盘** → 继续 → 出现破坏数据警告 → **继续**（只是虚拟盘，放心）
6. 用户：姓名 `ubuntu`，用户名 `ubuntu`，密码 **`ubuntu1234`**（记牢）→ 简单密码警告 → 「是，继续」
7. **勾选 OpenSSH server** → 继续
8. 无其他套件 → 继续 → 等待安装（几分钟）
9. 「安装完成」→ **重启**（Restart now）

重启后登录：`ubuntu` / `ubuntu1234`

---

## 第 3 步：一键准备（2 分钟）

登录后复制粘贴整个块（Mac 上复制 → 在 VM 终端 ⌘V）：

```bash
sudo apt update -y
sudo apt install -y git curl python3 python3-venv python3-pip python3-tk libusb-1.0-0
mkdir -p ~/pmca && cd ~/pmca
curl -sL https://codeload.github.com/ma1co/Sony-PMCA-RE/tar.gz/refs/heads/master -o p.tgz
mkdir -p Sony-PMCA-RE && tar xzf p.tgz -C Sony-PMCA-RE --strip-components=1 && rm p.tgz
cd Sony-PMCA-RE
python3 -m venv ~/pmca-venv
~/pmca-venv/bin/pip install -q --upgrade pip
~/pmca-venv/bin/pip install -q pyusb pycryptodomex pyyaml asn1crypto tlslite-ng axmlparserpy==0.0.4 certifi pycparser==2.17
```

自检：
```bash
cd ~/pmca/Sony-PMCA-RE
~/pmca-venv/bin/python -c "import usb.core, usb.backend.libusb1; print('USB:', 'OK' if usb.backend.libusb1.get_backend() else 'FAIL')"
~/pmca-venv/bin/python pmca-console.py --help 2>&1 | grep -c serviceshell
```
预期：`USB: OK` 和 `1`。不是这两个结果 → 把输出发我。

---

## 第 4 步：等相机来了再接（暂不操作）

1. 相机：MENU → 设置 → USB 连接 → **大容量存储**；关机 → USB 线连 Mac → 开机。
2. VMware：虚拟机窗口菜单 **虚拟机（Virtual Machine）→ 设置（Settings）→ USB 和蓝牙（USB & Bluetooth）** → 找到 **ILCE-1** 并勾选连接（相机会从 Mac 桌面消失，正常）。
3. VM 内：`lsusb | grep -i sony` 应看到 `054c:0d1a`。
4. 零风险验证：
   ```bash
   sudo ~/pmca-venv/bin/python pmca-console.py info -d libusb
   ```
   预期 `Sony DSC ... is a camera in mass storage mode`。
5. 通过后：`sudo ~/pmca-venv/bin/python pmca-console.py serviceshell`
   等到 `platform shell >` —— **先停，把屏幕内容发我**，我再给只读提取指令。

---

## 常见问题

| 现象 | 处理 |
|---|---|
| 卡在许可/登录页 | 选「个人使用 / Personal use」；有账号就登录，没有就注册（免费） |
| 鼠标被 VM 锁住 | 按 ⌃Ctrl 释放，再点 VM 窗口取回 |
| 选镜像时找不到 ISO | ⌘⇧G 粘贴 `~/pmca-a1/ubuntu-24.04.4-live-server-arm64.iso` |
| 装完系统网络不通 | VM 默认 NAT 网络；`ping 8.8.8.8` 试试，不通告诉我 |
| `USB: FAIL` | `sudo apt install -y libusb-1.0-0` 后重跑自检 |

---

做完第 1~3 步回我"装好了"；任何一步卡住随时发屏幕内容，我全程监控虚拟机目录（VMware 的 VM 存放在
`~/Documents/Virtual Machines.localized/`，你每做一步我都能看到）。
