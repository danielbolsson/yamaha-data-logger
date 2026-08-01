#!/usr/bin/env python3
"""
Yamaha YDS Full 256 Opcode Bus Scanner.
Scans all single-byte opcodes (0x00 through 0xFF) over /dev/ttyUSB0 @ 9600 baud
and logs every opcode that yields a valid ECU response.
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial required. Install with: pip install pyserial")
    sys.exit(1)


def scan_all_opcodes(port: str = "/dev/ttyUSB0", baud: int = 9600):
    print("=" * 70)
    print(f" SCANNING ALL 256 SINGLE-BYTE YDS OPCODES ({port} @ {baud} Baud)")
    print(" ⚠️  WARNING: DO NOT RUN WHILE ENGINE IS RUNNING!")
    print("     Sweeping 0x00-0xFF hits active ECU diagnostic opcodes (cylinder")
    print("     cut-off / ignition tests), causing engine misfires & hickups!")
    print("=" * 70)

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
            rtscts=False,
            dsrdtr=False
        )
    except Exception as e:
        print(f"[-] Could not open {port}: {e}")
        return

    responsive_opcodes = []

    print("Scanning opcodes 0x00 through 0xFF (0 to 255)...\n")

    for cmd in range(256):
        ser.reset_input_buffer()
        ser.write(bytes([cmd]))
        ser.flush()

        # Gather incoming bytes for 40ms
        rx_buf = bytearray()
        start = time.time()
        while (time.time() - start) < 0.04:
            n = ser.in_waiting
            if n > 0:
                rx_buf.extend(ser.read(n))
            time.sleep(0.005)

        rx = bytes(rx_buf)

        # Check if ECU responded beyond local 1-byte TX echo
        if len(rx) > 1:
            if rx[0] == cmd:
                payload = rx[1:]
                print(f"[FOUND] Opcode 0x{cmd:02X} ({cmd:3d}) -> ECU Payload ({len(payload)}b): {payload.hex().upper()}")
                responsive_opcodes.append((cmd, payload))
            else:
                print(f"[FOUND] Opcode 0x{cmd:02X} ({cmd:3d}) -> Raw RX ({len(rx)}b): {rx.hex().upper()}")
                responsive_opcodes.append((cmd, rx))
        elif len(rx) == 1 and rx[0] != cmd:
            print(f"[FOUND] Opcode 0x{cmd:02X} ({cmd:3d}) -> ECU Single Byte: {rx.hex().upper()}")
            responsive_opcodes.append((cmd, rx))

    ser.close()

    print("\n" + "=" * 70)
    print(f" SCAN COMPLETE: Found {len(responsive_opcodes)} responsive ECU opcodes:")
    print("=" * 70)
    for cmd, payload in responsive_opcodes:
        print(f"  Opcode 0x{cmd:02X} ({cmd:3d}) : {payload.hex().upper()}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha 256 Opcode Scanner")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default 9600)")
    args = parser.parse_args()

    scan_all_opcodes(args.port, args.baud)
