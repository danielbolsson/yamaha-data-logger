#!/usr/bin/env python3
"""
Yamaha YDS RPM Opcode Comparison Tool.
Monitors candidate RPM opcodes side-by-side to identify which opcode scales 1:1 with engine speed.
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial required. Install with: pip install pyserial")
    sys.exit(1)


def monitor_rpms(port: str = "/dev/ttyUSB0", baud: int = 9600):
    print("=" * 75)
    print(f" MONITORING CANDIDATE RPM OPCODES ON {port}")
    print("=" * 75)

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

    def get_val16(h_op, l_op):
        ser.reset_input_buffer()
        ser.write(bytes([h_op]))
        ser.flush()
        time.sleep(0.015)
        rx1 = ser.read(16)
        h_val = rx1[1] if len(rx1) > 1 and rx1[0] == h_op else 0

        ser.reset_input_buffer()
        ser.write(bytes([l_op]))
        ser.flush()
        time.sleep(0.015)
        rx2 = ser.read(16)
        l_val = rx2[1] if len(rx2) > 1 and rx2[0] == l_op else 0

        return (h_val << 8) | l_val

    print(f"{'Time':<10} | {'Op 0x06/07':<12} | {'Op 0x92/93':<12} | {'Op 0x08/09':<12} | {'Op 0x00/01':<12}")
    print("-" * 75)

    try:
        start_time = time.time()
        while (time.time() - start_time) < 10.0:
            val_0607 = get_val16(0x06, 0x07)
            val_9293 = get_val16(0x92, 0x93)
            val_0809 = get_val16(0x08, 0x09)
            val_0001 = get_val16(0x00, 0x01)

            t_str = time.strftime('%H:%M:%S')
            print(f"{t_str:<10} | {val_0607:<12} | {val_9293:<12} | {val_0809:<12} | {val_0001:<12}")
            time.sleep(0.2)

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor Candidate RPM Opcodes")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    args = parser.parse_args()

    monitor_rpms(args.port)
