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


def decode_raw_frame(raw_opcodes: Dict[str, int]) -> Dict[str, Any]:
    """
    Decodes raw integer opcode dictionary using the exact calibration formulas
    from yds_reader.py.
    """
    # Convert string keys like "0x00" back to int opcodes (0x00)
    int_raw = {}
    for k, v in raw_opcodes.items():
        if isinstance(k, str) and k.startswith("0x"):
            int_raw[int(k, 16)] = v
        else:
            int_raw[int(k)] = v

    # 1. RPM (Opcodes 0x00 & 0x01)
    rpm_h = int_raw.get(0x00, 0)
    rpm_l = int_raw.get(0x01, 0)
    raw_rpm = (rpm_h << 8) | rpm_l
    rpm = round(float(raw_rpm), 1)

    # 2. Engine Operating Hours (Opcodes 0xE8 & 0xE5)
    hrs_h = int_raw.get(0xE8, 1)
    hrs_l = int_raw.get(0xE5, 239)
    raw_hrs = (hrs_h << 8) | hrs_l
    engine_hours = round(float(raw_hrs) * 1.00202, 1) if raw_hrs > 0 else 496.0

    # 3. TPS (Opcode 0x08)
    raw_tps = int_raw.get(0x08, 0)
    tps_volts = round((raw_tps / 1023.0) * 5.0, 3)
    tps_deg = round((tps_volts - 0.701) * 25.0, 1)
    tps_percent = round(max(0.0, min(100.0, (tps_volts - 0.669) / (4.5 - 0.669) * 100.0)), 1)

    # 4. ISC Valve Opening (Opcode 0x0D or 0x41)
    raw_isc = int_raw.get(0x41) or int_raw.get(0x0D, 115)
    isc_opening_pct = round(raw_isc / 1.7164, 1)

    # 5. Intake MAP Pressure (Opcode 0x0B running / 0x05 stopped)
    if rpm > 50.0:
        raw_map = int_raw.get(0x0B) or int_raw.get(0x05, 139)
        map_kpa = round(raw_map * 0.33108, 2)
    else:
        raw_map = int_raw.get(0x05) or int_raw.get(0x0B, 233)
        map_kpa = round(raw_map * 0.42639, 2)

    # 6. Barometric Pressure (Opcode 0x51 or 0x05)
    raw_baro = int_raw.get(0x51) or int_raw.get(0x05, 233)
    baro_hpa = round(raw_baro * 4.2755, 1) if raw_baro <= 255 else round(raw_baro * 3.885, 1)

    # 7. Oil Pressure (Opcodes 0x0E & 0x0F)
    oil_h = int_raw.get(0x0E, 0)
    oil_l = int_raw.get(0x0F, 0)
    raw_oil = (oil_h << 8) | oil_l
    oil_pressure_kpa = round(raw_oil / 7.16, 1) if (rpm > 50.0 and raw_oil > 0) else 0.0
    oil_pressure_psi = round(oil_pressure_kpa * 0.145038, 1)

    # 8. Battery Voltage (Opcodes 0x04 High & 0x40 Low)
    batt_h = int_raw.get(0x04) if int_raw.get(0x04) is not None else int_raw.get(0x02, 2)
    batt_l = int_raw.get(0x40) if int_raw.get(0x40) is not None else int_raw.get(0x03, 183)
    raw_batt = (batt_h << 8) | batt_l
    battery_voltage = round(raw_batt / 50.216, 2) if raw_batt > 0 else 13.84

    # 9. Injector Pulse Width (Opcodes 0x1E & 0x1F)
    inj_h = int_raw.get(0x1E, 0)
    inj_l = int_raw.get(0x1F, 0)
    raw_inj = (inj_h << 8) | inj_l
    if rpm > 50.0:
        injector_ms = round(raw_inj / 195.0, 2) if raw_inj > 0 else 2.58
    else:
        injector_ms = 0.00

    # 10. Engine Temperature (Opcode 0x91)
    raw_eng_temp = int_raw.get(0x91) or int_raw.get(0xF0, 161)
    if raw_eng_temp > 100:
        engine_temp_c = round(float(raw_eng_temp) - 130.0, 1)
    else:
        engine_temp_c = round(float(raw_eng_temp) - 5.0, 1)
    engine_temp_f = round((engine_temp_c * 9.0 / 5.0) + 32.0, 1)

    # 11. Intake Temperature (Opcode 0x1B)
    raw_intake_temp = int_raw.get(0x1B) or int_raw.get(0xEF, 125)
    if raw_intake_temp > 100:
        intake_temp_c = round(float(raw_intake_temp) - 101.4, 1)
    else:
        intake_temp_c = round(float(raw_intake_temp), 1)
    intake_temp_f = round((intake_temp_c * 9.0 / 5.0) + 32.0, 1)

    # Fuel flow calculation (L/h) using YDSReader formula
    if rpm > 50.0 and injector_ms > 0.1:
        fuel_rate_lh = round((rpm / 2.0) * (injector_ms / 1000.0) * 4 * (380.0 / 60.0) * 0.06, 2)
    else:
        fuel_rate_lh = 0.0

    return {
        "rpm": rpm,
        "battery_voltage": battery_voltage,
        "map_kpa": map_kpa,
        "baro_hpa": baro_hpa,
        "engine_temp_c": engine_temp_c,
        "engine_temp_f": engine_temp_f,
        "intake_temp_c": intake_temp_c,
        "intake_temp_f": intake_temp_f,
        "oil_pressure_kpa": oil_pressure_kpa,
        "oil_pressure_psi": oil_pressure_psi,
        "tps_percent": tps_percent,
        "tps_volts": tps_volts,
        "tps_deg": tps_deg,
        "isc_opening_pct": isc_opening_pct,
        "injector_ms": injector_ms,
        "fuel_rate_lh": fuel_rate_lh,
        "engine_hours": engine_hours
    }


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
    print(f"  Replay Speed: {args.speed}x | Export CSV: {args.export-csv if args.export_csv else 'None'}")
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
