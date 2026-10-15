#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a1_uart_boot 离线测试：记录格式（与 uart_boot.ino 解码逻辑对照）+ RpUartTerm 桥接。

  ~/pmca-a1/venv/bin/python test_uart_boot_offline.py
"""
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import queue
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a1_uart_boot import (RpCmd, RpEvt, RP_VERSION, SerCmd, Device, Error,
                          RpUartTerm, record, boot_script, LOAD_ADDR,
                          STACK_ADDR_A7IV)
from senser_bridge import TerminalBridge


def check(name, cond, detail=''):
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f' — {detail}' if detail and not cond else ''))
    return cond


def test_record_format():
    ok = True
    rec = record(SerCmd.MEM_WRITE, 0xFE020000, b'\x11\x22\x33')
    ln, rtype, val = struct.unpack('<IHI', rec[:10])
    body = rec[:10 + 3]
    crc, = struct.unpack('<I', rec[-4:])
    ok &= check('record: len 字段 = 10+payload', ln == 13, f'{ln}')
    ok &= check('record: type/value', (rtype, val) == (SerCmd.MEM_WRITE, 0xFE020000))
    ok &= check('record: payload 原样', rec[10:-4] == b'\x11\x22\x33')
    ok &= check('record: CRC32(body)', crc == zlib.crc32(body))
    # uart_boot.ino 端 MAX_RECORD=4100, 记录不能超
    big = record(SerCmd.MEM_WRITE, 0, b'A' * 4086)
    ok &= check('record: 4086B 在 rp2040 上限内', len(big) + 4 <= 4100 + 4)

    payload = b'\xAA' * 1200
    recs = boot_script(payload)
    ok &= check('boot_script: 首条为 END_MARKER',
                struct.unpack('<H', recs[0][4:6])[0] == SerCmd.END_MARKER)
    writes = [r for r in recs if struct.unpack('<H', r[4:6])[0] == SerCmd.MEM_WRITE]
    ok &= check('boot_script: 3 条载荷分片 + 1 条栈改写', len(writes) == 4, f'{len(writes)}')
    ok &= check('boot_script: 载荷分片地址连续',
                [struct.unpack('<I', r[6:10])[0] for r in writes[:3]] ==
                [LOAD_ADDR, LOAD_ADDR + 512, LOAD_ADDR + 1024])
    ok &= check('boot_script: 栈改写在写载荷之后',
                struct.unpack('<I', writes[-1][6:10])[0] == STACK_ADDR_A7IV)
    types = [struct.unpack('<H', r[4:6])[0] for r in recs]
    ok &= check('boot_script: 尾部 SET_ENTRY→SET_UNLOCK→END',
                types[-3:] == [SerCmd.SET_ENTRY, SerCmd.SET_UNLOCK, SerCmd.END_MARKER])
    return ok


class FakeDev:
    """假 rp2040：UART 写回环 + 预置相机输出队列"""

    def __init__(self):
        self.rx = queue.Queue()       # 相机 -> 主机 (RpEvt.UART)
        self.sent = []

    # 供 RpUartTerm 调用的接口（与 Device 同名）
    def send(self, cmd, data=b''):
        if cmd == RpCmd.UART:
            self.sent.append(data)
            # 模拟载荷回显
            self.rx.put((RpEvt.UART, b'echo:' + data))
        elif cmd == RpCmd.BAUD:
            self.rx.put((RpEvt.ACK, b''))

    def recv(self):
        try:
            return self.rx.get_nowait()
        except queue.Empty:
            time.sleep(0.005)
            return None

    def ping(self):
        return RP_VERSION

    def reset(self):
        pass

    def carrier(self, on):
        pass

    def blob(self, rec):
        pass

    def baud(self, baud):
        self.send(RpCmd.BAUD, struct.pack('<I', baud))


def test_uart_term_bridge():
    ok = True
    tmp = tempfile.mkdtemp(prefix='a1_uart_boot_test_')
    log_path = os.path.join(tmp, 'boot_console.log')
    dev = FakeDev()
    term = RpUartTerm(dev, 115200)
    bridge = TerminalBridge(term, log_path, pty_enabled=True, tcp_port=0,
                            verbose=False)
    bridge.setup()
    t = threading.Thread(target=bridge.run, daemon=True)
    t.start()
    tcp = socket.create_connection(('127.0.0.1', bridge.bound_tcp_port), timeout=3)
    time.sleep(0.1)

    # 主机 -> 载荷: TCP 发 >512B 验证 RpUartTerm 的 512 分片
    payload = bytes(range(256)) * 3    # 768B
    tcp.sendall(payload)
    deadline = time.time() + 3
    while time.time() < deadline and len(b''.join(dev.sent)) < len(payload):
        time.sleep(0.05)
    sent = b''.join(dev.sent)
    ok &= check('主机→载荷 768B 经 512 分片', sent == payload,
                f'len={len(sent)}')
    ok &= check('分片 ≤512', all(len(c) <= 512 for c in dev.sent))

    # 载荷 -> 主机: 预置输出 + 回显都应到 TCP 与日志
    dev.rx.put((RpEvt.UART, b'[mira] fastboot ready\n'))
    dev.rx.put((RpEvt.ERR, b'something bad'))
    buf = b''
    tcp.settimeout(3)
    deadline = time.time() + 3
    while time.time() < deadline and b'something bad' not in buf:
        try:
            buf += tcp.recv(4096)
        except socket.timeout:
            break
    ok &= check('载荷→TCP 输出(含 ERR 事件)', b'[mira] fastboot ready' in buf
                and b'[dev] something bad' in buf, repr(buf[:120]))
    time.sleep(0.2)
    log = open(log_path, 'rb').read()
    ok &= check('日志记录双向', b'<< ' in log and b'>> ' in log)

    bridge.stop = True
    t.join(timeout=2)
    ok &= check('桥线程退出', not t.is_alive())
    tcp.close()
    bridge.close()
    return ok


if __name__ == '__main__':
    print('-- 记录格式 --')
    ok1 = test_record_format()
    print('-- RpUartTerm 桥接 --')
    ok2 = test_uart_term_bridge()
    print()
    print('结果: 全部通过' if (ok1 and ok2) else '结果: 存在失败项')
    sys.exit(0 if (ok1 and ok2) else 1)
