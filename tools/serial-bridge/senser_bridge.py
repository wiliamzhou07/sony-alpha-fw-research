#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
senser-bridge — Sony 相机 senser 串口桥

把相机的 senser 终端通道（a7C II senser root shell 同一条通道：
readTerminal/writeTerminal）桥接到本机 PTY + TCP 端口，全程落盘日志；
另提供只读的文件/内存通道用于读系统底层数据。

复用 ma1co/Sony-PMCA-RE 的协议实现（StartSenser 认证、分包、终端 ep）。

用法（用装好 pyusb 的 venv 跑）:
  ~/pmca-a1/venv/bin/python senser_bridge.py list
  ~/pmca-a1/venv/bin/python senser_bridge.py bridge            # 串口桥主功能
  ~/pmca-a1/venv/bin/python senser_bridge.py capture --seconds 30
  ~/pmca-a1/venv/bin/python senser_bridge.py readfile /proc/version out.txt
  ~/pmca-a1/venv/bin/python senser_bridge.py readmem 0xF1000000 0x100 out.bin
  ~/pmca-a1/venv/bin/python senser_bridge.py exit              # 退出 senser 模式

只读设计：刻意不暴露 writeFile/writeMemory/deleteFile（见 BRICK_SAFETY.md）。
"""
import argparse
import errno
import os
import pty
import select
import socket
import sys
import time
from datetime import datetime

DEFAULT_PMCA_HOME = os.path.expanduser('~/pmca-a1/src/Sony-PMCA-RE-master')
TERM_CHUNK = 0x40          # senser 终端通道单次读写上限（与 PMCA-RE 一致）
DEFAULT_TCP_PORT = 4599

# α1 上实测过的 senser 错误码（KEY_HUNT_LOG.md 2026-10-08/09）
LOCK_HINTS = {
    128: '通道被固件锁定（Error 128）——国行 CN2 α1 已知：文件/终端/内存通道全部关闭',
    129: 'adjust/备份通道被固件锁定（Error 129）——国行 CN2 α1 已知',
}


# ---------------------------------------------------------------- PMCA 装载

def load_pmca(home=None):
    home = home or os.environ.get('PMCA_HOME') or DEFAULT_PMCA_HOME
    if not os.path.isdir(home):
        sys.exit(f'找不到 PMCA-RE 源码目录: {home}\n'
                 f'用 --pmca-home 或环境变量 PMCA_HOME 指定（需含 pmca/ 包）')
    if home not in sys.path:
        sys.path.insert(0, home)
    from pmca.commands.usb import importDriver, listDevices          # noqa: F401
    from pmca.usb.sony import (SonySenserDevice, SonySenserAuthDevice,
                               SonySenserCamera, SonyMscExtCmdDevice,
                               SONY_ID_PRODUCT_SENSER)
    from pmca.usb.driver.generic import GenericUsbException
    import pmca.commands.usb as pmca_usb
    ns = type(sys)('pmca_ns')
    ns.importDriver = importDriver
    ns.listDevices = listDevices
    ns.SonySenserDevice = SonySenserDevice
    ns.SonySenserAuthDevice = SonySenserAuthDevice
    ns.SonySenserCamera = SonySenserCamera
    ns.SonyMscExtCmdDevice = SonyMscExtCmdDevice
    ns.SONY_ID_PRODUCT_SENSER = SONY_ID_PRODUCT_SENSER
    ns.GenericUsbException = GenericUsbException
    ns.pmca_usb = pmca_usb
    return ns


# ---------------------------------------------------------------- 终端桥（与硬件无关，可离线测试）

class TerminalBridge:
    """相机终端通道 <-> PTY + TCP + 日志。

    term 只需两个方法（由真机或测试假对象提供）:
      read_terminal()  -> bytes   （内部自带短超时，无数据返回 b''）
      write_terminal(bytes)       （超出 0x40 自动分片）
    """

    def __init__(self, term, log_path, pty_enabled=True, tcp_port=DEFAULT_TCP_PORT,
                 verbose=True):
        """tcp_port: None=禁用 TCP，0=随机端口，其它=固定端口"""
        self.term = term
        self.log_path = log_path
        self.pty_enabled = pty_enabled
        self.tcp_port = tcp_port
        self.verbose = verbose
        self.stop = False
        self._logf = None
        self._master = None
        self._slave_path = None
        self._srv = None
        self._clients = []
        self._out_buf = b''          # PTY 非阻塞写缓冲
        self.bound_tcp_port = None

    # ---- 生命周期 ----

    def setup(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
        self._logf = open(self.log_path, 'ab', 0)
        self._log_line('=== senser-bridge start ===')

        if self.pty_enabled:
            self._master, slave = pty.openpty()
            fcntl_set_nonblock(self._master)
            self._slave_path = os.ttyname(slave)
            os.close(slave)

        if self.tcp_port is not None:
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.bind(('127.0.0.1', self.tcp_port))
            self._srv.listen(4)
            self._srv.setblocking(False)
            self.bound_tcp_port = self._srv.getsockname()[1]

        if self.verbose:
            print('串口桥已建立：')
            if self._slave_path:
                print(f'  PTY  : screen {self._slave_path}')
            if self._srv:
                print(f'  TCP  : nc 127.0.0.1 {self.tcp_port}')
            print(f'  日志 : {self.log_path}')
            print('  Ctrl+C 退出（相机回到普通模式用 exit 子命令）')

    def close(self):
        try:
            self._log_line('=== senser-bridge stop ===')
        except Exception:
            pass
        for c in self._clients:
            try:
                c.close()
            except OSError:
                pass
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
        if self._master is not None:
            try:
                os.close(self._master)
            except OSError:
                pass
        if self._logf:
            self._logf.close()

    # ---- 数据面 ----

    def _log_line(self, text):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        self._logf.write(f'[{ts}] {text}\n'.encode('utf-8', 'replace'))

    @staticmethod
    def _render(data):
        text = data.decode('utf-8', 'replace')
        if any(ord(ch) < 32 and ch not in '\r\n\t' for ch in text):
            return repr(data)
        return text.rstrip('\n')

    def _distribute(self, data):
        """相机 -> 本机各出口"""
        self._log_line('<< ' + self._render(data))
        if self._master is not None:
            self._out_buf += data
            self._flush_pty()
        for c in list(self._clients):
            try:
                c.sendall(data)
            except OSError:
                self._drop_client(c)

    def _flush_pty(self):
        while self._out_buf:
            try:
                n = os.write(self._master, self._out_buf)
                self._out_buf = self._out_buf[n:]
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                self._master = None      # 对端关闭（screen 退出）
                return

    def _drop_client(self, c):
        if c in self._clients:
            self._clients.remove(c)
        try:
            c.close()
        except OSError:
            pass

    def _host_input(self, data):
        """本机(PTY/TCP) -> 相机"""
        self._log_line('>> ' + self._render(data))
        for i in range(0, len(data), TERM_CHUNK):
            self.term.write_terminal(data[i:i + TERM_CHUNK])

    def pump_once(self, timeout=0.02):
        """跑一轮桥：收发双向。返回本轮是否从相机读到数据。"""
        rlist = []
        if self._master is not None:
            rlist.append(self._master)
        if self._srv is not None:
            rlist.append(self._srv)
        rlist += self._clients
        ready, _, _ = select.select(rlist, [], [], timeout)

        if self._srv is not None and self._srv in ready:
            c, addr = self._srv.accept()
            c.setblocking(True)
            self._clients.append(c)
            self._log_line(f'-- tcp client {addr[0]}:{addr[1]} connected')

        for fd in ready:
            if fd is self._master:
                try:
                    d = os.read(fd, 4096)
                except OSError:
                    self._master = None
                    continue
                if d:
                    self._host_input(d)
            elif fd is self._srv:
                continue
            else:
                try:
                    d = fd.recv(4096)
                except OSError:
                    self._drop_client(fd)
                    continue
                if d == b'':
                    self._drop_client(fd)
                elif d:
                    self._host_input(d)

        d = self.term.read_terminal()
        if d:
            self._distribute(d)
            return True
        return False

    def run(self):
        try:
            while not self.stop:
                self.pump_once()
        except KeyboardInterrupt:
            if self.verbose:
                print('\n桥已停止。')


def fcntl_set_nonblock(fd):
    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


# ---------------------------------------------------------------- 相机侧封装

class SenserTerm:
    """真机终端通道适配：SonySenserDevice.readTerminal/writeTerminal"""

    def __init__(self, senser_dev):
        self.dev = senser_dev

    def read_terminal(self):
        return self.dev.readTerminal()

    def write_terminal(self, data):
        self.dev.writeTerminal(data)


def wait_for_senser(pmca, driver, timeout=15.0, verbose=True):
    """相机重枚举后返回 SonySenserDevice"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            devs = [d for d in pmca.listDevices(driver, quiet=True)
                    if isinstance(d, pmca.SonySenserDevice)]
        except Exception:
            devs = []
        if devs:
            return devs[0]
        time.sleep(0.5)
        if verbose:
            print('.', end='', flush=True)
    raise RuntimeError('等待 senser 模式设备超时（相机未重枚举为 PID 0x0336/0x02a9）')


