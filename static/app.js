/**
 * Yamaha YDS Real-Time Telemetry Dashboard Frontend Engine.
 * Handles Canvas Gauge Rendering, WebSocket Auto-Reconnect, Chart.js Trends, and Alarm Overlays.
 */

document.addEventListener("DOMContentLoaded", () => {
    // --- State Variables ---
    let ws = null;
    let reconnectTimer = null;
    let pingStartTime = 0;
    let currentLatency = 0;

    let useFahrenheit = false;
    let currentTelemetry = null;

    // History data arrays for Chart.js (max 40 data points ~8 seconds of history)
    const MAX_HISTORY = 40;
    const timeLabels = [];
    const rpmHistory = [];
    const fuelHistory = [];

    // --- DOM Elements ---
    const connBadge = document.getElementById("connection-badge");
    const connDot = document.getElementById("conn-dot");
    const connText = document.getElementById("conn-text");
    const pingText = document.getElementById("ping-text");
    const mockBadge = document.getElementById("mock-badge");
    const tempToggleBtn = document.getElementById("temp-toggle-btn");

    const alertBanner = document.getElementById("alert-banner");
    const alertTitle = document.getElementById("alert-title");
    const alertDetail = document.getElementById("alert-detail");

    const digitalRpm = document.getElementById("digital-rpm-val");
    const tpsVal = document.getElementById("tps-value");
    const tpsFill = document.getElementById("tps-fill");

    const fuelRateVal = document.getElementById("fuel-rate-val");
    const engineTempVal = document.getElementById("engine-temp-val");
    const engineTempUnit = document.getElementById("engine-temp-unit");
    const tempCardElem = document.getElementById("temp-card-elem");

    const batteryVal = document.getElementById("battery-val");
    const battCardElem = document.getElementById("batt-card-elem");
    const mapVal = document.getElementById("map-val");
    const injectorVal = document.getElementById("injector-val");
    const engineHoursVal = document.getElementById("engine-hours-val");

    const flagOil = document.getElementById("flag-oil");
    const flagTemp = document.getElementById("flag-temp");
    const flagCheck = document.getElementById("flag-check");
    const flagBatt = document.getElementById("flag-batt");

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

        // Angles for gauge (225 degrees total arc: 135deg to 405deg)
        const startAngle = 0.75 * Math.PI; // 135 deg
        const endAngle = 2.25 * Math.PI;   // 405 deg
        const totalAngle = endAngle - startAngle;

        const maxRpm = 6000;
        const clampedRpm = Math.max(0, Math.min(maxRpm, rpmValue));
        const fillPct = clampedRpm / maxRpm;
        const currentAngle = startAngle + (fillPct * totalAngle);

        // 1. Background Arc Track
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, startAngle, endAngle, false);
        ctx.lineWidth = 18;
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.lineCap = "round";
        ctx.stroke();

        // 2. Redline Zone Arc (5200 RPM to 6000 RPM)
        const redlineStart = startAngle + ((5200 / maxRpm) * totalAngle);
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, redlineStart, endAngle, false);
        ctx.lineWidth = 18;
        ctx.strokeStyle = "rgba(255, 23, 68, 0.35)";
        ctx.lineCap = "round";
        ctx.stroke();

        // 3. Dynamic Active RPM Arc (Gradient Fill)
        if (clampedRpm > 10) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, startAngle, currentAngle, false);
            ctx.lineWidth = 18;
            ctx.lineCap = "round";

            const gradient = ctx.createConicGradient(startAngle, centerX, centerY);
            gradient.addColorStop(0, "#00e5ff");
            gradient.addColorStop(0.6, "#00e676");
            gradient.addColorStop(0.85, "#ffb700");
            gradient.addColorStop(1.0, "#ff1744");

            ctx.strokeStyle = gradient;
            ctx.stroke();
        }

        // 4. Tick Marks & Numbers
        for (let i = 0; i <= 6; i++) {
            const tickRpm = i * 1000;
            const tickPct = tickRpm / maxRpm;
            const angle = startAngle + (tickPct * totalAngle);

            const innerRadius = radius - 16;
            const outerRadius = radius - 6;

            const x1 = centerX + Math.cos(angle) * innerRadius;
            const y1 = centerY + Math.sin(angle) * innerRadius;
            const x2 = centerX + Math.cos(angle) * outerRadius;
            const y2 = centerY + Math.sin(angle) * outerRadius;

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.lineWidth = i >= 5 ? 3 : 2;
            ctx.strokeStyle = i >= 5 ? "#ff1744" : "rgba(255, 255, 255, 0.4)";
            ctx.stroke();

            // Label
            const textRadius = radius - 30;
            const tx = centerX + Math.cos(angle) * textRadius;
            const ty = centerY + Math.sin(angle) * textRadius;

            ctx.font = "bold 13px 'Chakra Petch', sans-serif";
            ctx.fillStyle = i >= 5 ? "#ff1744" : "#8a9bb0";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(i.toString(), tx, ty);
        }

        // 5. Center Pointer / Needle
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(currentAngle);

        ctx.beginPath();
        ctx.moveTo(-10, 0);
        ctx.lineTo(radius - 22, 0);
        ctx.lineWidth = 4;
        ctx.strokeStyle = clampedRpm >= 5200 ? "#ff1744" : "#00e5ff";
        ctx.shadowColor = clampedRpm >= 5200 ? "#ff1744" : "#00e5ff";
        ctx.shadowBlur = 10;
        ctx.stroke();

        ctx.restore();

        // Needle Pivot Center Cap
        ctx.beginPath();
        ctx.arc(centerX, centerY, 8, 0, 2 * Math.PI);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
    }

    // Render initial empty gauge
    renderRpmGauge(0);

    // --- Chart.js Real-time Trend Setup ---
    const chartCtx = document.getElementById("trendChart").getContext("2d");
    const trendChart = new Chart(chartCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'RPM',
                    data: rpmHistory,
                    borderColor: '#00e5ff',
                    backgroundColor: 'rgba(0, 229, 255, 0.08)',
                    fill: true,
                    tension: 0.3,
                    yAxisID: 'yRPM',
                    pointRadius: 0
                },
                {
                    label: 'Fuel (L/h)',
                    data: fuelHistory,
                    borderColor: '#ffb700',
                    backgroundColor: 'transparent',
                    borderDash: [4, 4],
                    tension: 0.3,
                    yAxisID: 'yFuel',
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    display: false
                },
                yRPM: {
                    type: 'linear',
                    position: 'left',
                    min: 0,
                    max: 6000,
                    ticks: { color: '#8a9bb0', font: { size: 10 } },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                yFuel: {
                    type: 'linear',
                    position: 'right',
                    min: 0,
                    max: 60,
                    ticks: { color: '#ffb700', font: { size: 10 } },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });

    // --- WebSocket Manager ---
    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

        console.log(`Connecting to WebSocket: ${wsUrl}`);
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket connected!");
            connBadge.classList.remove("disconnected");
            connBadge.classList.add("connected");
            connDot.style.backgroundColor = "var(--accent-green)";
            connText.textContent = "LIVE";

            // Start ping timer
            pingStartTime = Date.now();
            ws.send("ping");

            if (reconnectTimer) {
                clearInterval(reconnectTimer);
                reconnectTimer = null;
            }
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Handle ping response latency
                if (data.pong) {
                    currentLatency = Date.now() - pingStartTime;
                    pingText.textContent = `${currentLatency} ms`;
                    return;
                }

                // Process Telemetry Frame
                updateDashboardUI(data);

            } catch (err) {
                console.error("Error parsing WebSocket JSON payload:", err);
            }
        };

        ws.onclose = () => {
            console.warn("WebSocket connection lost.");
            connBadge.classList.remove("connected");
            connBadge.classList.add("disconnected");
            connDot.style.backgroundColor = "var(--accent-red)";
            connText.textContent = "DISCONNECTED";
            pingText.textContent = "-- ms";

            // Schedule reconnect
            if (!reconnectTimer) {
                reconnectTimer = setInterval(connectWebSocket, 2000);
            }
        };

        ws.onerror = (err) => {
            console.error("WebSocket error:", err);
            ws.close();
        };
    }

    // Measure ping latency every 3 seconds
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            pingStartTime = Date.now();
            ws.send("ping");
        }
    }, 3000);

    // --- Temperature Unit Toggle ---
    tempToggleBtn.addEventListener("click", () => {
        useFahrenheit = !useFahrenheit;
        tempToggleBtn.textContent = useFahrenheit ? "°F" : "°C";
        if (currentTelemetry) {
            updateDashboardUI(currentTelemetry);
        }
    });

    // --- Update UI with Telemetry Data ---
    function updateDashboardUI(data) {
        currentTelemetry = data;

        // Toggle Mock Badge
        if (data.is_mock) {
            mockBadge.classList.remove("mock-hidden");
        } else {
            mockBadge.classList.add("mock-hidden");
        }

        // 1. Tachometer & TPS
        const rpm = Math.round(data.rpm || 0);
        digitalRpm.textContent = rpm.toLocaleString();
        renderRpmGauge(rpm);

        const tps = data.tps_percent || 0;
        tpsVal.textContent = `${tps.toFixed(1)} %`;
        tpsFill.style.width = `${Math.min(100, Math.max(0, tps))}%`;

        // 2. Fuel Consumption
        fuelRateVal.textContent = (data.fuel_rate_lh || 0).toFixed(2);

        // 3. Engine Temperature
        const tempC = data.engine_temp_c || 0;
        const tempF = data.engine_temp_f || 32;
        if (useFahrenheit) {
            engineTempVal.textContent = Math.round(tempF);
            engineTempUnit.textContent = "°F";
        } else {
            engineTempVal.textContent = Math.round(tempC);
            engineTempUnit.textContent = "°C";
        }

        // Temp warning border color
        if (tempC >= 85) {
            tempCardElem.style.borderColor = "var(--accent-red)";
        } else if (tempC >= 75) {
            tempCardElem.style.borderColor = "var(--accent-amber)";
        } else {
            tempCardElem.style.borderColor = "var(--bg-card-border)";
        }

        // 4. Battery Voltage
        const batt = data.battery_voltage || 0;
        batteryVal.textContent = batt.toFixed(1);
        if (batt < 11.8 || batt > 15.2) {
            battCardElem.style.borderColor = "var(--accent-red)";
        } else {
            battCardElem.style.borderColor = "var(--bg-card-border)";
        }

        // 5. MAP & Injector
        mapVal.textContent = (data.map_kpa || 0).toFixed(1);
        injectorVal.textContent = (data.injector_ms || 0).toFixed(2);
        engineHoursVal.textContent = `${(data.engine_hours || 0).toFixed(1)} HRS`;

        // 6. Diagnostics & Alerts
        const warnings = data.warnings || {};

        // Oil Flag
        if (warnings.low_oil_pressure) {
            flagOil.textContent = "LOW OIL";
            flagOil.classList.add("alert");
        } else {
            flagOil.textContent = "OIL OK";
            flagOil.classList.remove("alert");
        }

        // Temp Flag
        if (warnings.overheat || tempC >= 85) {
            flagTemp.textContent = "OVERHEAT";
            flagTemp.classList.add("alert");
        } else {
            flagTemp.textContent = "TEMP OK";
            flagTemp.classList.remove("alert");
        }

        // Check Engine Flag
        if (warnings.check_engine) {
            flagCheck.textContent = "ECU FAULT";
            flagCheck.classList.add("alert");
        } else {
            flagCheck.textContent = "CHECK OK";
            flagCheck.classList.remove("alert");
        }

        // Battery Flag
        if (warnings.low_voltage || batt < 11.8) {
            flagBatt.textContent = "LOW BATT";
            flagBatt.classList.add("alert");
        } else {
            flagBatt.textContent = "BATT OK";
            flagBatt.classList.remove("alert");
        }

        // Prominent Alert Banner Display
        if (warnings.overheat || warnings.low_oil_pressure) {
            alertBanner.classList.remove("hidden");
            if (warnings.overheat) {
                alertTitle.textContent = "⚠️ ENGINE OVERHEAT ALARM";
                alertDetail.textContent = `Engine temp reaching ${tempC.toFixed(1)}°C! Reduce speed immediately!`;
            } else if (warnings.low_oil_pressure) {
                alertTitle.textContent = "⚠️ LOW OIL PRESSURE ALARM";
                alertDetail.textContent = "Critical engine oil pressure drop detected!";
            }
        } else {
            alertBanner.classList.add("hidden");
        }

        // 7. Update Live Chart History
        const nowStr = new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });
        timeLabels.push(nowStr);
        rpmHistory.push(rpm);
        fuelHistory.push(data.fuel_rate_lh || 0);

        if (timeLabels.length > MAX_HISTORY) {
            timeLabels.shift();
            rpmHistory.shift();
            fuelHistory.shift();
        }

        trendChart.update('none'); // Update without full re-animation for performance
    }

    // Initialize Connection
    connectWebSocket();
});
