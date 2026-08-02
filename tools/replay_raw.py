#!/usr/bin/env python3
"""
Yamaha Diagnostic System (YDS) Raw Telemetry Replayer & Calibration Tester.
Reads logged raw ECU opcode JSON Lines (.jsonl) files and runs them through
the YDSReader calibration engine to verify telemetry calculations, test formula changes,
or export CSV files.

Usage:
  python3 replay_raw.py --input logs/raw_ecu_20260729_144400.jsonl
  python3 replay_raw.py --input logs/raw_ecu_20260729_144400.jsonl --export-csv calibration_test.csv
  python3 replay_raw.py --input logs/raw_ecu_20260729_144400.jsonl --speed 2.0
"""

import os
import sys
import time
import json
import csv
import argparse
import logging
from typing import Dict, Any, List

# Ensure app directory is in sys.path for yds_reader import
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

try:
    from yds_reader import YDSReader
except ImportError:
    print("Error: yds_reader module not found in app directory.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("replay_raw")


def decode_raw_frame(raw_opcodes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delegates decoding to YDSReader.decode_raw_frame (single source of truth).
    """
    return YDSReader.decode_raw_frame(raw_opcodes)


def replay_raw_log():
    parser = argparse.ArgumentParser(description="Replay logged raw Yamaha YDS ECU opcode telemetry.")
    parser.add_argument("--input", required=True, help="Input JSONL raw telemetry file path")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (1.0 = real-time, 0 = instant)")
    parser.add_argument("--export-csv", default=None, help="Optional output CSV filepath to export calibrated data")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    print("\n" + "=" * 90)
    print(f"  🎬 REPLAYING RAW YDS TELEMETRY -> {args.input}")
    print(f"  Replay Speed: {args.speed}x | Export CSV: {args.export_csv if args.export_csv else 'None'}")
    print("=" * 90 + "\n")

    frames: List[Dict[str, Any]] = []
    header_info = {}

    with open(args.input, "r", encoding="utf-8") as infile:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "header":
                    header_info = data
                elif data.get("type") == "frame" or "raw_opcodes" in data:
                    frames.append(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping invalid JSON line: {e}")

    logger.info(f"Loaded {len(frames)} raw opcode frames from {args.input}")

    if header_info:
        print(f"  ECU Model: {header_info.get('ecu_model', 'N/A')} | Recorded: {header_info.get('iso_start', 'N/A')}")
        print(f"  Target Rate: {header_info.get('polling_rate_hz', 'N/A')} Hz\n")

    csv_writer = None
    csv_file = None
    if args.export_csv:
        csv_file = open(args.export_csv, "w", newline="", encoding="utf-8")
        fieldnames = [
            "frame", "elapsed_s", "rpm", "battery_v", "map_kpa", "baro_hpa",
            "eng_temp_c", "intake_temp_c", "oil_kpa", "tps_pct", "isc_pct",
            "inj_ms", "fuel_lh", "hours"
        ]
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        csv_writer.writeheader()

    prev_timestamp = None
    start_time = time.time()

    for idx, frame_entry in enumerate(frames):
        raw_opcodes = frame_entry.get("raw_opcodes", {})
        curr_timestamp = frame_entry.get("timestamp", time.time())
        elapsed = frame_entry.get("elapsed", idx * 0.2)

        # Calculate time delay for real-time replay simulation
        if args.speed > 0 and prev_timestamp is not None:
            time_delta = (curr_timestamp - prev_timestamp) / args.speed
            if 0 < time_delta < 2.0:
                time.sleep(time_delta)
        prev_timestamp = curr_timestamp

        decoded = decode_raw_frame(raw_opcodes)

        # Print detailed calibrated frame summary
        print(
            f"Frame #{idx+1:04d} [{elapsed:6.1f}s] | "
            f"RPM: {int(decoded['rpm']):4d} r/min | "
            f"Batt: {decoded['battery_voltage']:5.2f}V | "
            f"MAP: {decoded['map_kpa']:5.2f} kPa | "
            f"Temp: {decoded['engine_temp_c']:4.1f}°C | "
            f"Oil: {decoded['oil_pressure_kpa']:5.1f} kPa | "
            f"Fuel: {decoded['fuel_rate_lh']:4.2f} L/h | "
            f"Hours: {decoded['engine_hours']:5.1f} HRS"
        )

        if csv_writer:
            csv_writer.writerow({
                "frame": idx + 1,
                "elapsed_s": elapsed,
                "rpm": decoded["rpm"],
                "battery_v": decoded["battery_voltage"],
                "map_kpa": decoded["map_kpa"],
                "baro_hpa": decoded["baro_hpa"],
                "eng_temp_c": decoded["engine_temp_c"],
                "intake_temp_c": decoded["intake_temp_c"],
                "oil_kpa": decoded["oil_pressure_kpa"],
                "tps_pct": decoded["tps_percent"],
                "isc_pct": decoded["isc_opening_pct"],
                "inj_ms": decoded["injector_ms"],
                "fuel_lh": decoded["fuel_rate_lh"],
                "hours": decoded["engine_hours"]
            })

    if csv_file:
        csv_file.close()
        logger.info(f"Exported calibrated telemetry to CSV: {args.export_csv}")

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 90)
    print("  ✅ REPLAY COMPLETE")
    print(f"  Total Frames Processed: {len(frames)}")
    print(f"  Replay Duration: {total_elapsed:.2f} seconds")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    replay_raw_log()
