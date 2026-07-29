#!/usr/bin/env python3
"""
FastAPI & WebSocket Telemetry Server for Yamaha YDS Diagnostic Dashboard.
Manages serial polling loop, broadcasts real-time telemetry to web browsers over WebSockets,
and serves high-contrast marine helm dashboard.
"""

import os
import sys
import time
import json
import asyncio
import logging
import argparse
import subprocess
from typing import Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from yds_reader import YDSReader
from gps_reader import GPSReader
import database

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("yds_server")

# Global State
active_websockets: Set[WebSocket] = set()
latest_telemetry: dict = {}
yds_reader_instance: YDSReader = None
gps_reader_instance: GPSReader = None
polling_task: asyncio.Task = None

# Fuel Tracking State
current_fuel_state: dict = {}
last_polling_time: float = 0.0
last_db_log_time: float = 0.0

# System Configuration
DEFAULT_SERIAL_PORT = os.getenv("YDS_PORT", "/dev/ttyUSB0")
DEFAULT_GPS_PORT = os.getenv("GPS_PORT", "/dev/ttyACM0")
DEFAULT_BAUD_RATE = int(os.getenv("YDS_BAUD", "9600"))
DEFAULT_WEB_PORT = int(os.getenv("WEB_PORT", "8000"))
DEFAULT_MOCK_MODE = os.getenv("YDS_MOCK", "false").lower() in ("true", "1", "yes")

# Command-line Argument Parsing
parser = argparse.ArgumentParser(description="Yamaha YDS Telemetry Web Server")
parser.add_argument("--serial-port", default=DEFAULT_SERIAL_PORT, help="YDS Serial device path (default /dev/ttyUSB0)")
parser.add_argument("--gps-port", default=DEFAULT_GPS_PORT, help="GPS Receiver device path (default /dev/ttyACM0)")
parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE, help="Serial baud rate (default 9600)")
parser.add_argument("--host", default="0.0.0.0", help="Web server host IP (default 0.0.0.0)")
parser.add_argument("--web-port", type=int, default=DEFAULT_WEB_PORT, help="Web server port (default 8000)")
parser.add_argument("--mock", action="store_true", default=DEFAULT_MOCK_MODE, help="Force mock simulation mode")
parser.add_argument("--replay-file", default=None, help="Path to raw telemetry JSONL log file to replay")

# Parse known args so uvicorn / command execution runs cleanly
cli_args, _ = parser.parse_known_args()