def ensure_senser(pmca, driver, verbose=True):
    """确保相机处于 senser 模式并完成认证，返回 (senser_dev, camera, auth_dev)"""
    def log(msg):
        if verbose:
            print(msg)

    devs = list(pmca.listDevices(driver, quiet=True))
    senser = [d for d in devs if isinstance(d, pmca.SonySenserDevice)]
    if not senser:
        msc = [d for d in devs if isinstance(d, pmca.SonyMscExtCmdDevice)]
        if not msc:
            modes = describe_devices(pmca, devs)
            raise RuntimeError(
                '未找到可切换到 senser 模式的相机。\n'
                f'  当前设备: {modes or "无"}\n'
                '  请把相机 USB 模式设为 MSC（大容量存储）后重新插拔。')
        log('发现 MSC 模式相机，发送 StartSenser 并认证…')
        auth = pmca.SonySenserAuthDevice(msc[0].driver)
        auth.start()
        auth.authenticate()
        log('等待相机重枚举…')
        senser = [wait_for_senser(pmca, driver)]

    log('senser 设备已就绪，认证…')
    auth = pmca.SonySenserAuthDevice(senser[0].driver)
    auth.start()                 # 已在 senser 模式时厂商请求会失败，忽略
    auth.authenticate()
    camera = pmca.SonySenserCamera(senser[0])
    camera.readHasp()            # SenserPlatformBackend.start() 的同款握手
    log('认证通过。')
    return senser[0], camera, auth


