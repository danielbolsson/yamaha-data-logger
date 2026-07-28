# Yamaha YDS Telemetry System & Data Logger

A real-time telemetry decoding engine and marine helm web dashboard for **Yamaha Outboard Engines** (calibrated for Yamaha F150 ECU `63P-8591A-01` / `63P-01`) connected via a 12V ISO 9141 K-Line USB diagnostic adapter to a Raspberry Pi or PC.

---

## 1. Wiring & Hardware Requirements

### Connector Pinout: USB OBD2 Adapter to Yamaha 3-Pin YDS Port

| OBD2 Cable Pin | YDS 3-Pin Connector Wire | Description | Notes |
| :--- | :--- | :--- | :--- |
| **Pin 16** | **Red Wire** | +12V Power | Switched +12V DC from Engine Harness |
| **Pin 4 / Pin 5** | **Black Wire** | Engine / Battery Ground | Chassis / Battery Negative Ground |
| **Pin 7 (K-Line)** | **Data Wire** (Yellow/White) | ISO 9141 K-Line Data Signal | ~4V–12V TTL Data Line (Do NOT use Pin 15 L-Line) |

> [!IMPORTANT]
> **Ignition Key Requirement:** The boat ignition key switch **MUST BE ON** for the ECU to power up and respond to K-Line requests.

---

## 2. Installation & Environment Setup

### A. System Dependencies

Update packages and install Python 3, virtual environment tools, and `udev`:

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git udev
```

### B. Python Virtual Environment

Clone or navigate to the project directory, create a virtual environment, and install required modules:

```bash
cd /home/pi/yamaha-data-logger
python3 -m venv venv
source venv/bin/activate

pip install pyserial fastapi uvicorn websockets
```

---

## 3. Serial Port & USB Permissions (`udev` Setup)

### A. Grant User Permissions
Allow the non-root user to access serial devices:

```bash
sudo usermod -a -G dialout $USER
```
*(Log out and log back in or reboot for group changes to take effect).*

### B. Create Persistent `udev` Rule (Recommended)
To assign a fixed device symlink (e.g. `/dev/ttyUSB-yds`) regardless of USB port plugging order:

1. Identify USB serial chipset vendor & product ID:
   ```bash
   lsusb
   ```
   *(Common chipsets: FTDI `0403:6001` or CH340 `1a86:7523`)*

2. Create a `udev` rule file:
   ```bash
   sudo nano /etc/udev/rules.d/99-yamaha-yds.rules
   ```

3. Add the rule line (adjust `idVendor`/`idProduct` if necessary):
   ```udev
   SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="ttyUSB-yds", GROUP="dialout", MODE="0666"
   ```

4. Reload `udev` rules:
   ```bash
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```

---

## 4. Testing & Verification Workflow (Step-by-Step)

Follow these steps to verify hardware connection, K-Line communication, serial handshakes, and telemetry parsing.

### Step 1: Cable Offline Self-Test (Disconnected from Engine)
Verify local cable loopback behavior before plugging into the engine:

```bash
python3 tests/test_yds_hardware.py --port /dev/ttyUSB0
```
- **Expected Outcome:** Determines whether the adapter echoes bytes locally (cable internal loopback) or only when connected to an active K-Line bus.

### Step 2: Bus Scanner & Opcode Discovery (Optional)
Run an exhaustive bus scan to probe wakeup handshakes and custom query opcodes:

```bash
python3 tests/scan_yamaha_yds.py --port /dev/ttyUSB0
```

### Step 3: YDS Reader CLI Direct Polling Test
Test the calibrated telemetry decoder directly in the terminal to verify live parameter reading:

```bash
python3 yds_reader.py --port /dev/ttyUSB0 --baud 9600
```
- **Expected Outcome:** Displays real-time RPM, Engine Operating Hours, TPS %, MAP Pressure, Oil Pressure, and Temperatures directly in the console output.

### Step 4: Web Server & Live Telemetry Dashboard
Launch the FastAPI WebSocket server and dashboard interface:

```bash
python3 server.py --serial-port /dev/ttyUSB0 --baud 9600 --web-port 8000
```
- Open a web browser to **`http://localhost:8000`** or **`http://<RPI-IP>:8000`**.
- Verify REST status API: `http://localhost:8000/api/status`

---

## 5. Simulation / Mock Mode (Testing Without Hardware)

You can run both the reader CLI and the web server in mock mode to test the UI or develop software without connecting to the engine:

- **CLI Reader Mock:**
  ```bash
  python3 yds_reader.py --mock
  ```
- **Web Server Mock:**
  ```bash
  python3 server.py --mock --web-port 8000
  ```

---

## 6. Systemd Auto-Start Service (Run on Boot)

To run the telemetry server automatically when the system boots:

1. Create service file:
   ```bash
   sudo nano /etc/systemd/system/yamaha-telemetry.service
   ```

2. Add configuration:
   ```ini
   [Unit]
   Description=Yamaha YDS Real-Time Telemetry Web Server
   After=network.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/yamaha-data-logger
   ExecStart=/home/pi/yamaha-data-logger/venv/bin/python3 /home/pi/yamaha-data-logger/server.py --serial-port /dev/ttyUSB0 --web-port 8000
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable yamaha-telemetry.service
   sudo systemctl start yamaha-telemetry.service
   ```

