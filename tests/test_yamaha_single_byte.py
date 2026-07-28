#!/usr/bin/env python3
"""
Yamaha YDS Single-Byte Protocol Tester.
Based on sniffed YDS traffic (Commands: 0x1C, 0xFD, 0xF1).
Sends single-byte command requests over /dev/ttyUSB0 and logs ECU response bytes.
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial required. Install with: pip install pyserial")
    sys.exit(1)


def test_single_byte_protocol(port: str = "/dev/ttyUSB0", baud: int = 9600):
    print("=" * 70)
    print(f" TESTING YAMAHA SINGLE-BYTE YDS PROTOCOL ({port} @ {baud} Baud)")
    print("=" * 70)

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            rtscts=False,
            dsrdtr=False
        )
    except Exception as e:
        print(f"[-] Could not open {port}: {e}")
        return

    # List of known and candidate single-byte YDS command opcodes
    # 0x1C, 0xFD, 0xF1 were observed in the official YDS sniff log!
    test_opcodes = [
        0x1C, 0xFD, 0xF1, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x15, 0x1A, 0x1B, 0x20, 0x30,
        0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0xFF
    ]

    print(f"\nPolling {len(test_opcodes)} single-byte opcodes...\n")

    for cmd in test_opcodes:
        ser.reset_input_buffer()
        ser.write(bytes([cmd]))
        ser.flush()

        time.sleep(0.05)

        # Gather incoming bytes
        rx_buf = bytearray()
        start = time.time()
        while (time.time() - start) < 0.15:
            n = ser.in_waiting
            if n > 0:
                rx_buf.extend(ser.read(n))
            time.sleep(0.005)

        rx_bytes = bytes(rx_buf)

        if not rx_bytes:
            print(f"Cmd 0x{cmd:02X} -> 0 bytes received.")
            continue

        # Remove 1-byte TX echo
        if rx_bytes[0] == cmd:
            ecu_response = rx_bytes[1:]
            if ecu_response:
                print(f"Cmd 0x{cmd:02X} -> [SUCCESS] TX Echo: 0x{cmd:02X} | ECU Response ({len(ecu_response)}b): {ecu_response.hex().upper()}")
            else:
                print(f"Cmd 0x{cmd:02X} -> TX Echo 0x{cmd:02X} (No ECU response byte)")
        else:
            print(f"Cmd 0x{cmd:02X} -> RX Stream ({len(rx_bytes)}b): {rx_bytes.hex().upper()}")

    ser.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha Single-Byte YDS Protocol Tester")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default 9600)")
    args = parser.parse_args()

    test_single_byte_protocol(args.port, args.baud)
