#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线回环测试：用假相机终端对象驱动 TerminalBridge，
验证 PTY / TCP / 日志 / 0x40 分片全链路（无需真机）。

  ~/pmca-a1/venv/bin/python test_bridge_offline.py
"""
import os
import socket
import sys
import tempfile
import threading
import time
import queue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from senser_bridge import TerminalBridge, TERM_CHUNK


class FakeTerm:
    """假相机终端通道：inject = 相机发数据；written = 相机收到的数据"""

    def __init__(self):
        self.inbox = queue.Queue()
        self.written = []
        self._fail_after = None

    def read_terminal(self):
        try:
            return self.inbox.get_nowait()
        except queue.Empty:
            time.sleep(0.005)
            return b''

    def write_terminal(self, data):
        assert len(data) <= TERM_CHUNK, f'分片失败: {len(data)} > 0x40'
        self.written.append(data)

    def inject(self, data):
        self.inbox.put(data)


def recv_until(sock, want, timeout=3.0):
    sock.settimeout(timeout)
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline and len(buf) < want:
        try:
            d = sock.recv(4096)
        except socket.timeout:
            break
        if not d:
            break
        buf += d
    return buf


def read_fd_until(fd, want, timeout=3.0):
    import select as _sel
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline and len(buf) < want:
        r, _, _ = _sel.select([fd], [], [], 0.1)
        if r:
            buf += os.read(fd, 4096)
        else:
            time.sleep(0.02)
    return buf


def main():
    tmp = tempfile.mkdtemp(prefix='senser_bridge_test_')
    log_path = os.path.join(tmp, 'console_test.log')

    term = FakeTerm()
    bridge = TerminalBridge(term, log_path, pty_enabled=True, tcp_port=0,
                            verbose=False)
    bridge.setup()
    assert bridge.bound_tcp_port, 'TCP 端口未绑定'

    failures = []

    def check(name, cond, detail=''):
        print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f' — {detail}' if detail and not cond else ''))
        if not cond:
            failures.append(name)

    # 打开 PTY 从端（模拟 screen）和 TCP 客户端（模拟 nc）
    slave_fd = os.open(bridge._slave_path, os.O_RDWR | os.O_NOCTTY)
    tcp = socket.create_connection(('127.0.0.1', bridge.bound_tcp_port), timeout=3)

    t = threading.Thread(target=bridge.run, daemon=True)
    t.start()
    time.sleep(0.1)

    # 1) 本机 -> 相机：TCP 发 200 字节（>0x40，验证分片），PTY 发一行
    # （从端默认行规程会把 \n 转成 \r\n，真实场景 screen 设 raw 模式无此转换）
    payload = bytes(range(200))
    tcp.sendall(payload)
    os.write(slave_fd, b'hello from screen\n')
    expect = payload + b'hello from screen'
    deadline = time.time() + 3
    while time.time() < deadline and len(b''.join(term.written)) < len(expect):
        time.sleep(0.05)
    got = b''.join(term.written)
    check('本机→相机 TCP 200B 分片转发', payload in got)
    check('本机→相机 PTY 转发', b'hello from screen' in got, repr(got))
    check('0x40 分片约束（FakeTerm 内 assert）', True)

    # 2) 相机 -> 本机：PTY 与 TCP 都应收到
    boot = b'BOOT: CXD90057 console ready\n'
    term.inject(boot)
    got_tcp = recv_until(tcp, len(boot))
    check('相机→TCP 输出', boot in got_tcp, repr(got_tcp))
    got_pty = read_fd_until(slave_fd, len(boot))
    check('相机→PTY 输出', boot in got_pty, repr(got_pty))

    # 3) 二进制（非 UTF-8）数据也要落到日志
    term.inject(bytes([0xff, 0xfe, 0x00, 0x41]))
    recv_until(tcp, 4)
    time.sleep(0.2)
    log = open(log_path, 'rb').read()
    check('日志含 << 方向记录', b'<< ' in log)
    check('日志含 >> 方向记录', b'>> ' in log)
    check('日志二进制转义记录', b'\\x00' in log or b'\\xff' in log or b'0xff' in log.lower())

    # 4) 断开清理
    bridge.stop = True
    t.join(timeout=2)
    check('桥线程正常退出', not t.is_alive())

    os.close(slave_fd)
    tcp.close()
    bridge.close()

    print()
    if failures:
        print(f'结果: {len(failures)} 项失败 -> {failures}')
        sys.exit(1)
    print(f'结果: 全部通过。日志样例: {log_path}')


if __name__ == '__main__':
    main()