4. Monitor status & logs:
   ```bash
   sudo systemctl status yamaha-telemetry.service
   journalctl -u yamaha-telemetry.service -f
   ```

---

## 7. Multi-Device & Kiosk Display Setup

### A. Secondary Displays (Tablets & Mobile Phones)
Connect phones or tablets to the boat Wi-Fi or Raspberry Pi hotspot and navigate to:
```
http://<RASPBERRY-PI-IP>:8000
```
The server broadcasts WebSocket telemetry to multiple concurrent client devices with ultra-low latency.

### B. Raspberry Pi Touchscreen Kiosk Mode
To launch Chromium automatically in full-screen kiosk mode on boot:

1. Install dependencies:
   ```bash
   sudo apt install -y chromium-browser unclutter
   ```

2. Add autostart entries in `~/.config/lxsession/LXDE-pi/autostart` (or equivalent compositor config):
   ```bash
   @xset s off
   @xset -dpms
   @xset s noblank
   @unclutter -idle 0.5 -root
   @chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:8000
   ```

---

## 8. Debugging & Hardware Troubleshooting

### Symptom: TX Echo Received, but 0 ECU Response Bytes Returned

If diagnostic scripts show transmitted bytes echoed back but no response payload from the ECU:

1. **Ignition Key Switch:**
   - Confirm key switch is turned **ON**. The ECM requires +12V power to transmit telemetry.
2. **Voltage Levels (4V/5V TTL vs 12V OBD2 Transceivers):**
   - Disconnected Yamaha YDS K-Line floats around ~4V DC (5V TTL logic level).
   - Standard 12V OBD2 transceivers (e.g. L9637D, MC33660) powered by 13.8V have a ~7.0V–9.6V receiver threshold and will ignore 4V pulses!
   - **Fix:** Supply +5V (instead of 12V) to OBD2 Pin 16, or use a 5V USB-to-TTL serial adapter.
3. **Multimeter Engine Connector Checklist:**
   - **Ground (Black Wire):** 0 Ω resistance to battery negative.
   - **Power (Red Wire):** +12.5V to +14.4V DC to Ground.
   - **Data Wire (Yellow/White):** +10V to +12V DC to Ground (disconnected ECU side). If Data wire reads 0V DC when disconnected, check harness wiring or ECU main relay.

---

## 9. Packet Sniffing & Capturing (Linux Host + Windows VM)

To capture raw packets when running official Windows YDS software in a VirtualBox VM:

### Method A: Virtual Serial Port PTY Proxy (`sniff_yds.py`)
*Best for VirtualBox Serial Port Passthrough (`COM1`)*

1. Start the proxy script on Linux:
   ```bash
   python3 sniff_yds.py
   ```
   This creates a virtual serial port symlink `/tmp/ttyYDS`.

2. In VirtualBox VM Settings $\rightarrow$ **Serial Ports**:
   - Enable Serial Port 1
   - Port Mode: **Host Device** / **Host Pipe**
   - Path/Address: `/tmp/ttyYDS`

3. Launch Windows YDS inside the VM. All `[VM -> ECU]` requests and `[ECU -> VM]` responses are logged in real-time to stdout and `yds_sniff_log.txt`.

### Method B: Linux Kernel `usbmon` Raw USB Sniffer (`tools/sniff_usbmon_raw.py`)
*Best for VirtualBox USB Device Passthrough*

1. Enable the Linux kernel `usbmon` module:
   ```bash
   sudo modprobe usbmon
   sudo chmod 666 /dev/usbmon*
   ```

2. Run the raw USB packet capture script:
   ```bash
   python3 tools/sniff_usbmon_raw.py --bus 1
   ```
   All low-level USB URB transfer packets will be logged to stdout and `logs/yds_usb_raw_sniff.log`.

---

## 10. Reverse-Engineered Yamaha ECU Protocol & Standalone Unlock Specification

