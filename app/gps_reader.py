#!/usr/bin/env python3
"""
NMEA 0183 GPS / GNSS Receiver Interface for u-blox 7 & USB ACM Serial Devices.
Parses $GPRMC, $GNRMC, $GPGGA, $GPVTG sentences for Speed Over Ground (Knots/kmh),
Course Over Ground (Heading deg), Satellites in View, and Fix Status.
"""

import os
import time
import math
import random
import logging
import threading
import datetime
import subprocess
from typing import Dict, Any, Optional

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger("gps_reader")


class GPSReader:
    """
    Handles serial connection to USB GPS receiver (/dev/ttyACM0 by default).
    Parses NMEA 0183 sentences for marine speed (Knots), heading, and fix status.
    """

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baudrate: int = 9600,
        timeout: float = 0.5,
        mock_mode: bool = False
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.mock_mode = mock_mode or (serial is None)

        self.ser: Optional[Any] = None
        self.is_connected = False
        self.last_connect_attempt = 0.0

        # Latest Parsed GPS Metrics State
        self.speed_knots = 0.0
        self.speed_kmh = 0.0
        self.speed_mph = 0.0
        self.track_deg = 0.0
        self.cardinal_heading = "N"
        self.satellites = 0
        self.fix_quality = 0
        self.has_fix = False
        self.latitude = 0.0
        self.longitude = 0.0
        self.last_fix_time = 0.0

        # GPS Time & System Clock Synchronization State
        self.last_gps_utc_timestamp: Optional[float] = None
        self.last_clock_sync_check: float = 0.0
        self.last_clock_sync_time: float = 0.0
        self.clock_drift_seconds: float = 0.0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        if self.mock_mode:
            logger.info("GPSReader initialized in MOCK / SIMULATION mode.")
        else:
            logger.info(f"GPSReader initialized for port {self.port} @ {self.baudrate} baud.")

    def connect(self) -> bool:
        """Establishes connection to USB serial GPS receiver."""
        if self.mock_mode:
            self.is_connected = True
            return True

        if serial is None:
            logger.warning("pyserial module not installed. Falling back to GPS MOCK mode.")
            self.mock_mode = True
            self.is_connected = True
            return True

        if self.ser and getattr(self.ser, 'is_open', False):
            self.is_connected = True
            return True

        now = time.time()
        if (now - self.last_connect_attempt) < 3.0:
            return False
        self.last_connect_attempt = now

        if not os.path.exists(self.port):
            logger.debug(f"GPS serial port {self.port} does not exist.")
            self.is_connected = False
            return False

        try:
            logger.info(f"Opening GPS serial port {self.port} at {self.baudrate} baud...")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            self.is_connected = True
            logger.info(f"GPS serial port {self.port} connected successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to open GPS serial port {self.port}: {e}")
            self.is_connected = False
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
            return False

    def start(self):
        """Starts background thread polling NMEA serial lines continuously."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops background GPS thread and closes serial port."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self.close()

    def close(self):
        """Closes serial connection."""
        self.is_connected = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def _worker_loop(self):
        """Background thread reading NMEA lines continuously."""
        while not self._stop_event.is_set():
            if self.mock_mode:
                time.sleep(0.2)
                continue

            if not self.is_connected or not self.ser or not getattr(self.ser, 'is_open', False):
                self.connect()
                time.sleep(1.0)
                continue

            try:
                line_bytes = self.ser.readline()
                if not line_bytes:
                    time.sleep(0.05)
                    continue

                line = line_bytes.decode('ascii', errors='ignore').strip()
                idx = line.find('$')
                if idx >= 0:
                    self.parse_nmea_sentence(line[idx:])

            except Exception as e:
                logger.debug(f"Error reading GPS NMEA line: {e}")
                self.is_connected = False
                self.close()
                time.sleep(1.0)

    def parse_nmea_sentence(self, sentence: str):
        """Parses standard NMEA 0183 sentences ($GPRMC, $GNRMC, $GPGGA, $GPVTG)."""
        idx_dollar = sentence.find('$')
        if idx_dollar >= 0:
            sentence = sentence[idx_dollar:]

        # Extract sentence data before checksum asterisk
        if '*' in sentence:
            parts = sentence.split('*')
            sentence_data = parts[0]
        else:
            sentence_data = sentence

        tokens = sentence_data.split(',')
        if len(tokens) < 2:
            return

        cmd = tokens[0].upper()

        # 1. RMC Sentence: Recommended Minimum Specific GPS/TRANSIT Data
        # $GPRMC,hhmmss.ss,A,llll.ll,a,yyyyy.yy,a,x.x,x.x,ddmmyy,x.x,a*hh
        if cmd.endswith("RMC") and len(tokens) >= 9:
            status = tokens[2]
            if status == 'A':
                self.has_fix = True
                self.last_fix_time = time.time()

                # Parse GPS UTC Timestamp & Date, Sync System Clock if off > 5.0 seconds
                if len(tokens) >= 10 and tokens[1] and tokens[9]:
                    time_str = tokens[1]
                    date_str = tokens[9]
                    if len(time_str) >= 6 and len(date_str) == 6:
                        try:
                            hh = int(time_str[0:2])
                            mm = int(time_str[2:4])
                            ss = int(time_str[4:6])
                            day = int(date_str[0:2])
                            month = int(date_str[2:4])
                            year = 2000 + int(date_str[4:6])
                            dt_gps = datetime.datetime(year, month, day, hh, mm, ss, tzinfo=datetime.timezone.utc)
                            gps_ts = dt_gps.timestamp()
                            self.last_gps_utc_timestamp = gps_ts
                            self.sync_system_clock_if_needed(gps_ts, dt_gps)
                        except Exception as e:
                            logger.debug(f"Error parsing GPS timestamp from RMC ({date_str} {time_str}): {e}")

                # Speed in Knots
                if tokens[7]:
                    try:
                        self.speed_knots = round(float(tokens[7]), 1)
                        self.speed_kmh = round(self.speed_knots * 1.852, 1)
                        self.speed_mph = round(self.speed_knots * 1.15078, 1)
                    except ValueError:
                        pass

                # Track Made Good (Heading in degrees)
                if tokens[8]:
                    try:
                        self.track_deg = round(float(tokens[8]), 1)
                        self.cardinal_heading = self.deg_to_cardinal(self.track_deg)
                    except ValueError:
                        pass

                # Parse Latitude & Longitude
                if len(tokens) >= 6 and tokens[3] and tokens[5]:
                    self.latitude = self._parse_nmea_coord(tokens[3], tokens[4])
                    self.longitude = self._parse_nmea_coord(tokens[5], tokens[6])
            else:
                self.has_fix = False

        # 2. GGA Sentence: Global Positioning System Fix Data
        # $GPGGA,hhmmss.ss,llll.ll,a,yyyyy.yy,a,x,xx,x.x,x.x,M,x.x,M,x.x,xxxx*hh
        elif cmd.endswith("GGA") and len(tokens) >= 8:
            try:
                self.fix_quality = int(tokens[6]) if tokens[6] else 0
                self.satellites = int(tokens[7]) if tokens[7] else 0
                if self.fix_quality > 0:
                    self.has_fix = True
                    self.last_fix_time = time.time()
                else:
                    self.has_fix = False
            except ValueError:
                pass

        # 3. GSV Sentence: Satellites in View
        # $GPGSV,2,1,08,01,40,083,46,02,17,308,38,...*hh
        elif cmd.endswith("GSV") and len(tokens) >= 4:
            try:
                if tokens[3]:
                    sats_in_view = int(tokens[3])
                    if sats_in_view > self.satellites or self.fix_quality == 0:
                        self.satellites = sats_in_view
            except ValueError:
                pass

        # 4. VTG Sentence: Track Made Good and Ground Speed
        # $GPVTG,x.x,T,x.x,M,x.x,N,x.x,K*hh
        elif cmd.endswith("VTG") and len(tokens) >= 8:
            if tokens[5] and tokens[6] == 'N':
                try:
                    self.speed_knots = round(float(tokens[5]), 1)
                    self.speed_kmh = round(self.speed_knots * 1.852, 1)
                    self.speed_mph = round(self.speed_knots * 1.15078, 1)
                except ValueError:
                    pass
            if tokens[1] and tokens[2] == 'T':
                try:
                    self.track_deg = round(float(tokens[1]), 1)
                    self.cardinal_heading = self.deg_to_cardinal(self.track_deg)
                except ValueError:
                    pass

    def _parse_nmea_coord(self, coord_str: str, hemisphere: str) -> float:
        """Converts NMEA latitude/longitude string (ddmm.mmmm) to decimal degrees."""
        try:
            val = float(coord_str)
            deg = int(val / 100)
            minutes = val - (deg * 100)
            decimal = deg + (minutes / 60.0)
            if hemisphere.upper() in ('S', 'W'):
                decimal = -decimal
            return round(decimal, 5)
        except Exception:
            return 0.0

    def sync_system_clock_if_needed(self, gps_timestamp: float, gps_dt: datetime.datetime):
        """
        Compares host system time against GPS UTC time.
        If system time drift exceeds 5.0 seconds, synchronizes the system clock.
        Rate-limited to once every 10 seconds to prevent excessive calls.
        """
        now = time.time()
        if (now - self.last_clock_sync_check) < 10.0:
            return

        self.last_clock_sync_check = now
        drift = abs(gps_timestamp - now)
        self.clock_drift_seconds = round(drift, 1)

        if drift > 5.0:
            sys_utc = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            gps_utc = gps_dt.strftime("%Y-%m-%d %H:%M:%S")
            logger.warning(
                f"⏰ System clock drift detected! System time ({sys_utc} UTC) "
                f"differs by {drift:.1f}s from GPS UTC ({gps_utc}). Synchronizing system clock..."
            )
            success = self._set_system_clock(gps_timestamp, gps_dt)
            if success:
                self.last_clock_sync_time = time.time()
                self.clock_drift_seconds = 0.0

    def _set_system_clock(self, gps_timestamp: float, gps_dt: datetime.datetime) -> bool:
        """Sets host Linux system clock to GPS UTC time."""
        utc_str = gps_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Method 1: standard Linux 'date -u -s "YYYY-MM-DD HH:MM:SS"'
        try:
            subprocess.run(["date", "-u", "-s", utc_str], capture_output=True, text=True, check=True)
            logger.info(f"✅ System clock successfully set via date command: {utc_str} UTC")
            return True
        except (subprocess.CalledProcessError, PermissionError, OSError):
            pass

        # Method 2: 'sudo -n date -u -s "YYYY-MM-DD HH:MM:SS"' (passwordless sudo if available)
        try:
            subprocess.run(["sudo", "-n", "date", "-u", "-s", utc_str], capture_output=True, text=True, check=True)
            logger.info(f"✅ System clock successfully set via sudo date: {utc_str} UTC")
            return True
        except (subprocess.CalledProcessError, PermissionError, OSError):
            pass

        # Method 3: 'date -s "@<timestamp>"'
        try:
            subprocess.run(["date", "-s", f"@{int(gps_timestamp)}"], capture_output=True, text=True, check=True)
            logger.info(f"✅ System clock successfully set via timestamp: {gps_timestamp}")
            return True
        except (subprocess.CalledProcessError, PermissionError, OSError) as e:
            logger.error(f"❌ Failed to set system clock from GPS time ({utc_str}): Permission denied or missing date utility.")
            return False

    @staticmethod
    def deg_to_cardinal(deg: float) -> str:
        """Converts compass heading degrees (0 - 360) to cardinal direction (N, NE, E, SE, S, SW, W, NW)."""
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx]

    def read_gps(self, engine_rpm: float = 0.0) -> Dict[str, Any]:
        """Returns current GPS telemetry snapshot."""
        if self.mock_mode:
            # Generate realistic mock GPS speed based on engine RPM
            if engine_rpm > 500:
                mock_speed = max(0.0, round(((engine_rpm - 700.0) / 3800.0) * 32.0 + (random.random() * 0.8), 1))
            else:
                mock_speed = 0.0

            return {
                "status": "ok",
                "connected": True,
                "has_fix": True,
                "speed_knots": mock_speed,
                "speed_kmh": round(mock_speed * 1.852, 1),
                "speed_mph": round(mock_speed * 1.15078, 1),
                "track_deg": 245.0,
                "cardinal_heading": "WSW",
                "satellites": 9,
                "fix_quality": 1,
                "latitude": 57.70887,
                "longitude": 11.97456,
                "gps_utc_timestamp": time.time(),
                "clock_drift_seconds": 0.0,
                "is_mock": True
            }

        # Check if GPS fix expired (> 5s without fix update)
        if time.time() - self.last_fix_time > 5.0:
            self.has_fix = False

        if not self.is_connected or not self.has_fix:
            return {
                "status": "no_fix" if self.is_connected else "offline",
                "connected": self.is_connected,
                "has_fix": False,
                "speed_knots": 0.0,
                "speed_kmh": 0.0,
                "speed_mph": 0.0,
                "track_deg": 0.0,
                "cardinal_heading": "N",
                "satellites": self.satellites,
                "fix_quality": self.fix_quality,
                "latitude": 0.0,
                "longitude": 0.0,
                "gps_utc_timestamp": self.last_gps_utc_timestamp,
                "clock_drift_seconds": self.clock_drift_seconds,
                "is_mock": False
            }

        return {
            "status": "ok",
            "connected": True,
            "has_fix": self.has_fix,
            "speed_knots": self.speed_knots,
            "speed_kmh": self.speed_kmh,
            "speed_mph": self.speed_mph,
            "track_deg": self.track_deg,
            "cardinal_heading": self.cardinal_heading,
            "satellites": self.satellites,
            "fix_quality": self.fix_quality,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "gps_utc_timestamp": self.last_gps_utc_timestamp,
            "clock_drift_seconds": self.clock_drift_seconds,
            "is_mock": False
        }


if __name__ == "__main__":
    import sys
    print("Testing GPSReader on /dev/ttyACM0...")
    gps = GPSReader(port="/dev/ttyACM0")
    if gps.connect():
        gps.start()
        try:
            for _ in range(10):
                time.sleep(1.0)
                data = gps.read_gps(engine_rpm=2500)
                print(f"GPS Data: {data}")
        finally:
            gps.stop()
    else:
        print("Could not connect to /dev/ttyACM0. Testing mock mode:")
        gps = GPSReader(mock_mode=True)
        print(gps.read_gps(engine_rpm=3200))