def describe_devices(pmca, devs):
    out = []
    for d in devs:
        pid = d.driver.getId()[1] if hasattr(d.driver, 'getId') else '?'
        if isinstance(d, pmca.SonySenserDevice):
            mode = 'senser 服务模式'
        elif isinstance(d, pmca.SonyMscExtCmdDevice):
            mode = 'MSC 大容量存储（可切换 senser）'
        else:
            mode = type(d).__name__
        out.append(f'PID 0x{pid:04x} ({mode})')
    return ', '.join(out)


def default_log_path(prefix):
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'logs', f'{prefix}_{stamp}.log')


class ProgressFile:
    """写文件并打印进度（给 readFile/readMemory 的 outFile 用）"""

    def __init__(self, f, total=None):
        self.f = f
        self.total = total
        self.n = 0
        self._t0 = time.time()

    def write(self, b):
        self.f.write(b)
        self.n += len(b)
        if self.total:
            pct = min(100.0, self.n * 100.0 / self.total)
            rate = self.n / max(1e-6, time.time() - self._t0) / 1024
            print(f'\r  {self.n} / {self.total} B ({pct:5.1f}%, {rate:7.1f} KB/s)',
                  end='', flush=True)

    def close_done(self):
        print(f'\r  完成：共 {self.n} B，'
              f'耗时 {time.time() - self._t0:.1f}s' + ' ' * 20)


