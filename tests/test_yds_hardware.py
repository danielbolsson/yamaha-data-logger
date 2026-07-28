#!/usr/bin/env python3
"""
Yamaha YDS Hardware & Pinout Verification Tool.
Helps isolate:
1. Internal Cable TX Echo vs Bus Echo.
2. FTDI Serial Break / Pulse Signal Integrity.
3. ECU K-Line Pull-Up Voltage vs Adapter Internal Pull-Up.
"""

import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial package is required. Run: pip install pyserial")
    sys.exit(1)


def run_cable_offline_echo_test(port: str):
    print("=" * 65)
    print(" STEP 1: CABLE SELF-TEST (UNPLUG CABLE FROM ENGINE 3-PIN PLUG)")
    print("=" * 65)
    print("Keep the USB cable plugged into the computer, but DISCONNECT")
    print("the 3-pin connector from the Yamaha engine.")
    input("\nPress ENTER when cable is disconnected from engine...")

    try:
        ser = serial.Serial(port=port, baudrate=9600, timeout=0.2)
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        test_bytes = bytes([0x02, 0x02, 0x30, 0x34])
        ser.write(test_bytes)
        ser.flush()
        time.sleep(0.1)

        rx = ser.read(32)
        ser.close()

        print(f"\n[+] Cable Standalone RX Output: {rx.hex().upper()}")

        if rx == test_bytes:
            print(" -> RESULT: Cable has INTERNAL hardware TX loopback (transceiver echoes TX locally).")
        elif not rx:
            print(" -> RESULT: Cable does NOT echo locally. Echo only happens when connected to a 12V bus.")
        else:
            print(f" -> RESULT: Received unexpected byte sequence: {rx.hex().upper()}")

    except Exception as e:
        print(f"[-] Error opening serial port: {e}")

    print("=" * 65 + "\n")


def print_multimeter_pinout_guide():
    print("=" * 65)
    print(" STEP 2: MULTIMETER VOLTAGE DIAGNOSIS ON ENGINE 3-PIN CONNECTOR")
    print("=" * 65)
    print("With the engine running or key switch ON, measure DC Voltage on the")
    print("ENGINE SIDE of the 3-pin diagnostic connector (DISCONNECTED from cable):")
    print("")
    print("  1. Black Wire (Engine Ground):")
    print("     -> Measure resistance to battery negative terminal: MUST BE 0 OHMS.")
    print("")
    print("  2. Red Wire (Engine +12V Power):")
    print("     -> Measure DC Voltage to Ground: MUST BE 12.5V - 14.4V.")
    print("")
    print("  3. Data Wire (Yamaha ECU K-Line Data):")
    print("     -> Measure DC Voltage to Ground (DISCONNECTED from OBD2 cable):")
    print("     -> EXPECTED: +10V to +12V DC (Driven by ECU internal pull-up resistor).")
    print("     -> CRITICAL: If Data wire reads 0V DC when disconnected, the ECU")
    print("        is NOT outputting K-Line voltage or the wrong wire is pinned!")
    print("")
    print("  4. OBD2 Cable Adapter Pinout Matching:")
    print("     - OBD2 Pin 16  <---> Engine Red Wire (+12V)")
    print("     - OBD2 Pin 4/5 <---> Engine Black Wire (GND)")
    print("     - OBD2 Pin 7   <---> Engine Data Wire (K-Line)")
    print("     * Note: Ensure Data is connected to OBD2 PIN 7 (K-Line), NOT Pin 15 (L-Line)!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yamaha YDS Hardware & Pinout Verification Tool")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    args = parser.parse_args()

    run_cable_offline_echo_test(args.port)
    print_multimeter_pinout_guide()
