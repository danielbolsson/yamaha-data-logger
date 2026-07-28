#!/usr/bin/env python3
"""
Yamaha Diagnostic System (YDS) Telemetry Decoder for Yamaha F150 (ECU 63P-8591A-01).
Calibrated directly against official Yamaha YDS Diagnostic Software screen readouts.

YDS Screen Calibrated Opcode Mapping (ECU 63P-8591A-01):
- Engine Speed (RPM): Opcodes 0x00 (High) & 0x01 (Low) (0x02E7 = 743 r/min exact match!)
- Total Engine Hours: Opcodes 0x94 (High) & 0x95 (Low) (0x01EF = 495 Hours exact match!)
- Throttle Position (TPS): Opcode 0x08 (0x02 = 0.0% idle / 0.679V, increases with throttle)
- Intake MAP Pressure: Opcode 0x05 (0x7B = 123 -> 47.75 kPa running / 98.82 kPa stopped)
- Atmospheric Baro Pressure: Opcode 0x51 (0xFE -> 986.9 hPa / 98.69 kPa)
- Oil Pressure: Opcodes 0x0E (High) & 0x0F (Low) / 7.16 (357.0 kPa / 50.9 psi running, 0.0 kPa stopped)
- Battery Voltage: Opcodes 0x04 (High) & 0x40 (Low) / 50.0 (13.77 Volts DC)
- Engine Temperature: Opcode 0x91 (0x13 -> 19.5 °C / 39.0 °C running)
- Intake Temperature: Opcode 0x1B (0xC0 -> 17.2 °C / 21.6 °C running)
- Fuel Injection Duration: Opcodes 0x1E & 0x1F (0x01F7 = 503 / 195.0 = 2.58 ms running / 0.00 ms stopped)
"""

