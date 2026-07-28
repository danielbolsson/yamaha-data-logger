#!/usr/bin/env python3
"""
Advanced Yamaha YDS K-Line Protocol Diagnostic & Hardware Verification Tool.
Performs:
1. ISO 9141 5-Baud Slow Initialization (0x33 @ 5 Baud).
2. K-Line Fast-Init / Break Pulses.
3. Multi-Baud Rate Testing (9600, 10400, 15625, 16064, 4800, 6250 baud).
4. Full byte stream monitoring to isolate physical hardware wiring vs ECU protocol issues.
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial package is required. Run: pip install pyserial")
    sys.exit(1)


def test_5baud_init(port: str, target_baud: int = 10400):
    print(f"\n---> Testing ISO 9141 5-Baud Slow Initialization (Target: {target_baud} Baud)...")
    try:
        # 1. Send Address Byte 0x33 at 5 Baud (200ms bit time)
        print("     [1/4] Sending 0x33 address byte at 5 baud...")
        s5 = serial.Serial(port=port, baudrate=5, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=3.0)
        s5.reset_input_buffer()
        s5.reset_output_buffer()
        s5.write(bytes([0x33]))
        s5.flush()
        time.sleep(2.0)  # Wait for 5-baud transmission to finish
        s5.close()

        # 2. Switch to target operational baud rate
        print(f"     [2/4] Switching port to {target_baud} baud and listening for ECU sync bytes...")
        s = serial.Serial(port=port, baudrate=target_baud, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=1.5)
        
        # Read ECU sync bytes (ISO 9141 expects 0x55, KB1, KB2)
        rx_sync = s.read(16)
        print(f"     [3/4] Received Sync Bytes ({len(rx_sync)}b): {rx_sync.hex().upper()}")

        if rx_sync:
            print(f"     [SUCCESS] ECU Responded to 5-Baud Init! Raw Hex: {rx_sync.hex().upper()}")
            
            # Send standard YDS live data polling request
            req = bytes([0x02, 0x02, 0x30, 0x34])
            s.reset_input_buffer()
            s.write(req)
            s.flush()
            time.sleep(0.15)
            rx_data = s.read(32)
            print(f"     [4/4] Live Sensor Response ({len(rx_data)}b): {rx_data.hex().upper()}")
        else:
            print("     [!] No sync bytes received from ECU after 5-baud init.")

        s.close()

    except Exception as e:
        print(f"     [-] 5-Baud Init Exception: {e}")


def test_fast_init(port: str, baud: int):
    print(f"\n==================================================")
    print(f" Testing Fast-Init Direct Polling: {port} @ {baud} Baud")
    print(f"==================================================")

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,
            rtscts=False,
            dsrdtr=False
        )
    except Exception as e:
        print(f"[-] ERROR: Could not open {port} at {baud} baud: {e}")
        return

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    # K-Line 25ms to 50ms break pulse
    ser.break_condition = True
    time.sleep(0.025)
    ser.break_condition = False
    time.sleep(0.025)

    test_requests = [
        ("YDS Standard Request [02 02 30 34]", bytes([0x02, 0x02, 0x30, 0x34])),
        ("YDS Init Request [02 01 B0 47]", bytes([0x02, 0x01, 0xB0, 0x47])),
        ("YDS Sensor Query [02 01 30 33]", bytes([0x02, 0x01, 0x30, 0x33])),
        ("KWP2000 Fast Init [81 11 F1 81 04]", bytes([0x81, 0x11, 0xF1, 0x81, 0x04])),
    ]

    for name, req in test_requests:
        ser.reset_input_buffer()
        print(f"\n--> Transmitting '{name}'...")
        ser.write(req)
        ser.flush()

        time.sleep(0.15)
        raw_rx = ser.read(64)

        if not raw_rx:
            print("    [!] 0 bytes received.")
            continue

        print(f"    [+] Total RX ({len(raw_rx)} bytes): {raw_rx.hex().upper()}")

        if raw_rx.startswith(req):
            payload = raw_rx[len(req):]
            if payload:
                print(f"    [SUCCESS] ECU Response Received! Payload: {payload.hex().upper()}")
            else:
                print("    [*] TX Echo received, but ECU did not append response bytes.")
        else:
            print(f"    [+] Received data without TX echo prefix: {raw_rx.hex().upper()}")

    ser.close()


def print_hardware_troubleshooting():
    print("\n" + "=" * 60)
    print(" HARDWARE & WIRING CHECKLIST FOR YAMAHA YDS (ECU 63P-01)")
    print("=" * 60)
    print("If TX Echo is received but 0 ECU response bytes are returned:")
    print("1. IGNITION KEY SWITCH: Is the key switch turned ON?")
    print("   -> The ECM must have +12V power to send/receive telemetry.")
    print("2. 4V TTL LOGIC vs 12V RECEIVER THRESHOLD:")
    print("   -> Disconnected Yamaha K-Line reads ~4V DC (5V TTL logic level).")
    print("   -> Standard 12V OBD2 transceivers (L9637D/MC33660) powered by 13.8V")
    print("      have a ~7.0V-9.6V receiver threshold, ignoring 4V pulses!")
    print("   -> FIX: Supply +5V (instead of 12V) to OBD2 Pin 16, or use a 5V USB-to-TTL adapter.")
    print("3. PIN MAPPING CHECK:")
    print("   -> OBD2 Pin 16 (Red)   <--> YDS 3-Pin Red (+12V or +5V for 5V transceiver)")
    print("   -> OBD2 Pin 4/5 (Black) <--> YDS 3-Pin Black (GND)")
    print("   -> OBD2 Pin 7 (K-Line) <--> YDS 3-Pin Data Wire (~4V TTL)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha YDS K-Line Hardware Diagnostic Utility")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    args = parser.parse_args()

    print(f"Starting Yamaha YDS K-Line Diagnostic Tool on {args.port}...")
    print("Ensure the boat ignition key switch is turned ON.")

    target_bauds = [9600, 10400, 15625, 16064, 4800, 6250]

    # 1. Run 5-Baud Slow Init Tests across baud rates
    for baud in target_bauds:
        test_5baud_init(args.port, baud)

    # 2. Run Fast-Init Tests across baud rates
    for baud in target_bauds:
        test_fast_init(args.port, baud)

    # 3. Print Hardware Troubleshooting Guide
    print_hardware_troubleshooting()
