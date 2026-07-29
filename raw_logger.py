#!/usr/bin/env python3
"""
Yamaha Diagnostic System (YDS) Raw Telemetry Logger.
Connects to Yamaha F150 ECU (63P-8591A-01) over serial port and logs raw ECU opcode responses
to a JSON Lines (.jsonl) file for offline calibration, testing, and replay.

Usage:
  python3 raw_logger.py --port /dev/ttyUSB0 --baud 9600 --rate 5.0 --output logs/raw_telemetry.jsonl
  python3 raw_logger.py --mock  # Test logging with simulated raw ECU frames
"""

import os
import sys
import time
import json
import math
import argparse
import datetime
import logging
from typing import Dict, Any, Optional

try:
    from yds_reader import YDSReader
except ImportError:
    print("Error: yds_reader.py not found in current directory.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("raw_logger")

FRAME_OPCODES = [
    0x1C, 0xFD, 0xE5, 0xE8, 0xFE, 0xFF, 0xDE, 0xD0, 0xF0, 0xEF,
    0x00, 0x01, 0x04, 0x05, 0x08, 0x09, 0x0B, 0x0E, 0x0F,
    0x1B, 0x1D, 0x40, 0x41, 0x51, 0x91, 0xE9, 0x02, 0x03, 0xF1
]


def create_raw_logger():
    parser = argparse.ArgumentParser(description="Log raw Yamaha YDS ECU opcode telemetry to file.")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--rate", type=float, default=5.0, help="Polling rate in Hz (default: 5.0)")
    parser.add_argument("--output", default=None, help="Output file path (default: logs/raw_ecu_<timestamp>.jsonl)")
    parser.add_argument("--duration", type=float, default=0, help="Logging duration limit in seconds (0 = unlimited)")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode generating simulated raw frames")
    return parser


def log_raw_telemetry():
    parser = create_raw_logger()
    args = parser.parse_args()

    # Determine output filepath
    if not args.output:
        os.makedirs("logs", exist_ok=True)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = os.path.join("logs", f"raw_ecu_{timestamp_str}.jsonl")
    else:
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    reader = YDSReader(port=args.port, baudrate=args.baud, mock_mode=args.mock)

    logger.info(f"Initializing YDS Raw Telemetry Logger -> Saving to: {args.output}")
    logger.info(f"Polling rate: {args.rate} Hz | Target Port: {args.port} | Mock: {args.mock}")

    if not args.mock:
        if not reader.connect():
            logger.error(f"Could not connect to serial port {args.port}. Check cable & ignition switch.")
            sys.exit(1)
        logger.info("Connected to Yamaha ECU serial port.")

    frame_count = 0
    start_time = time.time()
    interval = 1.0 / max(0.1, args.rate)

    print("\n" + "=" * 80)
    print(f"  🔴 LOGGING RAW YAMAHA YDS ECU TELEMETRY -> {args.output}")
    print("  Press Ctrl+C to stop logging and save recording.")
    print("=" * 80 + "\n")

    try:
        with open(args.output, "a", encoding="utf-8") as outfile:
            # Write recording header metadata
            header = {
                "type": "header",
                "version": "1.0",
                "ecu_model": "63P-8591A-01",
                "engine": "Yamaha F150",
                "timestamp_start": start_time,
                "iso_start": datetime.datetime.utcnow().isoformat() + "Z",
                "polling_rate_hz": args.rate,
                "opcodes_polled": [f"0x{op:02X}" for op in FRAME_OPCODES]
            }
            outfile.write(json.dumps(header) + "\n")
            outfile.flush()

            while True:
                loop_start = time.time()

                if args.duration > 0 and (loop_start - start_time) >= args.duration:
                    logger.info(f"Reached logging duration limit of {args.duration}s. Stopping.")
                    break

                raw_vals = {}
                if args.mock:
                    # Simulated raw opcode values for testing logger offline
                    sim_t = loop_start - start_time
                    sim_rpm = 650.0 + math.sin(sim_t * 0.5) * 50.0
                    raw_rpm = int(sim_rpm)
                    raw_vals = {
                        0x00: (raw_rpm >> 8) & 0xFF,
                        0x01: raw_rpm & 0xFF,
                        0x04: 2,
                        0x40: 183,  # 13.84V
                        0x05: 112,  # 47.75 kPa
                        0x91: 161,  # 31.0°C
                        0x1B: 125,  # 23.6°C
                        0x0E: 10,
                        0x0F: 19,   # 364.4 kPa oil
                        0x1E: 1,
                        0x1F: 247,  # 2.58 ms injector
                        0xE8: 1,
                        0xE5: 239   # 496.0 Hours
                    }
                else:
                    for op in FRAME_OPCODES:
                        val = reader.query_opcode(op)
                        if val is not None:
                            raw_vals[op] = val

                if raw_vals:
                    frame_count += 1

                    # Convert integer opcodes to hex string keys ("0x00": 2, etc.) for JSON readability
                    formatted_opcodes = {f"0x{op:02X}": val for op, val in raw_vals.items()}

                    record = {
                        "type": "frame",
                        "frame": frame_count,
                        "timestamp": loop_start,
                        "elapsed": round(loop_start - start_time, 3),
                        "raw_opcodes": formatted_opcodes
                    }

                    # Write record line
                    outfile.write(json.dumps(record) + "\n")
                    outfile.flush()

                    # Print status summary
                    rpm_h = raw_vals.get(0x00, 0)
                    rpm_l = raw_vals.get(0x01, 0)
                    calc_rpm = (rpm_h << 8) | rpm_l

                    batt_h = raw_vals.get(0x04, 0)
                    batt_l = raw_vals.get(0x40, 0)
                    raw_batt = (batt_h << 8) | batt_l
                    calc_batt = round(raw_batt / 50.216, 2) if raw_batt > 0 else 0.0

                    print(f"[{frame_count:05d} | {record['elapsed']:6.1f}s] RPM: {calc_rpm:4d} r/min | Batt: {calc_batt:5.2f}V | Opcodes Polled: {len(raw_vals):2d}", end="\r")

                # Sleep to maintain requested Hz polling rate
                elapsed = time.time() - loop_start
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n" + "-" * 80)
        logger.info("Logging stopped by user (Ctrl+C).")
    finally:
        reader.close()
        total_time = time.time() - start_time
        avg_rate = frame_count / total_time if total_time > 0 else 0.0
        print("\n" + "=" * 80)
        print("  ✅ YDS RAW LOGGING COMPLETE")
        print(f"  📁 File: {os.path.abspath(args.output)}")
        print(f"  📊 Total Frames Logged: {frame_count}")
        print(f"  ⏱️  Duration: {total_time:.2f} seconds ({avg_rate:.2f} Hz avg)")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    log_raw_telemetry()
