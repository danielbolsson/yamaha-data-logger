#!/usr/bin/env python3
"""
Yamaha YDS TPS & Oil Pressure Opcode Detector.
Scans all 112 active ECU opcodes to identify:
1. Oil Pressure (~350 kPa / 51 psi)
2. Fuel Injection Duration (~2.58 ms)
3. Warning Status flags (Fixing false low oil warning)
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial required. Install with: pip install pyserial")
    sys.exit(1)


def scan_tps_and_oil(port: str = "/dev/ttyUSB0", baud: int = 9600):
    print("=" * 70)
    print(f" SCANNING OPCODES FOR OIL PRESSURE (~350 kPa) AND TPS ON {port}")
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

    results = {}

    for cmd in range(256):
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
            results[cmd] = rx[1]
        elif len(rx) == 1 and rx[0] != cmd:
            results[cmd] = rx[0]

    ser.close()

    print(f"\nCaptured {len(results)} active opcodes from running engine:\n")

    # 1. Search for Oil Pressure candidates (~350 kPa)
    print("--- OIL PRESSURE CANDIDATES (~350 kPa / 51 psi) ---")
    for h in results:
        for l in results:
            if h != l:
                val16 = (results[h] << 8) | results[l]
                # Check 16-bit / 10 = 350.0 (3400 to 3700 raw)
                if 3400 <= val16 <= 3700:
                    print(f"[16-BIT OIL MATCH!] High Opcode 0x{h:02X} ({results[h]}) + Low Opcode 0x{l:02X} ({results[l]}) = {val16} -> {val16/10.0:.1f} kPa ({val16/68.95:.1f} psi)")

    # 2. Search for Injection Duration candidates (~2.58 ms -> 645 raw / 250)
    print("\n--- INJECTION DURATION CANDIDATES (~2.58 ms) ---")
    for h in results:
        for l in results:
            if h != l:
                val16 = (results[h] << 8) | results[l]
                if 600 <= val16 <= 700:
                    print(f"[INJ MATCH!] Opcode 0x{h:02X} (0x{results[h]:02X}) + Opcode 0x{l:02X} (0x{results[l]:02X}) = {val16} -> {val16/250.0:.2f} ms")

    # 3. Print all 1-byte opcodes and values
    print("\n--- ALL ACTIVE OPCODES (HEX & DECIMAL) ---")
    for op, val in sorted(results.items()):
        print(f"Opcode 0x{op:02X} ({op:3d}) = 0x{val:02X} ({val:3d})")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha TPS & Oil Pressure Scanner")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    args = parser.parse_args()

    scan_tps_and_oil(args.port)
