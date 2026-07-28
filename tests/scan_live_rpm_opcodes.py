#!/usr/bin/env python3
"""
Yamaha YDS Live Engine RPM Opcode Finder.
Queries all responsive opcodes while the engine is running (~700 RPM)
and identifies the exact High/Low bytes matching ~700 RPM (0x02BC or raw ~700).
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial required. Install with: pip install pyserial")
    sys.exit(1)


def scan_live_rpm(port: str = "/dev/ttyUSB0", baud: int = 9600):
    print("=" * 70)
    print(f" SCANNING YDS OPCODES FOR LIVE ENGINE RPM (~700 RPM) ON {port}")
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

    # List of candidate opcodes that returned data
    opcodes_to_test = [
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
        0x10, 0x11, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x30, 0x31, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x50,
        0x51, 0x56, 0x57, 0x58, 0x59, 0x5C, 0x5E, 0x5F, 0x60, 0x61, 0x70, 0x71, 0x72, 0x80, 0x81, 0x82,
        0x83, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0x9B, 0x9C, 0x9D, 0xB0,
        0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xCB, 0xCC, 0xD0,
        0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF, 0xE0, 0xE1, 0xE2, 0xE3, 0xE4,
        0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xF0, 0xF1, 0xFD, 0xFE, 0xFF
    ]

    results = {}

    for cmd in opcodes_to_test:
        ser.reset_input_buffer()
        ser.write(bytes([cmd]))
        ser.flush()

        rx_buf = bytearray()
        start = time.time()
        while (time.time() - start) < 0.03:
            n = ser.in_waiting
            if n > 0:
                rx_buf.extend(ser.read(n))
            time.sleep(0.003)

        rx = bytes(rx_buf)
        if len(rx) > 1 and rx[0] == cmd:
            val = rx[1]
            results[cmd] = val

    ser.close()

    print(f"\nCaptured {len(results)} live opcodes while engine is running:\n")

    # Search for High/Low 16-bit pairs that equal ~650 to ~850 RPM
    print("--- 16-Bit RPM Pair Candidates (Target ~650 - 850 RPM) ---")
    found_rpm_pair = False

    for h_op in results:
        for l_op in results:
            if h_op != l_op:
                val16 = (results[h_op] << 8) | results[l_op]
                if 500 <= val16 <= 1200:
                    print(f"[RPM MATCH!] High Opcode 0x{h_op:02X} (0x{results[h_op]:02X}) + Low Opcode 0x{l_op:02X} (0x{results[l_op]:02X}) = {val16} RPM")
                    found_rpm_pair = True

    # Search for single-byte RPM candidates (e.g. RPM / 10)
    print("\n--- 8-Bit Single Byte RPM Candidates (Target ~65 - 85) ---")
    for op, val in results.items():
        if 60 <= val <= 90:
            print(f"[SINGLE-BYTE RPM MATCH!] Opcode 0x{op:02X} = {val} (--> {val * 10} RPM)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha Live Engine RPM Opcode Finder")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    args = parser.parse_args()

    scan_live_rpm(args.port)
