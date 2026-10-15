#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a1_uart_boot — α1 的 bootrom 串口引导桥（ILCE-7M4-RE 路线的 α1 适配版）

原始实现: DavidBuchanan314/ILCE-7M4-RE (scripts/push_payload.py + tools/uart_boot)
  - rp2040 固件把 bootrom 秘密串口启动模式的记录格式位敲到 Multi 口 RX 脚
  - 本脚本通过 rp2040(USB 串口协议) 推送记录: 任意内存写 + 设入口 → 裸机载荷
  - 解锁检查绕过: MEM_WRITE 直接改栈上的期望值 (A7IV 偏移 0xfe02f398, α1 需验证)

改进(相对原版): 载荷控制台不只 echo 到 stdout, 而是接上本目录 TerminalBridge
  —— 得到 PTY(screen) + TCP(nc) + 时间戳日志, 与 senser 串口桥同一套体验。

用法:
  ~/pmca-a1/venv/bin/python a1_uart_boot.py <payload.bin> -p /dev/ttyACM0
  ~/pmca-a1/venv/bin/python a1_uart_boot.py payload.bin --expect '[mira] fastboot ready'
  ~/pmca-a1/venv/bin/python a1_uart_boot.py payload.bin --no-bridge   # 原版行为

⚠️ 只读纪律: 载荷用 fastboot 的 dump/peek/dumpbrom; 不要在 α1 上执行任何
   flash/poke 写操作, 除非先完成两份完整 eMMC 备份 (见 BRICK_SAFETY.md)。
