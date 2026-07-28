#!/usr/bin/env python3
"""
Yamaha 4V TTL Logic Level Diagnostic & Compatibility Test.
Explains the voltage threshold mismatch between 4V ECU TTL logic and 12V OBD2 transceivers.
"""

import sys

def explain_4v_ttl_mismatch():
    print("=" * 70)
    print(" CRITICAL DIAGNOSIS: 4V TTL LOGIC LEVEL DETECTED ON YAMAHA ECU")
    print("=" * 70)
    print("Your measurement of ~4V DC on the disconnected ECU data line is the key!")
    print("")
    print("1. THE PHYSICS ISSUE:")
    print("   - Your Yamaha ECU (63P-01) uses a 5V/3.3V TTL UART logic signal (~4V High).")
    print("   - The USB-to-OBD2 (VAG-COM KKL) adapter is designed for 12V automotive K-Line.")
    print("   - A 12V K-Line transceiver (L9637D / MC33660) powered by 13.8V battery voltage")
    print("     sets its receiver high-threshold (V_IH) at ~7.0V to 9.6V.")
    print("")
    print("   RESULT: The 12V adapter sees 4V as PERMANENT LOW (0V). The ECU's")
    print("   responses (0V to 4V pulses) are completely ignored by the 12V receiver!")
    print("")
    print("2. HOW TO SOLVE THIS (2 Options):")
    print("")
    print("   Option A: Use a 5V/3.3V USB-to-TTL Serial Adapter (Recommended)")
    print("   --------------------------------------------------------------")
    print("   - Connect a cheap 5V/3.3V FTDI or CP2102 USB-to-UART adapter:")
    print("     * Adapter GND  <---> Yamaha Black Wire (GND)")
    print("     * Adapter RX/TX <---> Yamaha Data Wire (~4V)")
    print("       (Connect RX & TX together via a 1k resistor or 1N4148 signal diode).")
    print("   - Since TTL adapters have a ~2.0V threshold, they read 4V logic perfectly!")
    print("")
    print("   Option B: Convert your VAG-COM OBD2 Cable to 5V Operation")
    print("   --------------------------------------------------------")
    print("   - Disconnect 13.8V battery power from OBD2 Pin 16.")
    print("   - Feed +5V DC (e.g. from USB +5V wire) into OBD2 Pin 16.")
    print("   - This lowers the internal transceiver receiver threshold to ~2.5V, allowing")
    print("     the VAG-COM cable to read the 4V ECU pulses cleanly!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    explain_4v_ttl_mismatch()