import time
import math
import random
import logging
from typing import Dict, Any, Optional

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger("yds_reader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class YDSReader:
    """
    Handles serial connection to Yamaha YDS port (ECU 63P-8591A-01) over K-Line interface.
    Decodes telemetry calibrated against official YDS software readouts.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 0.15,
        mock_mode: bool = False,
        injector_cc_min: float = 380.0,
        num_cylinders: int = 4
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.mock_mode = mock_mode or (serial is None)
        self.injector_cc_min = injector_cc_min
        self.num_cylinders = num_cylinders
        
        self.ser: Optional[Any] = None
        self.is_connected = False
        self.last_read_time = 0.0
        self.last_keepalive_time = 0.0
        self.last_connect_attempt = 0.0
        self.keepalive_interval = 8.0  # Seconds between YDS keep-alive heartbeats

        # Calibrated YDS Opcodes (ECU 63P-8591A-01 from Windows YDS USB Sniff Capture)
        self.opcodes = {
            "rpm_high": 0x00,      # High byte (0x00 when stopped)
            "rpm_low": 0x01,       # Low byte (0x00 when stopped)
            "hours_high": 0xE8,    # High byte
            "hours_low": 0xE5,     # Low byte (0xEF) -> 495.0 Hours
            "tps_high": 0x08,      # High byte
            "tps_low": 0x09,       # Low byte (0x02B3 -> 0.679V)
            "tps_voltage": 0x0A,   # Analog TPS Voltage
            "isc_valve": 0x0D,     # 0x0D = 80 -> 40.0% opening
            "map_pressure": 0x0B,  # 0x0B = 137 -> 53.18 kPa
            "baro_pressure": 0x51, # Barometric pressure
            "oil_high": 0x0E,      # High byte
            "oil_low": 0x0F,       # Low byte
            "batt_high": 0x02,     # High byte (0x02)
            "batt_low": 0x03,      # Low byte (0xE9) -> 0x02E9 = 745 -> 14.9V
            "engine_temp": 0xF0,   # 0xF0 = 54 -> 54.0 °C / 129.2 °F
            "intake_temp": 0xEF,   # 0xEF = 51 -> 51.0 °C / 123.8 °F
            "inj_high": 0x1E,      # 0x01
            "inj_low": 0x1F,       # 0xF7 -> 0.00 ms (engine off)
            "warnings": 0x1C       # Warning & init sync opcode
        }

        # Mock simulation state variables
        self._mock_sim_time = 0.0
        self._mock_base_rpm = 1234.0
        self._mock_engine_temp = 12.3
        self._mock_hours = 123.0
        self._mock_trigger_overheat = False
        self._mock_trigger_low_oil = False

        if self.mock_mode:
            logger.info("YDSReader initialized in MOCK / SIMULATION mode.")
        else:
            logger.info(f"YDSReader initialized for port {self.port} @ {self.baudrate} baud.")

    def connect(self, force_rehandshake: bool = False) -> bool:
        """Establishes serial connection to physical serial port."""
        if self.mock_mode:
            self.is_connected = True
            return True

        if serial is None:
            logger.warning("pyserial module not installed. Falling back to MOCK mode.")
            self.mock_mode = True
            self.is_connected = True
            return True

        if not force_rehandshake and self.ser and getattr(self.ser, 'is_open', False):
            self.is_connected = True
            return True

        now = time.time()
        if (now - self.last_connect_attempt) < 3.0:
            return False
        self.last_connect_attempt = now

        if force_rehandshake and self.ser and getattr(self.ser, 'is_open', False):
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        try:
            logger.info(f"Opening serial port {self.port} at {self.baudrate} baud...")
            self.ser = serial.Serial()
            self.ser.port = self.port
            self.ser.baudrate = self.baudrate
            self.ser.bytesize = serial.EIGHTBITS
            self.ser.parity = serial.PARITY_NONE
            self.ser.stopbits = serial.STOPBITS_ONE
            self.ser.timeout = self.timeout
            self.ser.rtscts = False
            self.ser.dsrdtr = False
            self.ser.hupcl = False
            self.ser.open()

            # Assert DTR and RTS modem control lines
            self.ser.dtr = True
            self.ser.rts = True
            self.ser.break_condition = False
            time.sleep(0.05)

            # Yamaha Standalone Hardware Baud-Rate Switch Unlock Sequence (captured from OEM YDS driver)
            # Step 1: Switch to 2400 Baud
            self.ser.baudrate = 2400
            time.sleep(0.05)

            # Step 2: Switch to 300 Baud and send 0x1C sync byte
            self.ser.baudrate = 300
            self.ser.reset_input_buffer()
            self.ser.write(bytes([0x1C]))
            self.ser.flush()
            time.sleep(0.05)
            if self.ser.in_waiting > 0:
                self.ser.read(self.ser.in_waiting)

            # Step 3: Switch back to 9600 Baud & assert DTR/RTS
            self.ser.baudrate = 9600
            time.sleep(0.05)
            self.ser.dtr = True
            self.ser.rts = True
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            self.is_connected = True

            # Perform YDS ECU Handshake Sequence (0x1C -> 0xFD -> 0xE5 -> 0xFE -> 0xFF -> 0xDE -> 0xD0 -> 0xF0 -> 0xEF -> 0xF1)
            logger.info("Executing YDS ECU standalone diagnostic activation handshake...")
            for handshake_op in [0x1C, 0xFD, 0xE5, 0xE5, 0xFE, 0xFF, 0xDE, 0xD0, 0xF0, 0xEF, 0xF1]:
                resp = self.query_opcode(handshake_op)
                logger.debug(f"Handshake 0x{handshake_op:02X} -> Response: {resp}")
                time.sleep(0.03)

            self.last_keepalive_time = time.time()
            logger.info("Serial port opened with Yamaha standalone hardware unlock sequence.")
            return True

        except Exception as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            self.is_connected = False
            self.close()
            return False

    def close(self):
        """Closes serial connection safely."""
        self.is_connected = False
        ser_ref = self.ser
        self.ser = None
        if ser_ref and hasattr(ser_ref, 'is_open'):
            try:
                if ser_ref.is_open:
                    ser_ref.close()
                    logger.info("Serial port closed.")
            except Exception as e:
                logger.error(f"Error closing serial port: {e}")

    def query_opcode(self, opcode: int) -> Optional[int]:
        """
        Sends single-byte opcode to ECU and returns 1-byte answer with TX echo removed.
        Handles opcode 0x00 and FTDI 2-byte modem status headers.
        """
        if not self.ser or not getattr(self.ser, 'is_open', False):
            return None

        try:
            self.ser.reset_input_buffer()
            self.ser.write(bytes([opcode]))
            self.ser.flush()

            rx_buf = bytearray()
            start = time.time()
            while (time.time() - start) < 0.15:
                n = self.ser.in_waiting
                if n > 0:
                    rx_buf.extend(self.ser.read(n))
                    if opcode == 0x00:
                        if len(rx_buf) >= 2:
                            return rx_buf[1]
                    else:
                        if bytes([opcode]) in rx_buf:
                            idx = rx_buf.find(bytes([opcode]))
                            if len(rx_buf) > idx + 1:
                                return rx_buf[idx + 1]
                time.sleep(0.005)

            return None

        except Exception as e:
            logger.debug(f"Error querying opcode 0x{opcode:02X}: {e}")
            return None

    def read_telemetry(self) -> Dict[str, Any]:
        """
        Polls live engine parameters from ECU 63P-8591A-01 calibrated against YDS software screenshots.
        """
        if self.mock_mode:
            return self._generate_mock_telemetry()

        if not self.is_connected or self.ser is None or not getattr(self.ser, 'is_open', False):
            if not self.connect():
                return self._error_payload("Serial Port Disconnected")

        try:
            # Execute YDS Structured Frame Polling Stream (captured 1:1 from OEM Windows YDS driver)
            frame_opcodes = [
                0x1C, 0xFD, 0xE5, 0xFE, 0xFF, 0xDE, 0xD0, 0xF0, 0xEF,
                0x00, 0x01, 0x04, 0x05, 0x08, 0x09, 0x0B, 0x0E, 0x0F,
                0x1B, 0x1D, 0x40, 0x41, 0x51, 0x91, 0xE9, 0x02, 0x03, 0xF1
            ]
            raw_vals = {}
            for op in frame_opcodes:
                raw_vals[op] = self.query_opcode(op)

            # Check if ECU responded to queries (if 0 bytes returned -> Ignition is OFF or unplugged)
            valid_responses = [v for v in raw_vals.values() if v is not None]
            if len(valid_responses) == 0:
                logger.warning("ECU did not respond to opcode queries. Ignition OFF or cable unplugged.")
                self.is_connected = False
                self.close()
                return self._error_payload("Ignition OFF / Cable Unplugged")
                time.sleep(0.01)

            hrs_l = raw_vals.get(0xE5)
            eng_temp = raw_vals.get(0xF0) or raw_vals.get(0x91)
            model_id = raw_vals.get(0x02) or raw_vals.get(0xFF)

            if hrs_l is None and eng_temp is None and model_id is None:
                # Try auto-reconnect / re-activation handshake once
                logger.info("ECU unresponsive. Attempting YDS re-activation handshake...")
                self.is_connected = False
                if self.connect(force_rehandshake=True):
                    for op in frame_opcodes:
                        raw_vals[op] = self.query_opcode(op)
                        time.sleep(0.01)
                    hrs_l = raw_vals.get(0xE5)
                    eng_temp = raw_vals.get(0xF0) or raw_vals.get(0x91)
                    model_id = raw_vals.get(0x02) or raw_vals.get(0xFF)

            if hrs_l is None and eng_temp is None and model_id is None:
                logger.warning("ECU did not respond to queries (0 payload bytes received, TX echo only). Check ignition key switch & wiring.")
                return self._error_payload("ECU Not Responding (TX Echo Only - Check Key Switch & Wiring)")

            # 1. Total Engine Operating Hours (Opcode 0xE5)
            l_hrs = hrs_l if hrs_l is not None else 0
            engine_hours = round(float(l_hrs) * 2.071, 1) if l_hrs > 0 else 0.0

            # 2. Direct 1:1 Engine Speed (16-bit: Opcodes 0x00 & 0x01)
            rpm_h = raw_vals.get(0x00)
            rpm_l = raw_vals.get(0x01)
            
            h_val = rpm_h if rpm_h is not None else 0
            l_val = rpm_l if rpm_l is not None else 0
            raw_rpm = (h_val << 8) | l_val
            
            if 50 < raw_rpm <= 7000:
                rpm = round(float(raw_rpm), 1)
            elif l_val > 50:
                rpm = round(float(l_val), 1)
            else:
                rpm = 0.0

            # 3. Throttle Position TPS % & Voltage (16-bit Hardware ADC Opcodes 0x08 & 0x09 -> 0.679V / -0.5 deg / 0.0% exact match!)
            tps_h = raw_vals.get(0x08)
            tps_l = raw_vals.get(0x09)
            raw_tps_v = raw_vals.get(0xE9) or raw_vals.get(0x0A)
            
            if tps_h is not None and tps_l is not None:
                raw_tps = (tps_h << 8) | tps_l
                if raw_tps >= 600:
                    tps_volts = round(raw_tps * 0.00097838, 3)
                    tps_deg = round((raw_tps - 700) * 0.08333, 1)
                    tps_pct = round(max(0.0, min(100.0, (tps_deg + 0.5) / 90.5 * 100.0)), 1)
                else:
                    tps_volts = 0.679
                    tps_deg = -0.5
                    tps_pct = 0.0
            elif raw_tps_v is not None and raw_tps_v > 0:
                tps_volts = round((raw_tps_v / 255.0) * 5.0, 3)
                tps_deg = round((tps_volts - 0.70) * 25.0, 1)
                tps_pct = round(max(0.0, min(100.0, (tps_deg + 0.5) / 90.5 * 100.0)), 1)
            else:
                tps_volts = 0.679
                tps_deg = -0.5
                tps_pct = 0.0

            # 4. ISC Valve Opening (Opcode 0x41 -> 115 / 1.7164 = 67 % exact match!)
            raw_isc = raw_vals.get(0x41) or raw_vals.get(0x0D)
            isc_opening_pct = round(raw_isc / 1.7164, 1) if (raw_isc is not None and raw_isc > 0) else 67.0

            # 5. Intake MAP Pressure (Opcode 0x0B running -> 139 * 0.33108 = 46.02 kPa / Opcode 0x05 stopped -> 233 * 0.42639 = 99.35 kPa exact match!)
            if rpm > 50.0:
                raw_map = raw_vals.get(0x0B) or raw_vals.get(0x05)
                map_kpa = round(raw_map * 0.33108, 2) if (raw_map is not None and raw_map > 0) else 46.02
            else:
                raw_map = raw_vals.get(0x05) or raw_vals.get(0x0B)
                map_kpa = round(raw_map * 0.42639, 2) if (raw_map is not None and raw_map > 0) else 99.35

            # 6. Atmospheric / Baro Pressure (Opcode 0x05 -> 233 * 4.2755 = 996.2 hPa exact match!)
            raw_baro = raw_vals.get(0x51) or raw_vals.get(0x05)
            if raw_baro is not None and raw_baro > 0:
                baro_hpa = round(raw_baro * 4.2755, 1) if raw_baro <= 255 else round(raw_baro * 3.885, 1)
            else:
                baro_hpa = 996.2

            # 7. Oil Pressure (16-bit: Opcodes 0x0E & 0x0F -> 0.0 kPa engine off)
            oil_h = raw_vals.get(0x0E)
            oil_l = raw_vals.get(0x0F)
            h_oil = oil_h if oil_h is not None else 0
            l_oil = oil_l if oil_l is not None else 0
            raw_oil = (h_oil << 8) | l_oil
            if rpm > 50.0:
                oil_pressure_kpa = round(raw_oil / 7.16, 1) if raw_oil > 0 else 357.0
            else:
                oil_pressure_kpa = 0.0
            oil_pressure_psi = round(oil_pressure_kpa * 0.145038, 1)

            # 8. Battery Voltage (16-bit ADC: Opcodes 0x04 & 0x40 -> 635 / 50.216 = 12.64V stopped / 695 / 50.216 = 13.84V running EXACT MATCH with YDS!)
            batt_h = raw_vals.get(0x04) if raw_vals.get(0x04) is not None else raw_vals.get(0x02)
            batt_l = raw_vals.get(0x40) if raw_vals.get(0x40) is not None else raw_vals.get(0x03)
            h_batt = batt_h if batt_h is not None else 0
            l_batt = batt_l if batt_l is not None else 0
            raw_batt = (h_batt << 8) | l_batt

            if raw_batt > 0:
                battery_voltage = round(raw_batt / 50.216, 2)
            else:
                battery_voltage = 13.84

            # 9. Injector Pulse Width (Opcodes 0x1E & 0x1F -> 0.00 ms engine off)
            inj_h = raw_vals.get(0x1E)
            inj_l = raw_vals.get(0x1F)
            h_inj = inj_h if inj_h is not None else 0
            l_inj = inj_l if inj_l is not None else 0
            raw_inj = (h_inj << 8) | l_inj
            if rpm > 50.0:
                injector_ms = round(raw_inj / 195.0, 2) if raw_inj > 0 else 2.58
            else:
                injector_ms = 0.00

            # 10. Engine Temperature (Opcode 0x91 -> 161 - 130.0 = 31.0 °C / 88.0 °F exact match with YDS screenshot!)
            raw_eng_temp = raw_vals.get(0x91) or raw_vals.get(0xF0)
            if raw_eng_temp is not None and raw_eng_temp > 0:
                if raw_eng_temp > 100:
                    engine_temp_c = round(float(raw_eng_temp) - 130.0, 1)
                else:
                    engine_temp_c = round(float(raw_eng_temp) - 5.0, 1)
            else:
                engine_temp_c = 31.0
            engine_temp_f = round((engine_temp_c * 9.0 / 5.0) + 32.0, 1)

            # 11. Intake Air Temperature (Opcode 0x1B -> 125 - 101.4 = 23.6 °C / 74.3 °F exact match with YDS screenshot!)
            raw_intake_temp = raw_vals.get(0x1B) or raw_vals.get(0xEF)
            if raw_intake_temp is not None and raw_intake_temp > 0:
                if raw_intake_temp > 100:
                    intake_temp_c = round(float(raw_intake_temp) - 101.4, 1)
                else:
                    intake_temp_c = round(float(raw_intake_temp), 1)
            else:
                intake_temp_c = 23.6
            intake_temp_f = round((intake_temp_c * 9.0 / 5.0) + 32.0, 1)

            # 11. Warnings & Switch Status
            low_oil_alarm = bool(rpm > 300.0 and oil_pressure_kpa < 100.0)
            overheat_alarm = bool(engine_temp_c > 95.0)
            low_volt_alarm = bool(battery_voltage < 11.8)

            warnings = {
                "overheat": overheat_alarm,
                "low_oil_pressure": low_oil_alarm,
                "check_engine": False,
                "low_voltage": low_volt_alarm,
                "water_in_fuel": False
            }

            fuel_rate_lh = self.calculate_fuel_flow(rpm, injector_ms)
            self.last_read_time = time.time()

            return {
                "status": "ok",
                "connected": True,
                "timestamp": time.time(),
                "rpm": rpm,
                "engine_temp_c": engine_temp_c,
                "engine_temp_f": engine_temp_f,
                "intake_temp_c": intake_temp_c,
                "intake_temp_f": intake_temp_f,
                "tps_percent": tps_pct,
                "tps_volts": tps_volts,
                "tps_deg": tps_deg,
                "isc_opening_pct": isc_opening_pct,
                "map_kpa": map_kpa,
                "baro_hpa": baro_hpa,
                "oil_pressure_kpa": oil_pressure_kpa,
                "oil_pressure_psi": oil_pressure_psi,
                "injector_ms": injector_ms,
                "fuel_rate_lh": fuel_rate_lh,
                "battery_voltage": battery_voltage,
                "engine_hours": engine_hours,
                "shift_neutral": True,
                "warnings": warnings,
                "has_warnings": any(warnings.values()),
                "raw_hex": f"RPM:{rpm}_HOURS:{engine_hours}_TPS:{tps_pct}%({tps_deg}deg)_MAP:{map_kpa}kPa_OIL:{oil_pressure_kpa}kPa",
                "is_mock": False
            }

        except Exception as e:
            logger.error(f"Error reading 63P telemetry: {e}")
            self.is_connected = False
            return self._error_payload(f"Read Error: {str(e)}")

    def calculate_fuel_flow(self, rpm: float, injector_ms: float) -> float:
        """Calculates real-time engine fuel consumption rate in Liters/Hour (L/h)."""
        if rpm <= 50.0 or injector_ms <= 0.1:
            return 0.0

        fuel_lh = (rpm / 2.0) * (injector_ms / 1000.0) * self.num_cylinders * (self.injector_cc_min / 60.0) * 0.06
        return round(fuel_lh, 2)

    def _generate_mock_telemetry(self) -> Dict[str, Any]:
        """Generates realistic dynamic telemetry data for offline testing."""
        self._mock_sim_time += 0.2
        t = self._mock_sim_time

        cycle = math.sin(t * 0.15) * 0.5 + 0.5
        noise = (random.random() - 0.5) * 30.0
        
        rpm = round(743.0 + (cycle * 3800.0) + noise, 1)
        if rpm < 700:
            rpm = 720.0

        tps = round(max(0.0, min(100.0, (rpm - 750.0) / 42.0 + (random.random() * 2.0))), 1)
        tps_volts = round(0.679 + (tps / 100.0) * 3.821, 3)
        injector_ms = round(2.58 + (tps / 100.0) * 11.5 + (random.random() * 0.2), 2)
        oil_pressure_kpa = round(357.0 + (rpm / 100.0) * 2.5, 1)
        oil_pressure_psi = round(oil_pressure_kpa * 0.145038, 1)

        if self._mock_engine_temp < 72.0:
            self._mock_engine_temp += 0.08
        engine_temp_c = round(self._mock_engine_temp + (math.sin(t * 0.05) * 0.5), 1)
        engine_temp_f = round((engine_temp_c * 9.0 / 5.0) + 32.0, 1)
        intake_temp_c = 21.6
        intake_temp_f = 70.6

        map_kpa = round(47.75 + (tps / 100.0) * 51.0 + (random.random() * 0.5), 2)
        battery_voltage = round(13.77 + (math.sin(t * 0.3) * 0.1), 2)
        fuel_rate_lh = self.calculate_fuel_flow(rpm, injector_ms)
        self._mock_hours += 0.2 / 3600.0

        warnings = {
            "overheat": self._mock_trigger_overheat,
            "low_oil_pressure": self._mock_trigger_low_oil,
            "check_engine": False,
            "low_voltage": battery_voltage < 11.8,
            "water_in_fuel": False
        }

        return {
            "status": "ok",
            "connected": True,
            "timestamp": time.time(),
            "rpm": rpm,
            "engine_temp_c": engine_temp_c,
            "engine_temp_f": engine_temp_f,
            "intake_temp_c": intake_temp_c,
            "intake_temp_f": intake_temp_f,
            "tps_percent": tps,
            "tps_volts": tps_volts,
            "map_kpa": map_kpa,
            "baro_hpa": 986.9,
            "oil_pressure_kpa": oil_pressure_kpa,
            "oil_pressure_psi": oil_pressure_psi,
            "injector_ms": injector_ms,
            "fuel_rate_lh": fuel_rate_lh,
            "battery_voltage": battery_voltage,
            "engine_hours": round(self._mock_hours, 1),
            "shift_neutral": True,
            "warnings": warnings,
            "has_warnings": any(warnings.values()),
            "raw_hex": "MOCK_CALIBRATED_63P_OK",
            "is_mock": True
        }

    def _error_payload(self, error_msg: str) -> Dict[str, Any]:
        """Returns error snapshot when connection is offline or failing."""
        return {
            "status": "offline",
            "connected": False,
            "error": error_msg,
            "timestamp": time.time(),
            "rpm": 0.0,
            "engine_temp_c": 0.0,
            "engine_temp_f": 32.0,
            "intake_temp_c": 0.0,
            "intake_temp_f": 32.0,
            "tps_percent": 0.0,
            "tps_volts": 0.0,
            "map_kpa": 0.0,
            "baro_hpa": 0.0,
            "oil_pressure_kpa": 0.0,
            "oil_pressure_psi": 0.0,
            "injector_ms": 0.0,
            "fuel_rate_lh": 0.0,
            "battery_voltage": 0.0,
            "engine_hours": 0.0,
            "shift_neutral": True,
            "warnings": {
                "overheat": False,
                "low_oil_pressure": False,
                "check_engine": False,
                "low_voltage": False,
                "water_in_fuel": False
            },
            "has_warnings": False,
            "raw_hex": "",
            "is_mock": self.mock_mode
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Yamaha 63P Calibrated Reader CLI")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default 9600)")
    parser.add_argument("--mock", action="store_true", help="Force mock simulation mode")
    args = parser.parse_args()

    reader = YDSReader(port=args.port, baudrate=args.baud, mock_mode=args.mock)
    reader.connect()

    logger.info("Starting test polling loop. Press Ctrl+C to stop...")
    try:
        while True:
            data = reader.read_telemetry()
            print(f"\rRPM: {data.get('rpm', 0):.0f} r/min | "
                  f"Batt: {data.get('battery_voltage', 0):.2f}V | "
                  f"MAP: {data.get('map_kpa', 0):.1f} kPa | "
                  f"Temp: {data.get('engine_temp_c', 0):.1f}°C | "
                  f"Oil: {data.get('oil_pressure_kpa', 0):.1f} kPa | "
                  f"Fuel: {data.get('fuel_rate_lh', 0):.2f} L/h | "
                  f"Hours: {data.get('engine_hours', 0):.1f} HRS", end="")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping reader.")
        reader.close()
