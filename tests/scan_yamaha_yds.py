#!/usr/bin/env python3
"""
Yamaha YDS Exhaustive Bus Scanner & Protocol Diagnostic Utility.
Performs deep-scan polling across multiple baud rates (9600, 10400, 15625, 16064, 4800, 6250),
wakeup handshakes (0x80, 0x00, 0x02), and multi-step byte polling.
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)


def read_bus_stream(ser: serial.Serial, req_bytes: bytes, wait_sec: float = 0.4) -> bytes:
    """Sends request bytes and continuously gathers all response bytes for wait_sec."""
    ser.reset_input_buffer()
    ser.write(req_bytes)
    ser.flush()

    start_time = time.time()
    rx_buf = bytearray()

    while (time.time() - start_time) < wait_sec:
        n = ser.in_waiting
        if n > 0:
            rx_buf.extend(ser.read(n))
        time.sleep(0.01)

    return bytes(rx_buf)


def scan_baud_rate(port: str, baud: int):
    print(f"\n==================================================")
    print(f" SCANNING BAUD RATE: {baud} Baud (Port: {port})")
    print(f"==================================================")

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
        print(f"[-] Could not open {port} at {baud} baud: {e}")
        return

    # 1. Test 0x80 Wakeup byte -> 50ms pause -> 0x02 Poll
    print("\n[Test 1] 2-Step 0x80 Wakeup -> 50ms pause -> 0x02 Poll...")
    ser.reset_input_buffer()
    ser.write(bytes([0x80]))
    ser.flush()
    time.sleep(0.05)
    
    wake_rx = read_bus_stream(ser, bytes([0x02]), wait_sec=0.3)
    print(f"    Raw RX Stream: {wake_rx.hex().upper()}")

    # 2. Test 0x00 Wakeup byte
    print("\n[Test 2] Single-Byte 0x80 / 0x00 Query...")
    for byte_val in [0x80, 0x00, 0x02]:
        rx = read_bus_stream(ser, bytes([byte_val]), wait_sec=0.2)
        print(f"    Sent 0x{byte_val:02X} -> RX ({len(rx)}b): {rx.hex().upper()}")

    # 3. Test Multi-Byte Request Frames
    test_packets = [
        ("YDS Standard Live [02 02 30 34]", bytes([0x02, 0x02, 0x30, 0x34])),
        ("YDS Short Live [02 01 30 33]", bytes([0x02, 0x01, 0x30, 0x33])),
        ("YDS Init [02 01 B0 47]", bytes([0x02, 0x01, 0xB0, 0x47])),
        ("YDS Simple [02 00 02]", bytes([0x02, 0x00, 0x02])),
        ("ISO 9141 Init [80 00 80]", bytes([0x80, 0x00, 0x80])),
        ("KWP2000 Fast [81 11 F1 81 04]", bytes([0x81, 0x11, 0xF1, 0x81, 0x04])),
        ("OBD2 Standard PID [01 00]", bytes([0x01, 0x00])),
        ("OBD2 RPM PID [01 0C]", bytes([0x01, 0x0C]))
    ]

    for label, pkt in test_packets:
        rx = read_bus_stream(ser, pkt, wait_sec=0.3)
        print(f"\n--> Pkt '{label}': Sent {pkt.hex().upper()}")
        print(f"    Total RX ({len(rx)}b): {rx.hex().upper()}")

        if len(rx) > len(pkt):
            print(f"    *** ECU RESPONSE DETECTED! *** Extra bytes: {rx[len(pkt):].hex().upper()}")

    ser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha YDS Exhaustive Bus Scanner")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    args = parser.parse_args()

    print(f"Starting Yamaha YDS Bus Scanner on {args.port}...")
    print("Ensure the engine is running or key switch is ON.")

    for b in [9600, 10400, 15625, 16064, 4800, 6250]:
        scan_baud_rate(args.port, b)