"""
import argparse
import enum
import os
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from senser_bridge import TerminalBridge

# ---------------------------------------------------------------- rp2040 协议
# (与 ILCE-7M4-RE tools/uart_boot/uart_boot.ino 对应)

class RpCmd(enum.IntEnum):
    PING    = 0x01
    RESET   = 0x02
    CARRIER = 0x03
    BLOB    = 0x04
    BAUD    = 0x05
    UART    = 0x06


class RpEvt(enum.IntEnum):
    ACK  = 0x81
    ERR  = 0x82
    UART = 0x83


RP_VERSION = b"uart_boot 1"

# ---------------------------------------------------------------- bootrom 串口启动协议

class SerCmd(enum.IntEnum):
    """
    非 0/0xffff 的 type 都按内存写命令处理；
    重发第一条命令即可结束会话——所以先发一条空写 END_MARKER 备用。
    """
    SET_UNLOCK = 0x0000
    MEM_WRITE  = 0x0001
    END_MARKER = 0x0123
    SET_ENTRY  = 0xffff


LOAD_ADDR = 0xFE020000
MAX_RECORD_PAYLOAD = 512      # 真实上限 4086, 取小值让进度条平滑
TRANSMIT_START = 0.5
RECORD_GAP = 0.0144

# A7IV bootrom 的解锁期望值在栈上的地址；α1 的 bootrom 若是不同修订版,
# 该偏移可能漂移 —— 先用 fastboot 的 dumpbrom 拿到 α1 自己的 bootrom 核对。
STACK_ADDR_A7IV = 0xFE02F398


def record(rtype: int, value: int, payload=b""):
    body = struct.pack("<IHI", 10 + len(payload), rtype, value) + payload
    return body + struct.pack("<I", zlib.crc32(body))


def boot_script(payload, addr=LOAD_ADDR, entry=None, unlock_code=None,
                stack_addr=STACK_ADDR_A7IV):
    if entry is None:
        entry = addr

    recs = [record(SerCmd.END_MARKER, 0)]  # 空写命令, 备用作结束标记

    for off in range(0, len(payload), MAX_RECORD_PAYLOAD):
        recs.append(record(SerCmd.MEM_WRITE, addr + off,
                           payload[off:off + MAX_RECORD_PAYLOAD]))

    if unlock_code is None:  # 解锁绕过: 直接改写栈上的期望值
        unlock_code = 0xDEADBEEF
        val = unlock_code.to_bytes(4, "little")
        val += (zlib.crc32(val) ^ 0xFFFFFFFF).to_bytes(4, "little")
        recs.append(record(SerCmd.MEM_WRITE, stack_addr, val))

    recs.append(record(SerCmd.SET_ENTRY, entry))
    recs.append(record(SerCmd.SET_UNLOCK, unlock_code))
    recs.append(record(SerCmd.END_MARKER, 0))
    return recs


# ---------------------------------------------------------------- rp2040 设备

class Error(Exception):
    pass


class Device:
    def __init__(self, port, timeout=5.0):
        import serial
        self.ser = serial.Serial(port, 115200, timeout=timeout)

    def close(self):
        self.ser.close()

    def send(self, cmd: RpCmd, data=b""):
        self.ser.write(bytes([cmd]) + struct.pack("<H", len(data)) + data)

    def _read_exact(self, n):
        out = b""
        while len(out) < n:
            chunk = self.ser.read(n - len(out))
            if not chunk:
                return None
            out += chunk
        return out

    def recv(self):
        hdr = self._read_exact(3)
        if hdr is None:
            return None
        (n,) = struct.unpack("<H", hdr[1:3])
        data = self._read_exact(n) if n else b""
        if data is None:
            return None
        return RpEvt(hdr[0]), data

    def ack(self):
        while True:
            pkt = self.recv()
            if pkt is None:
                raise Error("等待 rp2040 应答超时")
            evt, data = pkt
            if evt == RpEvt.ACK:
                return data
            if evt == RpEvt.ERR:
                raise Error(data.decode("utf-8", "replace"))
            if evt == RpEvt.UART:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()

    def ping(self):
        self.send(RpCmd.PING)
        ver = self.ack()
        if ver != RP_VERSION:
            raise Error(f"rp2040 固件版本不符: {ver!r} (需要 {RP_VERSION!r})")

    def reset(self):
        self.send(RpCmd.RESET)
        self.ack()

    def carrier(self, on):
        self.send(RpCmd.CARRIER, bytes([1 if on else 0]))
        self.ack()

    def blob(self, rec):
        self.send(RpCmd.BLOB, rec)
        self.ack()

    def baud(self, baud):
        self.send(RpCmd.BAUD, struct.pack("<I", baud))
        self.ack()


# ---------------------------------------------------------------- 载荷控制台适配

class RpUartTerm:
    """把 rp2040 的 UART 事件流适配成 TerminalBridge 需要的 term 接口。

    ERR 事件转成控制台可见的一行（也进日志）。
    """

    def __init__(self, dev, uart_baud):
        self.dev = dev
        self.uart_baud = uart_baud
        self._buf = bytearray()

    def read_terminal(self):
        for _ in range(64):          # 一轮最多排空 64 个包, 避免饿死发送方向
            pkt = self.dev.recv()
            if pkt is None:
                break
            evt, data = pkt
            if evt == RpEvt.UART:
                self._buf += data
            elif evt == RpEvt.ERR:
                self._buf += b"\n[dev] " + data + b"\n"
            elif evt == RpEvt.ACK:
                pass
        out = bytes(self._buf)
        self._buf.clear()
        return out

    def write_terminal(self, data):
        # rp2040 侧一次最多 UART_CHUNK=512
        for i in range(0, len(data), 512):
            self.dev.send(RpCmd.UART, data[i:i + 512])


# ---------------------------------------------------------------- 主流程

def await_line(dev, want, timeout):
    """等载荷 UART 打印出 want 整行内容（等不到返回 False）"""
    needle = want.encode()
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        pkt = dev.recv()
        if pkt is None:
            continue
        evt, data = pkt
        if evt != RpEvt.UART:
            continue
        buf += data
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        end = buf.rfind(b"\n")
        if end >= 0:
            if needle in buf[:end]:
                return True
            del buf[:end + 1]
    return False


def main():
    ap = argparse.ArgumentParser(
        description="α1 bootrom 串口引导桥 (ILCE-7M4-RE 路线, 载荷控制台带 PTY/TCP/日志)")
    ap.add_argument("payload", help="裸机载荷 (如 payloads/fastboot/build/fastboot.bin)")
    ap.add_argument("-p", "--port", default="/dev/ttyACM0", help="rp2040 USB 串口")
    ap.add_argument("-a", "--addr", type=lambda s: int(s, 0), default=LOAD_ADDR)
    ap.add_argument("-e", "--entry", type=lambda s: int(s, 0), default=None)
    ap.add_argument("-u", "--unlock-code", type=lambda s: int(s, 0), default=None,
                    help=f"已知解锁码则给(0x2CF25621 为 A7IV); 缺省走栈改写绕过"
                         f"(栈地址 {STACK_ADDR_A7IV:#x}, α1 修订版可能漂移)")
    ap.add_argument("-s", "--stack-addr", type=lambda s: int(s, 0),
                    default=STACK_ADDR_A7IV)
    ap.add_argument("-b", "--baud", type=int, default=115200,
                    help="载荷控制台波特率")
    ap.add_argument("--expect", metavar="TEXT",
                    help="桥接前等待载荷 UART 打印 TEXT (如 '[mira] fastboot ready')")
    ap.add_argument("--expect-timeout", type=float, default=15.0)
    ap.add_argument("--no-bridge", action="store_true",
                    help="不接 PTY/TCP 桥, 只把载荷控制台 echo 到 stdout (原版行为)")
    ap.add_argument("--tcp-port", type=int, default=4599)
    ap.add_argument("--no-tcp", action="store_true")
    ap.add_argument("--no-pty", action="store_true")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    with open(args.payload, "rb") as f:
        payload = f.read()

    entry = args.addr if args.entry is None else args.entry
    records = boot_script(payload, args.addr, entry, args.unlock_code,
                          args.stack_addr)
    total = sum(len(r) for r in records)
    print(f"载荷 {len(payload)} B → {len(records)} 条记录 / {total} B, "
          f"入口 {entry:#x}, 载入 {args.addr:#x}")

    dev = Device(args.port)
    try:
        dev.ping()
        print("rp2040 OK。复位相机并开始推送…")
        dev.reset()
        dev.carrier(1)
        time.sleep(TRANSMIT_START)

        done = 0
        for i, rec in enumerate(records):
            dev.blob(rec)
            done += len(rec)
            pct = done * 100.0 / total
            print(f"\r  推送 {done}/{total} B ({pct:5.1f}%)", end="", flush=True)
            if i + 1 < len(records):
                time.sleep(RECORD_GAP)
        print("\r  推送完成。" + " " * 20)
        dev.carrier(0)

        uart_term = None
        if args.expect:
            dev.baud(args.baud)
            ok = await_line(dev, args.expect, args.expect_timeout)
            if not ok:
                sys.exit(f'TIMEOUT: {args.expect_timeout:g}s 内未等到 {args.expect!r}')
            uart_term = RpUartTerm(dev, args.baud)
        elif not args.no_bridge:
            dev.baud(args.baud)
            uart_term = RpUartTerm(dev, args.baud)

        if uart_term is not None:
            log_path = args.log or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "logs",
                "uartboot_" + time.strftime("%Y%m%d_%H%M%S") + ".log")
            bridge = TerminalBridge(uart_term, log_path,
                                    pty_enabled=not args.no_pty,
                                    tcp_port=None if args.no_tcp else args.tcp_port)
            bridge.setup()
            try:
                bridge.run()
            finally:
                bridge.close()
                try:
                    dev.baud(0)
                except Exception:
                    pass
        else:
            dev.baud(0)
    finally:
        dev.close()


if __name__ == "__main__":
    main()