Through low-level USB URB packet capture ([logs/yds_usb_raw_sniff.log](file:///home/daniel/src/yamaha-data-logger/logs/yds_usb_raw_sniff.log)) and empirical hardware testing, the exact protocol required to unlock and read Yamaha YDS ECUs (e.g. F150 / `63P-8591A-01`) **100% standalone on Raspberry Pi / Linux** without Windows or VirtualBox has been decoded:

### A. Standalone Hardware Baud-Rate Switch Unlock
When starting from a cold ignition power-on, standard 9600-baud queries receive only 1-byte TX echoes because the ECU's diagnostic UART comparator is in sleep mode. To wake up and unlock the ECU:

1. **Open FTDI Serial Port** (`/dev/ttyUSB0` / `/dev/ttyUSB-yds`).
2. **Switch to 2400 Baud** (`ser.baudrate = 2400`).
3. **Switch to 300 Baud** (`ser.baudrate = 300`) and transmit 1-byte sync opcode `0x1C`.
4. **Switch to 9600 Baud** (`ser.baudrate = 9600`).
5. **Assert DTR & RTS Lines HIGH** (`ser.dtr = True`, `ser.rts = True`).

This hardware baud-rate transition triggers the K-Line level shifter and wakes up the ECU's diagnostic UART interrupt.

### B. Sequential YDS Telemetry Frame Protocol
Once unlocked, the ECU requires every polling cycle to execute a structured frame sequence:

$$\text{Frame Sequence: } \mathtt{0x1C} \rightarrow \mathtt{0xFD} \rightarrow \mathtt{0xE5} \rightarrow \mathtt{0xFE} \rightarrow \mathtt{0xFF} \rightarrow \mathtt{0xDE} \rightarrow \mathtt{0xD0} \rightarrow \mathtt{0xF0} \rightarrow \mathtt{0xEF} \rightarrow \mathtt{0x00} \rightarrow \mathtt{0x01} \rightarrow \mathtt{0x08} \rightarrow \mathtt{0x09} \rightarrow \mathtt{0x0A} \rightarrow \mathtt{0x0B} \rightarrow \mathtt{0x0E} \rightarrow \mathtt{0x0F} \rightarrow \mathtt{0x02} \rightarrow \mathtt{0x03} \rightarrow \mathtt{0xF1}$$

### C. Opcode Mapping & Data Conversion Table

| Opcode | Parameter | Type | Conversion / Formula | Example Raw $\rightarrow$ Decoded Value |
| :---: | :--- | :---: | :--- | :--- |
| `0x1C` | Diagnostic Sync / Heartbeat | 8-bit | Handshake & Watchdog Reset | Payload `0x03` |
| `0xFD` | Diagnostic Session Unlock | 8-bit | Diagnostic Mode Unlock | Payload `0x00` |
| `0xE5` | Engine Operating Hours | 8-bit | $\text{Hours} = \text{Raw} \times 2.071$ | `0xEF` (239) $\rightarrow$ **495.0 Hours** |
| `0xFE` | ECU Status | 8-bit | Status Flags | Payload `0x00` |
| `0xFF` | ECU Model Sub-ID | 8-bit | Hardware Identification | `0x06` $\rightarrow$ **Yamaha 63P-01** |
| `0xDE` | Subsystem Unlock | 8-bit | Mode Flag | Payload `0x00` |
| `0xD0` | Subsystem Unlock | 8-bit | Mode Flag | Payload `0x00` |
| `0x91` | Engine Coolant Temp | 8-bit | $\text{°C} = \text{Raw} + 4.5$ ($\text{°F} = \text{°C} \times 1.8 + 32$) | `0x1D` (29) $\rightarrow$ **33.5 °C / 92.0 °F** |
| `0x1B` | Intake Air Temp | 8-bit | $\text{°C} = \text{Raw} - 101.4$ | `0x80` (128) $\rightarrow$ **26.6 °C / 79.7 °F** |
| `0x00` / `0x01` | Engine Speed RPM | 16-bit | $\text{RPM} = (\text{High} \ll 8) \mid \text{Low}$ | `0x0315` (789) $\rightarrow$ **787.0 r/min** |
| `0x08` / `0x09` | Throttle Position (TPS) | 16-bit | $\text{V} = \text{Raw} \times 0.0009784$, $\text{deg} = (\text{Raw} - 700) \times 0.0833$ | `0x02B6` (694) $\rightarrow$ **0.679 V / -0.5 deg (0.0%)** |
| `0x05` / `0x0B` | Manifold Absolute Pressure (MAP) | 8-bit | Stopped: $\text{Raw}_{05} \times 0.4253$, Running: $\text{Raw}_{0B} \times 0.3311$ | `0xE9` (233) $\rightarrow$ **99.09 kPa**, `0x8B` (139) $\rightarrow$ **46.02 kPa** |
| `0x41` | ISC Valve Opening | 8-bit | $\text{\%} = \text{Raw} / 1.7164$ | `0x73` (115) $\rightarrow$ **67 %** |
| `0x0E` / `0x0F` | Oil Pressure | 16-bit | $\text{kPa} = \text{Raw} / 7.16$ | `0x0A19` (2585) $\rightarrow$ **361.0 kPa / 52.3 PSI** |
| `0x1D` | Battery Voltage | 8-bit | $\text{Volts} = \text{Raw} / 17.222$ | `0xDE` (222) $\rightarrow$ **12.89 V**, `0xED` (237) $\rightarrow$ **13.79 V** |
| `0xF1` | Streaming Enable | 8-bit | Streaming Session Keep-Alive | Refresh every $\le 8$ seconds |

### D. Session Watchdog & Auto-Recovery
* The Yamaha ECU maintains an internal **45-second diagnostic session watchdog timer**. If no keep-alive command (`0xF1`) is received for 45 seconds, the ECU drops back to non-diagnostic mode.
* [yds_reader.py](file:///home/daniel/src/yamaha-data-logger/yds_reader.py) automatically handles periodic 8-second keep-alive heartbeats and includes automatic re-activation recovery if the connection is ever interrupted.