# ---------------------------------------------------------------- 子命令

def cmd_list(args):
    import usb.core
    SENSER = {0x02a9, 0x0336}
    UPDATER = {0x033a, 0x03e2}
    MSC = {0x0d1a}
    found = False
    for d in usb.core.find(find_all=True, idVendor=0x054c):
        found = True
        if d.idProduct in SENSER:
            mode = 'senser 服务模式 ← 桥可以直接连'
        elif d.idProduct in UPDATER:
            mode = 'updater/更新模式'
        elif d.idProduct in MSC:
            mode = 'MSC 大容量存储 ← 可切换 senser'
        else:
            mode = '普通模式（MTP/遥控）← 请先把相机 USB 连接设为 MSC 模式'
        print(f'  USB {d.bus:03d}/{d.address:03d}  PID 0x{d.idProduct:04x}  {mode}')
    if not found:
        print('  未发现索尼 USB 设备。请连接相机（USC 线，菜单里把 USB 连接设为 MSC）。')


def cmd_bridge(args):
    pmca = load_pmca(args.pmca_home)
    log_path = args.log or default_log_path('console')
    with pmca.importDriver(args.driver) as driver:
        senser_dev, camera, auth = ensure_senser(pmca, driver)
        bridge = TerminalBridge(SenserTerm(senser_dev), log_path,
                                pty_enabled=not args.no_pty,
                                tcp_port=None if args.no_tcp else args.tcp_port)
        camera.setTerminalEnable(False)
        camera.setTerminalEnable(True)
        try:
            bridge.setup()
            bridge.run()
        finally:
            try:
                camera.setTerminalEnable(False)
            except Exception:
                pass
            bridge.close()
            if args.stop_on_exit:
                print('发送 StopSenser，相机回到普通模式…')
                auth.stop()


def cmd_capture(args):
    pmca = load_pmca(args.pmca_home)
    log_path = args.log or default_log_path('capture')
    with pmca.importDriver(args.driver) as driver:
        senser_dev, camera, _ = ensure_senser(pmca, driver)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        print(f'单向捕获相机终端输出 -> {log_path}')
        print(f'（{args.seconds}s 后自动结束，Ctrl+C 随时停）')
        camera.setTerminalEnable(False)
        camera.setTerminalEnable(True)
        deadline = time.time() + args.seconds if args.seconds else None
        logf = open(log_path, 'ab', 0)
        try:
            while not (deadline and time.time() > deadline):
                d = senser_dev.readTerminal()
                if d:
                    sys.stdout.write(d.decode('utf-8', 'replace'))
                    sys.stdout.flush()
                    logf.write(d)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                camera.setTerminalEnable(False)
            except Exception:
                pass
            logf.close()
        print(f'\n日志已保存: {log_path}')


def cmd_readfile(args):
    pmca = load_pmca(args.pmca_home)
    with pmca.importDriver(args.driver) as driver:
        _, camera, _ = ensure_senser(pmca, driver)
        out = args.out or os.path.basename(args.path.rstrip('/')) or 'dump.bin'
        print(f'读取相机文件 {args.path} -> {out}')
        with open(out, 'wb') as f:
            pf = ProgressFile(f)
            try:
                camera.readFile(args.path, pf)
                pf.close_done()
            except Exception as e:
                f.truncate(0)
                hint = ''
                for code, h in LOCK_HINTS.items():
                    if str(code) in str(e):
                        hint = f'\n  → {h}'
                sys.exit(f'读取失败: {e}{hint}')


