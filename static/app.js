/**
 * Yamaha YDS Real-Time Telemetry Dashboard Frontend Engine.
 * Multi-Page Kiosk Architecture (800x480 resolution optimized for Raspberry Pi Touchscreen).
 * Includes SQLite Fuel Tank Management, Real-Time Consumption Tracking, and Dual-Axis Charting.
 */

let switchDashboardPage = function () { };
let adjustFuelLevel = function () { };
let fillTankFull = function () { };
let resetTripConsumed = function () { };
let confirmExitKiosk = function () { };
let cancelExitKiosk = function () { };
let executeExitKiosk = function () { };

document.addEventListener("DOMContentLoaded", () => {
    // --- State Variables ---
    let ws = null;
    let reconnectTimer = null;
    let pingStartTime = 0;
    let currentLatency = 0;
    let activePage = 1;
    let useFahrenheit = false;

    // Local Fuel State Fallback (Synced continuously with SQLite API)
    let fuelRemainingLiters = 170.0;
    let tankCapacityLiters = 170.0;
    let tripConsumedLiters = 0.0;

    // History data arrays (max 40 points ~8 seconds of continuous telemetry history)
    const MAX_HISTORY = 40;
    const timeLabels = [];
    const rpmHistory = [];
    const fuelHistory = [];
    const mapHistory = [];
    const tpsHistory = [];
    const engTempHistory = [];
    const intakeTempHistory = [];
    const battHistory = [];
    const oilHistory = [];

    // --- DOM Elements ---
    const pageSlider = document.getElementById("page-slider");
    const navBtn1 = document.getElementById("nav-btn-1");
    const navBtn2 = document.getElementById("nav-btn-2");
    const navBtn3 = document.getElementById("nav-btn-3");
    const navBtn4 = document.getElementById("nav-btn-4");

    const connBadge = document.getElementById("connection-badge");
    const connDot = document.getElementById("conn-dot");
    const connText = document.getElementById("conn-text");
    const pingText = document.getElementById("ping-text");
    const mockBadge = document.getElementById("mock-badge");
    const tempToggleBtn = document.getElementById("temp-toggle-btn");
    const headerHours = document.getElementById("header-hours");

    // GPS DOM Elements
    const gpsBadge = document.getElementById("gps-badge");
    const gpsDot = document.getElementById("gps-dot");
    const gpsText = document.getElementById("gps-text");
    const gpsSpeedVal = document.getElementById("gps-speed-val");
    const gpsHeadingVal = document.getElementById("gps-heading-val");
    const fuelEconomyVal = document.getElementById("fuel-economy-val");

    const alertBanner = document.getElementById("alert-banner");
    const alertTitle = document.getElementById("alert-title");
    const alertDetail = document.getElementById("alert-detail");

    const digitalRpm = document.getElementById("digital-rpm-val");
    const tpsVal = document.getElementById("tps-value");
    const tpsFill = document.getElementById("tps-fill");
    const tpsDegVal = document.getElementById("tps-deg-val");

    const fuelRateVal = document.getElementById("fuel-rate-val");
    const engineTempVal = document.getElementById("engine-temp-val");
    const engineTempUnit = document.getElementById("engine-temp-unit");
    const tempStatusText = document.getElementById("temp-status-text");

    const batteryVal = document.getElementById("battery-val");
    const battStatusText = document.getElementById("batt-status-text");
    const mapVal = document.getElementById("map-val");
    const baroVal = document.getElementById("baro-val");
    const injectorVal = document.getElementById("injector-val");

    const flagOil = document.getElementById("flag-oil");
    const flagTemp = document.getElementById("flag-temp");
    const flagCheck = document.getElementById("flag-check");
    const flagBatt = document.getElementById("flag-batt");
    const flagIsc = document.getElementById("flag-isc");

    // Page 1 Mini Tank Bar Elements
    const tankFillMini = document.getElementById("tank-fill-mini");
    const tankLitersMini = document.getElementById("tank-liters-mini");
    const tankPctMini = document.getElementById("tank-pct-mini");

    // Page 4 Fuel Config Elements
    const tankFillLarge = document.getElementById("tank-fill-large");
    const fuelRemainingLitersElem = document.getElementById("fuel-remaining-liters");
    const fuelRemainingPctElem = document.getElementById("fuel-remaining-pct");
    const fuelRangeHoursElem = document.getElementById("fuel-range-hours");
    const tripConsumedValElem = document.getElementById("trip-consumed-val");

    // --- Restore User Preferences ---
    const savedUnit = localStorage.getItem("yamaha_temp_unit");
    if (savedUnit === "F") {
        useFahrenheit = true;
        tempToggleBtn.innerText = "°F";
    }

    const savedPage = localStorage.getItem("yamaha_kiosk_page");
    if (savedPage) {
        activePage = parseInt(savedPage, 10) || 1;
    }

    // --- Page Switcher ---
    switchDashboardPage = function (pageNum) {
        if (pageNum < 1 || pageNum > 4) return;
        activePage = pageNum;
        localStorage.setItem("yamaha_kiosk_page", pageNum);

        pageSlider.className = `page-slider active-page-${pageNum}`;

        [navBtn1, navBtn2, navBtn3, navBtn4].forEach((btn, idx) => {
            if (btn) {
                if (idx + 1 === pageNum) {
                    btn.classList.add("active");
                } else {
                    btn.classList.remove("active");
                }
            }
        });
    };

    switchDashboardPage(activePage);

    // Touch Swipe Gesture Handler for Kiosk Screen
    let touchStartX = 0;
    let touchStartY = 0;
    document.addEventListener("touchstart", (e) => {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }, false);

    document.addEventListener("touchend", (e) => {
        const diffX = e.changedTouches[0].screenX - touchStartX;
        const diffY = e.changedTouches[0].screenY - touchStartY;
        if (Math.abs(diffX) > 60 && Math.abs(diffY) < 50) {
            if (diffX < 0 && activePage < 4) {
                switchDashboardPage(activePage + 1);
            } else if (diffX > 0 && activePage > 1) {
                switchDashboardPage(activePage - 1);
            }
        }
    }, false);

    // Keyboard Hotkey Navigation (F1/F2/F3/F4, 1/2/3/4, Left/Right Arrow)
    document.addEventListener("keydown", (e) => {
        if (e.key === "F1" || e.key === "1") {
            e.preventDefault();
            switchDashboardPage(1);
        } else if (e.key === "F2" || e.key === "2") {
            e.preventDefault();
            switchDashboardPage(2);
        } else if (e.key === "F3" || e.key === "3") {
            e.preventDefault();
            switchDashboardPage(3);
        } else if (e.key === "F4" || e.key === "4") {
            e.preventDefault();
            switchDashboardPage(4);
        } else if (e.key === "ArrowLeft") {
            e.preventDefault();
            if (activePage > 1) switchDashboardPage(activePage - 1);
        } else if (e.key === "ArrowRight") {
            e.preventDefault();
            if (activePage < 4) switchDashboardPage(activePage + 1);
        }
    });

    // --- Unit Toggle ---
    tempToggleBtn.addEventListener("click", () => {
        useFahrenheit = !useFahrenheit;
        tempToggleBtn.innerText = useFahrenheit ? "°F" : "°C";
        localStorage.setItem("yamaha_temp_unit", useFahrenheit ? "F" : "C");
        if (lastTelemetry) updateUI(lastTelemetry);
    });

    // --- Exit Kiosk Mode (Return to Pi Desktop) ---
    const exitModal = document.getElementById("exit-modal");

    confirmExitKiosk = function () {
        if (exitModal) exitModal.classList.remove("hidden");
    };

    cancelExitKiosk = function () {
        if (exitModal) exitModal.classList.add("hidden");
    };

    executeExitKiosk = async function () {
        try {
            if (exitModal) {
                const modalText = exitModal.querySelector(".modal-text");
                if (modalText) modalText.innerText = "Closing Chromium kiosk...";
            }
            await fetch("/api/kiosk/exit", { method: "POST" });
            window.close();
        } catch (e) {
            console.error("Error executing exit kiosk:", e);
        }
    };

    // --- Fuel API Controls (SQLite Persistence) ---
    adjustFuelLevel = async function (delta) {
        try {
            const res = await fetch("/api/fuel/adjust", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ delta: delta })
            });
            const data = await res.json();
            updateFuelDisplay(data);
        } catch (e) {
            console.error("Error adjusting fuel level:", e);
        }
    };

    fillTankFull = async function () {
        try {
            const res = await fetch("/api/fuel/fill", { method: "POST" });
            const data = await res.json();
            updateFuelDisplay(data);
        } catch (e) {
            console.error("Error filling fuel tank:", e);
        }
    };

    resetTripConsumed = async function () {
        try {
            const res = await fetch("/api/fuel/reset_trip", { method: "POST" });
            const data = await res.json();
            updateFuelDisplay(data);
        } catch (e) {
            console.error("Error resetting trip consumed:", e);
        }
    };

    function updateFuelDisplay(fuelState) {
        if (!fuelState) return;
        fuelRemainingLiters = fuelState.current_fuel_liters || 170.0;
        tankCapacityLiters = fuelState.tank_capacity_liters || 170.0;
        tripConsumedLiters = fuelState.trip_consumed_liters || 0.0;

        const pct = Math.max(0, Math.min(100, (fuelRemainingLiters / tankCapacityLiters) * 100));

        // Page 1 Mini Tank Bar
        if (tankFillMini) {
            tankFillMini.style.width = `${pct.toFixed(1)}%`;
            if (pct < 20) {
                tankFillMini.className = "tank-bar-fill warning-fill";
            } else {
                tankFillMini.className = "tank-bar-fill";
            }
        }
        if (tankLitersMini) tankLitersMini.innerText = `${fuelRemainingLiters.toFixed(0)} L`;
        if (tankPctMini) tankPctMini.innerText = `${pct.toFixed(0)}%`;

        // Page 4 Large Fuel Config Display
        if (tankFillLarge) {
            tankFillLarge.style.height = `${pct.toFixed(1)}%`;
            if (pct < 20) {
                tankFillLarge.className = "tank-gauge-fill-large warning-fill";
            } else {
                tankFillLarge.className = "tank-gauge-fill-large";
            }
        }
        if (fuelRemainingLitersElem) fuelRemainingLitersElem.innerText = fuelRemainingLiters.toFixed(1);
        if (fuelRemainingPctElem) fuelRemainingPctElem.innerText = pct.toFixed(0);
        if (tripConsumedValElem) tripConsumedValElem.innerText = tripConsumedLiters.toFixed(1);

        // Est. Range Hours
        if (fuelRangeHoursElem) {
            const flowRate = (lastTelemetry && lastTelemetry.fuel_rate_lh) ? lastTelemetry.fuel_rate_lh : 0;
            if (flowRate > 0.5) {
                const rangeHrs = fuelRemainingLiters / flowRate;
                fuelRangeHoursElem.innerText = rangeHrs.toFixed(1);
            } else {
                fuelRangeHoursElem.innerText = "--";
            }
        }
    }

    // Load initial fuel state from SQLite endpoint
    fetch("/api/fuel")
        .then(res => res.json())
        .then(data => updateFuelDisplay(data))
        .catch(err => console.debug("Initial fuel state fetch warning:", err));

    // --- Canvas Tachometer Setup ---
    const gaugeCanvas = document.getElementById("rpmGaugeCanvas");
    const ctx = gaugeCanvas.getContext("2d");

    function renderRpmGauge(rpmValue) {
        const width = gaugeCanvas.width;
        const height = gaugeCanvas.height;
        const centerX = width / 2;
        const centerY = height / 2;
        const radius = width * 0.42;

        ctx.clearRect(0, 0, width, height);

        const startAngle = 0.75 * Math.PI; // 135 deg
        const endAngle = 2.25 * Math.PI;   // 405 deg
        const totalAngle = endAngle - startAngle;

        const maxRpm = 6000;
        const clampedRpm = Math.max(0, Math.min(maxRpm, rpmValue));
        const fillPct = clampedRpm / maxRpm;
        const currentAngle = startAngle + (fillPct * totalAngle);

        // Track Arc
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, startAngle, endAngle, false);
        ctx.lineWidth = 14;
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.lineCap = "round";
        ctx.stroke();

        // Redline Zone Arc (5200 to 6000 RPM)
        const redlineStart = startAngle + ((5200 / maxRpm) * totalAngle);
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, redlineStart, endAngle, false);
        ctx.lineWidth = 14;
        ctx.strokeStyle = "rgba(255, 23, 68, 0.4)";
        ctx.lineCap = "round";
        ctx.stroke();

        // Active Arc
        if (clampedRpm > 10) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, startAngle, currentAngle, false);
            ctx.lineWidth = 14;
            ctx.lineCap = "round";

            if (clampedRpm > 5200) {
                ctx.strokeStyle = "#ff1744";
            } else {
                const grad = ctx.createLinearGradient(0, height, width, 0);
                grad.addColorStop(0, "#00e5ff");
                grad.addColorStop(1, "#0077ff");
                ctx.strokeStyle = grad;
            }
            ctx.stroke();
        }

        // Ticks
        for (let i = 0; i <= 6; i++) {
            const angle = startAngle + ((i / 6) * totalAngle);
            const innerR = radius - 16;
            const outerR = radius - 8;
            const x1 = centerX + Math.cos(angle) * innerR;
            const y1 = centerY + Math.sin(angle) * innerR;
            const x2 = centerX + Math.cos(angle) * outerR;
            const y2 = centerY + Math.sin(angle) * outerR;

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.lineWidth = i >= 5 ? 3 : 2;
            ctx.strokeStyle = i >= 5 ? "#ff1744" : "rgba(255, 255, 255, 0.4)";
            ctx.stroke();

            // Labels
            const labelR = radius - 26;
            const lx = centerX + Math.cos(angle) * labelR;
            const ly = centerY + Math.sin(angle) * labelR;
            ctx.font = "bold 9px 'Chakra Petch', sans-serif";
            ctx.fillStyle = i >= 5 ? "#ff1744" : "rgba(255, 255, 255, 0.6)";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(i.toString(), lx, ly);
        }
    }

    renderRpmGauge(0);

    // --- Chart.js Setup for Pages 2 & 3 ---
    const chartDefaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
            x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { display: false } },
            y: { grid: { color: "rgba(255,255,255,0.08)" }, ticks: { color: "#8a9bb0", font: { size: 9 } } }
        }
    };

    // Page 2 - RPM & Fuel Flow Dual-Axis Chart
    const rpmChartCtx = document.getElementById("rpmChartCanvas").getContext("2d");
    const rpmChart = new Chart(rpmChartCtx, {
        type: "line",
        data: {
            labels: timeLabels,
            datasets: [
                { label: "RPM", data: rpmHistory, borderColor: "#00e5ff", borderWidth: 2, pointRadius: 0, tension: 0.2, yAxisID: "y" },
                { label: "Fuel (L/h)", data: fuelHistory, borderColor: "#ffb700", borderWidth: 2, pointRadius: 0, tension: 0.2, yAxisID: "y1" }
            ]
        },
        options: {
            ...chartDefaultOptions,
            scales: {
                x: { ticks: { display: false } },
                y: { type: "linear", display: true, position: "left", min: 0, max: 6000, ticks: { color: "#00e5ff", font: { size: 8 } } },
                y1: { type: "linear", display: true, position: "right", min: 0, max: 60, grid: { drawOnChartArea: false }, ticks: { color: "#ffb700", font: { size: 8 } } }
            }
        }
    });

    // Page 2 - MAP & TPS Chart
    const mapTpsChartCtx = document.getElementById("mapTpsChartCanvas").getContext("2d");
    const mapTpsChart = new Chart(mapTpsChartCtx, {
        type: "line",
        data: {
            labels: timeLabels,
            datasets: [
                { label: "MAP", data: mapHistory, borderColor: "#00e5ff", borderWidth: 2, pointRadius: 0, yAxisID: "y" },
                { label: "TPS", data: tpsHistory, borderColor: "#ffb700", borderWidth: 2, pointRadius: 0, yAxisID: "y1" }
            ]
        },
        options: {
            ...chartDefaultOptions,
            scales: {
                x: { ticks: { display: false } },
                y: { type: "linear", display: true, position: "left", min: 0, max: 110, ticks: { color: "#00e5ff", font: { size: 8 } } },
                y1: { type: "linear", display: true, position: "right", min: 0, max: 100, grid: { drawOnChartArea: false }, ticks: { color: "#ffb700", font: { size: 8 } } }
            }
        }
    });

    // Page 3 - Temperature Chart
    const tempChartCtx = document.getElementById("tempChartCanvas").getContext("2d");
    const tempChart = new Chart(tempChartCtx, {
        type: "line",
        data: {
            labels: timeLabels,
            datasets: [
                { label: "Eng Temp", data: engTempHistory, borderColor: "#ff1744", borderWidth: 2, pointRadius: 0 },
                { label: "Intake Temp", data: intakeTempHistory, borderColor: "#0077ff", borderWidth: 2, pointRadius: 0 }
            ]
        },
        options: chartDefaultOptions
    });

    // Page 3 - Battery & Oil Chart
    const battOilChartCtx = document.getElementById("battOilChartCanvas").getContext("2d");
    const battOilChart = new Chart(battOilChartCtx, {
        type: "line",
        data: {
            labels: timeLabels,
            datasets: [
                { label: "Batt V", data: battHistory, borderColor: "#ffb700", borderWidth: 2, pointRadius: 0, yAxisID: "y" },
                { label: "Oil Press", data: oilHistory, borderColor: "#00e676", borderWidth: 2, pointRadius: 0, yAxisID: "y1" }
            ]
        },
        options: {
            ...chartDefaultOptions,
            scales: {
                x: { ticks: { display: false } },
                y: { type: "linear", display: true, position: "left", min: 9, max: 16, ticks: { color: "#ffb700", font: { size: 8 } } },
                y1: { type: "linear", display: true, position: "right", min: 0, max: 500, grid: { drawOnChartArea: false }, ticks: { color: "#00e676", font: { size: 8 } } }
            }
        }
    });

    // --- Update Telemetry UI Engine ---
    let lastTelemetry = null;

    function updateUI(data) {
        lastTelemetry = data;

        if (data.status !== "ok" || data.connected === false) {
            connBadge.className = "status-pill disconnected";
            connDot.style.backgroundColor = "var(--accent-red)";
            connText.innerText = "OFFLINE";
            pingText.innerText = "--ms";

            if (gpsBadge) {
                gpsBadge.className = "status-pill disconnected";
                if (gpsDot) gpsDot.style.backgroundColor = "var(--accent-red)";
                if (gpsText) gpsText.innerText = "🛰️ OFFLINE";
            }

            digitalRpm.innerText = "--";
            renderRpmGauge(0);

            if (headerHours) headerHours.innerText = "-- HRS";

            if (tpsVal) tpsVal.innerText = "--";
            if (tpsFill) tpsFill.style.width = "0%";
            if (tpsDegVal) tpsDegVal.innerText = "--";

            if (engineTempVal) engineTempVal.innerText = "--";
            if (tempStatusText) {
                tempStatusText.innerText = "OFFLINE / IGNITION OFF";
                tempStatusText.style.color = "#8a9bb0";
            }

            if (batteryVal) batteryVal.innerText = "--";
            if (battStatusText) {
                battStatusText.innerText = "OFFLINE";
                battStatusText.style.color = "#8a9bb0";
            }

            if (mapVal) mapVal.innerText = "--";
            if (baroVal) baroVal.innerText = "--";
            if (fuelRateVal) fuelRateVal.innerText = "--";

            if (gpsSpeedVal) gpsSpeedVal.innerText = "--";
            if (gpsHeadingVal) gpsHeadingVal.innerText = "--° N";
            if (fuelEconomyVal) fuelEconomyVal.innerText = "-- L/NM";

            updateFlag(flagOil, false, "OIL --", "LOW OIL");
            updateFlag(flagTemp, false, "TEMP --", "OVERHEAT");
            updateFlag(flagBatt, false, "BATT --", "LOW VOLT");
            updateFlag(flagCheck, false, "ENG --", "CHECK ENG");
            if (flagIsc) flagIsc.innerText = "ISC: --";
            if (fuelRangeHoursElem) fuelRangeHoursElem.innerText = "--";

            hideAlertBanner();
            return;
        }

        // Connected Online State
        connBadge.className = "status-pill connected";
        connDot.style.backgroundColor = "var(--accent-green)";
        connText.innerText = "ONLINE";

        // GPS Receiver Status
        if (data.gps) {
            const gpsData = data.gps;
            if (gpsBadge) {
                if (gpsData.has_fix) {
                    gpsBadge.className = "status-pill connected";
                    if (gpsDot) gpsDot.style.backgroundColor = "var(--accent-cyan)";
                    if (gpsText) gpsText.innerText = `🛰️ ${gpsData.satellites || 0} SATS`;
                } else {
                    gpsBadge.className = "status-pill disconnected";
                    if (gpsDot) gpsDot.style.backgroundColor = "var(--accent-red)";
                    if (gpsText) gpsText.innerText = "🛰️ NO FIX";
                }
            }

            if (gpsSpeedVal) gpsSpeedVal.innerText = (data.gps_speed_kts || 0.0).toFixed(1);
            if (gpsHeadingVal) gpsHeadingVal.innerText = `${Math.round(data.gps_heading_deg || 0)}° ${data.gps_cardinal || 'N'}`;
            if (fuelEconomyVal) {
                fuelEconomyVal.innerText = (data.fuel_economy_l_nm > 0) ? `${data.fuel_economy_l_nm.toFixed(2)} L/NM` : "-- L/NM";
            }
        }

        // 1. Tachometer & TPS
        const rpm = Math.round(data.rpm || 0);
        digitalRpm.innerText = rpm.toString();
        renderRpmGauge(rpm);

        const tps = data.tps_percent || 0;
        const tpsV = (data.tps_volts || 0.679).toFixed(3);
        const tpsDeg = (data.tps_deg || -0.5).toFixed(1);
        tpsVal.innerText = `${tps.toFixed(1)}% (${tpsV}V)`;
        tpsFill.style.width = `${Math.max(0, Math.min(100, tps))}%`;
        tpsDegVal.innerText = `${tpsDeg}°`;

        // 2. Engine Hours
        if (data.engine_hours) {
            headerHours.innerText = `${data.engine_hours.toFixed(1)} HRS`;
        }

        // 3. Engine Temperature
        const tempC = data.engine_temp_c || 0;
        const tempF = data.engine_temp_f || (tempC * 1.8 + 32);
        engineTempVal.innerText = useFahrenheit ? tempF.toFixed(1) : tempC.toFixed(1);
        engineTempUnit.innerText = useFahrenheit ? "°F" : "°C";

        if (tempC > 95) {
            tempStatusText.innerText = "OVERHEAT WARNING!";
            tempStatusText.style.color = "#ff1744";
        } else if (tempC > 75) {
            tempStatusText.innerText = "WARM";
            tempStatusText.style.color = "#ffb700";
        } else {
            tempStatusText.innerText = "NORMAL (33-75°C)";
            tempStatusText.style.color = "#8a9bb0";
        }

        // 4. Battery Voltage
        const battV = data.battery_voltage || 12.89;
        batteryVal.innerText = battV.toFixed(2);
        if (battV > 13.4) {
            battStatusText.innerText = "ALT. CHARGING";
            battStatusText.style.color = "#00e676";
        } else if (battV < 11.8) {
            battStatusText.innerText = "LOW VOLTAGE!";
            battStatusText.style.color = "#ff1744";
        } else {
            battStatusText.innerText = "STANDBY";
            battStatusText.style.color = "#8a9bb0";
        }

        // 5. Intake MAP Pressure & Baro
        if (mapVal) mapVal.innerText = (data.map_kpa || 99.09).toFixed(2);
        if (baroVal) baroVal.innerText = `${(data.baro_hpa || 990.9).toFixed(1)} hPa`;

        // 6. Fuel Rate, Injector Pulse & Fuel Tank Sync
        if (fuelRateVal) fuelRateVal.innerText = (data.fuel_rate_lh || 0.0).toFixed(2);
        if (injectorVal) injectorVal.innerText = `${(data.injector_ms || 0.0).toFixed(2)} ms`;

        if (data.current_fuel_liters !== undefined) {
            updateFuelDisplay({
                current_fuel_liters: data.current_fuel_liters,
                tank_capacity_liters: data.tank_capacity_liters || 170.0,
                trip_consumed_liters: data.trip_consumed_liters || 0.0
            });
        }

        // 7. Alarms & Status Flags
        const warnings = data.warnings || {};
        updateFlag(flagOil, warnings.low_oil_pressure, "OIL OK", "LOW OIL");
        updateFlag(flagTemp, warnings.overheat, "TEMP OK", "OVERHEAT");
        updateFlag(flagBatt, warnings.low_voltage, "BATT OK", "LOW VOLT");
        updateFlag(flagCheck, warnings.check_engine, "ENG OK", "CHECK ENG");

        if (data.isc_opening_pct !== undefined) {
            flagIsc.innerText = `ISC: ${Math.round(data.isc_opening_pct)}%`;
        }

        // Alarm Banner
        if (warnings.overheat) {
            showAlertBanner("ENGINE OVERHEAT WARNING", "Reduce throttle immediately and inspect cooling intake!");
        } else if (warnings.low_oil_pressure) {
            showAlertBanner("LOW OIL PRESSURE ALARM", "Shutdown engine immediately and check oil level!");
        } else if (warnings.low_voltage) {
            showAlertBanner("LOW BATTERY VOLTAGE", "Battery voltage dropped below 11.8V!");
        } else {
            hideAlertBanner();
        }

        // 8. History Trends Chart Push
        const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        timeLabels.push(nowStr);
        rpmHistory.push(rpm);
        fuelHistory.push(data.fuel_rate_lh || 0.0);
        mapHistory.push(data.map_kpa || 99.09);
        tpsHistory.push(tps);
        engTempHistory.push(useFahrenheit ? tempF : tempC);
        intakeTempHistory.push(useFahrenheit ? (data.intake_temp_f || 79.7) : (data.intake_temp_c || 26.6));
        battHistory.push(battV);
        oilHistory.push(data.oil_pressure_kpa || 0);

        if (timeLabels.length > MAX_HISTORY) {
            timeLabels.shift();
            rpmHistory.shift();
            fuelHistory.shift();
            mapHistory.shift();
            tpsHistory.shift();
            engTempHistory.shift();
            intakeTempHistory.shift();
            battHistory.shift();
            oilHistory.shift();
        }

        rpmChart.update();
        mapTpsChart.update();
        tempChart.update();
        battOilChart.update();
    }

    function updateFlag(elem, isAlarm, okText, alarmText) {
        if (isAlarm) {
            elem.innerText = alarmText;
            elem.className = "diag-flag alarm-active";
        } else {
            elem.innerText = okText;
            elem.className = "diag-flag";
        }
    }

    function showAlertBanner(title, detail) {
        alertTitle.innerText = title;
        alertDetail.innerText = detail;
        alertBanner.classList.remove("hidden");
    }

    function hideAlertBanner() {
        alertBanner.classList.add("hidden");
    }

    // --- WebSocket Manager ---
    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            connBadge.className = "status-pill connected";
            connDot.style.backgroundColor = "var(--accent-green)";
            connText.innerText = "ONLINE";
            pingStartTime = Date.now();
            ws.send(JSON.stringify({ type: "ping" }));
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "pong") {
                    currentLatency = Date.now() - pingStartTime;
                    pingText.innerText = `${currentLatency}ms`;
                    setTimeout(() => {
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            pingStartTime = Date.now();
                            ws.send(JSON.stringify({ type: "ping" }));
                        }
                    }, 3000);
                } else {
                    updateUI(msg);
                }
            } catch (e) {
                console.error("Error parsing WebSocket packet:", e);
            }
        };

        ws.onclose = () => {
            connBadge.className = "status-pill disconnected";
            connDot.style.backgroundColor = "var(--accent-red)";
            connText.innerText = "OFFLINE";
            pingText.innerText = "--ms";
            reconnectTimer = setTimeout(connectWebSocket, 2000);
        };

        ws.onerror = () => {
            ws.close();
        };
    }

    connectWebSocket();
});
