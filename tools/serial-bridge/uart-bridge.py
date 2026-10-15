#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uart-bridge — 物理 UART 串口桥（硬件备选路线）

CXD90057 的控制台 UART 是 PL011 @ 0xF1000000，serial0 = 460800 波特
（见 HARDWARE_ARCHITECTURE.md / cxd90057_decompiled.dts）。若给主板 UART 焊点接上
3.3V TTL USB 串口线，用本脚本即可把底层启动日志/控制台桥接到 PTY + TCP + 日志。

用法:
  ~/pmca-a1/venv/bin/python uart-bridge.py --list
  ~/pmca-a1/venv/bin/python uart-bridge.py --port /dev/tty.usbserial-XXXX --baud 460800
  # 然后: screen /dev/ttysXXX  或  nc 127.0.0.1 4599

⚠️ 相机主板 UART 为 3.3V TTL：切勿接 RS-232 电平(±12V)；GND 必须共地；先只接 TX/GND 只读。
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from senser_bridge import TerminalBridge


class SerialTerm:
    def __init__(self, ser):
        self.ser = ser

    def read_terminal(self):
        n = self.ser.in_waiting
        return self.ser.read(min(n, 4096) or 1)

    def write_terminal(self, data):
        self.ser.write(data)


def list_ports():
    from serial.tools import list_ports as lp
    ports = list(lp.comports())
    if not ports:
        print('未发现串口设备（USB-TTL 线插上后会出现 /dev/tty.usbserial-* 或 /dev/tty.usbmodem*）')
        return
    for p in ports:
        print(f'  {p.device}  {p.description}')


def main():
    ap = argparse.ArgumentParser(description='物理 UART 串口桥 (pyserial)')
    ap.add_argument('--list', action='store_true', help='列出串口设备')
    ap.add_argument('--port', help='串口设备路径，如 /dev/tty.usbserial-0001')
    ap.add_argument('--baud', type=int, default=460800,
                    help='波特率（CXD90057 控制台 460800；MultiPort 遥控协议 9600）')
    ap.add_argument('--tcp-port', type=int, default=4599)
    ap.add_argument('--no-pty', action='store_true')
    ap.add_argument('--no-tcp', action='store_true')
    ap.add_argument('--log', default=None)
    args = ap.parse_args()

    if args.list:
        list_ports()
        return
    if not args.port:
        ap.error('需要 --port（先 --list 查看）')

    import serial
    ser = serial.Serial(args.port, args.baud, bytesize=8, parity='N',
                        stopbits=1, timeout=0.02, write_timeout=1)
    log_path = args.log or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'logs',
        'uart_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.log')

    bridge = TerminalBridge(SerialTerm(ser), log_path,
                            pty_enabled=not args.no_pty,
                            tcp_port=None if args.no_tcp else args.tcp_port)
    bridge.setup()
    try:
        bridge.run()
    finally:
        bridge.close()
        ser.close()


if __name__ == '__main__':
    main()