def cmd_readmem(args):
    pmca = load_pmca(args.pmca_home)
    base = int(args.base, 0)
    size = int(args.size, 0)
    if size <= 0 or size > 0x10000000:
        sys.exit('size 需在 1 字节 ~ 256MB 之间')
    with pmca.importDriver(args.driver) as driver:
        _, camera, _ = ensure_senser(pmca, driver)
        out = args.out or f'mem_{base:08x}_{size:x}.bin'
        print(f'读取内存 0x{base:08X} +0x{size:X} -> {out}')
        with open(out, 'wb') as f:
            pf = ProgressFile(f, total=size)
            try:
                camera.readMemory(base, size, pf)
                pf.close_done()
            except Exception as e:
                f.truncate(0)
                hint = ''
                for code, h in LOCK_HINTS.items():
                    if str(code) in str(e):
                        hint = f'\n  → {h}'
                sys.exit(f'读取失败: {e}{hint}')


def cmd_info(args):
    pmca = load_pmca(args.pmca_home)
    with pmca.importDriver(args.driver) as driver:
        senser_dev, camera, _ = ensure_senser(pmca, driver)
        print('--- USB 描述符 ---')
        usb_dev = senser_dev.driver.dev if hasattr(senser_dev.driver, 'dev') else None
        if usb_dev is not None:
            for attr, label in (('manufacturer', '厂商'), ('product', '产品'),
                                ('serial_number', '序列号')):
                try:
                    print(f'  {label}: {getattr(usb_dev, attr)}')
                except Exception:
                    pass
        print('--- senser readHasp ---')
        data = camera.readHasp()
        print('  ' + data.hex())
        print('（详细 Model/Serial/Region 读取沿用 KEY_HUNT_LOG 2026-08-28 的流程脚本）')


def cmd_exit(args):
    pmca = load_pmca(args.pmca_home)
    with pmca.importDriver(args.driver) as driver:
        _, _, auth = ensure_senser(pmca, driver)
        auth.stop()
        print('已发送 StopSenser。重新插拔 USB 后相机回到普通模式。')


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(
        description='Sony senser 串口桥（a7C II root shell 同款通道，只读设计）')
    ap.add_argument('--pmca-home', default=None,
                    help=f'PMCA-RE 源码目录（默认 {DEFAULT_PMCA_HOME}）')
    ap.add_argument('--driver', default='libusb', help="USB 驱动（默认 'libusb'）")
    ap.add_argument('--debug', action='store_true', help='出错时打印完整栈回溯')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('list', help='列出索尼 USB 设备及模式')

    p = sub.add_parser('bridge', help='终端串口桥：相机 <-> PTY+TCP+日志')
    p.add_argument('--tcp-port', type=int, default=DEFAULT_TCP_PORT)
    p.add_argument('--no-tcp', action='store_true')
    p.add_argument('--no-pty', action='store_true')
    p.add_argument('--log', default=None, help='日志文件路径')
    p.add_argument('--stop-on-exit', action='store_true',
                   help='退出时发送 StopSenser 回普通模式')

    p = sub.add_parser('capture', help='单向捕获相机终端输出')
    p.add_argument('--seconds', type=int, default=60)
    p.add_argument('--log', default=None)

    p = sub.add_parser('readfile', help='只读：从相机文件系统读文件')
    p.add_argument('path')
    p.add_argument('out', nargs='?')

    p = sub.add_parser('readmem', help='只读：内存转储（地址/长度支持 0x 前缀）')
    p.add_argument('base')
    p.add_argument('size')
    p.add_argument('out', nargs='?')

    sub.add_parser('info', help='读 senser Hasp/描述符信息')
    sub.add_parser('exit', help='发送 StopSenser 退出 senser 模式')

    args = ap.parse_args()
    try:
        {'list': cmd_list, 'bridge': cmd_bridge, 'capture': cmd_capture,
         'readfile': cmd_readfile, 'readmem': cmd_readmem,
         'info': cmd_info, 'exit': cmd_exit}[args.cmd](args)
    except RuntimeError as e:
        sys.exit(f'\n错误: {e}')
    except Exception as e:
        if args.debug:
            raise
        sys.exit(f'\nUSB/协议错误: {type(e).__name__}: {e}\n'
                 '（重插 USB 后重试；确认相机 USB 连接模式；加 --debug 看栈回溯）')


if __name__ == '__main__':
    main()