async def telemetry_background_loop():
    """
    Asynchronous background loop polling ECU telemetry at 5 Hz (every 200ms),
    calculating fuel consumption, logging frames to SQLite, and broadcasting updates.
    """
    global latest_telemetry, active_websockets, yds_reader_instance, current_fuel_state, last_polling_time, last_db_log_time
    logger.info("Starting background YDS polling loop (5 Hz)...")

    # Connect to serial port / init reader
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, yds_reader_instance.connect)

    last_polling_time = time.time()
    last_db_log_time = time.time()

    while True:
        try:
            now = time.time()
            dt = max(0.05, min(1.0, now - last_polling_time))
            last_polling_time = now

            # Execute serial read in thread pool to prevent blocking asyncio loop
            data = await loop.run_in_executor(None, yds_reader_instance.read_telemetry)

            is_mock = cli_args.mock or (yds_reader_instance and yds_reader_instance.mock_mode)

            # Read GPS snapshot
            gps_data = gps_reader_instance.read_gps(engine_rpm=data.get("rpm", 0.0)) if gps_reader_instance else {}
            speed_kts = gps_data.get("speed_knots", 0.0)
            fuel_lh = data.get("fuel_rate_lh", 0.0)

            # Calculate Fuel Economy in Liters per Nautical Mile (L/NM)
            fuel_economy_l_nm = round(fuel_lh / speed_kts, 2) if speed_kts > 0.5 and fuel_lh > 0 else 0.0

            # Calculate real-time fuel consumption if running (live hardware mode only)
            if data and data.get("status") == "ok" and not is_mock:
                if fuel_lh > 0.0:
                    consumed_delta = (fuel_lh * dt) / 3600.0
                    new_rem = max(0.0, current_fuel_state["current_fuel_liters"] - consumed_delta)
                    new_trip = current_fuel_state["trip_consumed_liters"] + consumed_delta
                    current_fuel_state = database.update_fuel_state(new_rem, trip_consumed=new_trip)

            # Attach fuel state and GPS telemetry to payload
            data.update({
                "current_fuel_liters": current_fuel_state["current_fuel_liters"],
                "tank_capacity_liters": current_fuel_state["tank_capacity_liters"],
                "trip_consumed_liters": current_fuel_state["trip_consumed_liters"],
                "fuel_percent": current_fuel_state["fuel_percent"],
                "gps": gps_data,
                "gps_speed_kts": speed_kts,
                "gps_speed_kmh": gps_data.get("speed_kmh", 0.0),
                "gps_heading_deg": gps_data.get("track_deg", 0.0),
                "gps_cardinal": gps_data.get("cardinal_heading", "N"),
                "gps_satellites": gps_data.get("satellites", 0),
                "gps_has_fix": gps_data.get("has_fix", False),
                "fuel_economy_l_nm": fuel_economy_l_nm
            })

            latest_telemetry = data

            # Log to SQLite database history every 1.0 second (live hardware mode only)
            if not is_mock and (now - last_db_log_time) >= 1.0:
                last_db_log_time = now
                await loop.run_in_executor(None, database.log_telemetry_frame, data)

            # Broadcast to active WebSocket connections
            if active_websockets:
                payload = json.dumps(data)
                disconnected_clients = set()

                for ws in list(active_websockets):
                    try:
                        await ws.send_text(payload)
                    except Exception as ws_err:
                        logger.debug(f"Client disconnected or send failed: {ws_err}")
                        disconnected_clients.add(ws)

                # Clean up dropped connections
                for dead_ws in disconnected_clients:
                    active_websockets.discard(dead_ws)

            await asyncio.sleep(0.2)  # 5 Hz polling interval

        except asyncio.CancelledError:
            logger.info("Telemetry polling task cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in background loop: {e}")
            await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for starting SQLite DB, YDS Reader, and GPS Reader."""
    global yds_reader_instance, gps_reader_instance, polling_task, current_fuel_state
    logger.info("Initializing YDS Telemetry Backend, GPS Receiver & SQLite Database...")

    # Initialize SQLite Database
    database.init_db()
    current_fuel_state = database.get_fuel_state()

    # Instantiate YDS ECU Reader
    yds_reader_instance = YDSReader(
        port=cli_args.serial_port,
        baudrate=cli_args.baud,
        mock_mode=cli_args.mock,
        replay_file=cli_args.replay_file
    )

    # Instantiate GPS Receiver Reader
    gps_reader_instance = GPSReader(
        port=cli_args.gps_port,
        mock_mode=cli_args.mock
    )
    gps_reader_instance.connect()
    gps_reader_instance.start()

    # Start background polling task
    polling_task = asyncio.create_task(telemetry_background_loop())
    yield

    # Shutdown / cleanup
    logger.info("Shutting down YDS Telemetry Backend...")
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    if yds_reader_instance:
        yds_reader_instance.close()

    if gps_reader_instance:
        gps_reader_instance.stop()


# Initialize FastAPI Application
app = FastAPI(
    title="Yamaha YDS Telemetry Engine",
    description="Real-time telemetry WebSocket server with SQLite fuel logging for Yamaha F150",
    version="1.0.0",
    lifespan=lifespan
)

# REST API Diagnostics Endpoint
@app.get("/api/status")
async def get_system_status():
    """Returns current system health, serial status, and last telemetry frame."""
    return JSONResponse({
        "status": "online",
        "mock_mode": cli_args.mock or (yds_reader_instance.mock_mode if yds_reader_instance else False),
        "serial_port": cli_args.serial_port,
        "baud_rate": cli_args.baud,
        "active_clients": len(active_websockets),
        "fuel_state": current_fuel_state,
        "latest_telemetry": latest_telemetry
    })


# Fuel REST API Endpoints
@app.get("/api/fuel")
async def get_fuel_endpoint():
    """Returns current fuel tank level and trip consumption from SQLite."""
    global current_fuel_state
    current_fuel_state = database.get_fuel_state()
    return JSONResponse(current_fuel_state)


@app.post("/api/fuel/adjust")
async def adjust_fuel_endpoint(payload: dict):
    """Adjusts current fuel level by delta liters (+1, -1, +20, -20) in SQLite."""
    global current_fuel_state
    delta = float(payload.get("delta", 0.0))
    current_fuel_state = database.adjust_fuel_level(delta)
    logger.info(f"Adjusted fuel level by {delta}L -> New Level: {current_fuel_state['current_fuel_liters']}L")
    return JSONResponse(current_fuel_state)


@app.post("/api/fuel/fill")
async def fill_fuel_endpoint():
    """Resets fuel tank level to 170.0L full capacity in SQLite."""
    global current_fuel_state
    current_fuel_state = database.fill_tank_full(170.0)
    logger.info(f"Filled fuel tank to FULL (170.0L)")
    return JSONResponse(current_fuel_state)


@app.post("/api/fuel/reset_trip")
async def reset_trip_endpoint():
    """Resets trip consumed fuel counter to 0.0 in SQLite."""
    global current_fuel_state
    current_fuel_state = database.reset_trip_consumed()
    logger.info("Reset trip fuel consumption counter")
    return JSONResponse(current_fuel_state)


@app.get("/api/history")
async def get_history_endpoint(limit: int = 100):
    """Retrieves recent telemetry history frames from SQLite."""
    history = database.get_history(limit=limit)
    return JSONResponse({"count": len(history), "history": history})


@app.post("/api/kiosk/exit")
async def exit_kiosk_endpoint():
    """Terminates Chromium kiosk browser process on Raspberry Pi to return to desktop."""
    logger.info("Exit kiosk command triggered via web UI. Terminating Chromium process...")
    try:
        # Kill chromium browser instances
        subprocess.Popen(["pkill", "-f", "chromium"])
        return JSONResponse({"status": "exiting", "message": "Closing Chromium Kiosk..."})
    except Exception as e:
        logger.error(f"Error terminating Chromium process: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# WebSocket Endpoint for Live Telemetry Stream
@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint broadcasting live telemetry JSON packets.
    Client can also send commands (e.g. toggle unit modes or request immediate snapshot).
    """
    await websocket.accept()
    active_websockets.add(websocket)
    logger.info(f"WebSocket client connected from {websocket.client.host}. Total clients: {len(active_websockets)}")

    # Send initial telemetry snapshot immediately
    if latest_telemetry:
        try:
            await websocket.send_text(json.dumps(latest_telemetry))
        except Exception:
            pass

    try:
        while True:
            # Keep connection open and receive optional messages from client
            message = await websocket.receive_text()
            logger.debug(f"Received message from WS client: {message}")
            
            # Handle client commands if any (e.g. {"cmd": "ping"})
            if message == "ping":
                await websocket.send_text(json.dumps({"pong": True}))

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {websocket.client.host} disconnected.")
    except Exception as e:
        logger.warning(f"WebSocket exception: {e}")
    finally:
        active_websockets.discard(websocket)


# Mount Static Files (Frontend UI)
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main dashboard user interface."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>YDS Dashboard static files not found. Please build static/index.html</h2>")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://{cli_args.host}:{cli_args.web_port}")
    uvicorn.run(
        "server:app",
        host=cli_args.host,
        port=cli_args.web_port,
        log_level="info",
        reload=False
    )
