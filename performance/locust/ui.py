"""Local-only interactive configuration UI for Locust profiles."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from config import LoadConfig, Profile
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="Locust Performance Control",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

PAGE = """
<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Locust Performance Control</title>
<style>
    :root {
        color-scheme: dark;
        font-family: system-ui, sans-serif;
        background: #111;
        color: #eee;
    }

    * { box-sizing: border-box; }

    body {
        max-width: 850px;
        margin: 35px auto;
        padding: 0 18px;
    }

    h1 { margin-bottom: 24px; }

    .panel {
        border: 1px solid #383838;
        border-radius: 14px;
        padding: 18px;
    }

    .label {
        font-size: 13px;
        font-weight: 600;
        margin-bottom: 10px;
    }

    .tabs, .units {
        display: flex;
        gap: 5px;
        margin-bottom: 18px;
    }

    button {
        cursor: pointer;
        font: inherit;
        color: inherit;
    }

    .tab, .unit {
        flex: 1;
        border: 0;
        border-radius: 9px;
        background: transparent;
        padding: 9px 5px;
    }

    .tab.active, .unit.active {
        background: #303030;
        font-weight: 600;
    }

    .unit { background: #1b1b1b; }

    .control {
        margin-bottom: 17px;
    }

    .control-header {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 7px;
        font-size: 13px;
    }

    .control-body {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    input[type="range"] {
        flex: 1;
        min-width: 0;
        accent-color: #2196f3;
    }

    input[type="number"] {
        width: 108px;
        padding: 10px;
        background: #111;
        border: 1px solid #414141;
        border-radius: 9px;
        color: #eee;
        font: inherit;
    }

    .fields {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
    }

    .fields .control-body {
        flex-wrap: wrap;
    }

    .fields input[type="number"] {
        width: 100%;
    }

    .fields input[type="range"] {
        width: 100%;
    }

    .chart-panel {
        background: #222;
        border: 1px solid #383838;
        border-radius: 12px;
        padding: 15px;
        margin-top: 14px;
    }

    .chart-panel p {
        font-size: 12px;
        color: #aaa;
    }

    svg {
        display: block;
        width: 100%;
        height: auto;
    }

    .legend {
        text-align: center;
        font-size: 12px;
        color: #aaa;
        margin-top: 5px;
    }

    .dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        background: #2196f3;
        border-radius: 50%;
        margin-right: 5px;
    }

    .summary {
        display: flex;
        justify-content: space-between;
        gap: 18px;
        margin: 16px 0;
    }

    .summary small {
        display: block;
        color: #aaa;
    }

    .summary strong {
        display: block;
        margin-top: 4px;
    }

    .action {
        width: 100%;
        padding: 11px;
        border: 1px solid #444;
        border-radius: 10px;
        background: #1b1b1b;
    }

    .action:hover { background: #303030; }

    .note {
        font-size: 12px;
        color: #aaa;
        margin-top: 16px;
    }

    .error {
        color: #ff8e8e;
        min-height: 20px;
        font-size: 13px;
    }

    @media (max-width: 600px) {
        .fields { grid-template-columns: 1fr; }
        .tabs { flex-wrap: wrap; }
        .tab { min-width: 40%; }
    }
</style>
</head>
<body>

<h1>Locust Performance Control</h1>

<div class="panel">
    <div class="label">Strategie</div>
    <div class="tabs" id="profiles"></div>

    <div class="label">Jednotka intenzity</div>
    <div class="units">
        <button class="unit active" data-unit="rpm">req/min</button>
        <button class="unit" data-unit="rps">req/s (RPS)</button>
    </div>

    <div id="controls"></div>
    <div class="error" id="error"></div>

    <div class="chart-panel">
        <strong>Náhled cílové zátěže</strong>
        <p>
            Křivka podle nastavených hodnot.
            Nejde o měření skutečného provozu.
        </p>

        <svg id="chart" viewBox="0 0 700 260"
             role="img" aria-label="Graf cílové zátěže"></svg>

        <div class="legend">
            <span class="dot"></span>Cílové tempo
        </div>
    </div>

    <div class="summary">
        <div>
            <small>Cílové maximum</small>
            <strong id="maximum"></strong>
        </div>
        <div>
            <small>Celková délka</small>
            <strong id="duration"></strong>
        </div>
    </div>

    <button class="action" id="run" type="button">
        Run
    </button>
    <button class="action" id="github-run" type="button">
        Run GitHub
    </button>
    <button class="action" id="stop" type="button">
        Stop
    </button>
    <p id="run-status" aria-live="polite">Local: Idle</p>
    <p id="github-status" aria-live="polite">GitHub: Idle</p>
    <p id="github-link"></p>
</div>

<p class="note">
    Lokální Run/Stop ovládá lokální proces. Run GitHub spouští
    vzdálený test; průběh a reporty jsou dostupné v GitHub Actions.
</p>

<script>
"use strict";

const defaults = {
    hold: {
        rpm: 60,
        duration: 60,
        tolerance: 20
    },
    bell: {
        rpm: 120,
        up: 10,
        peak: 10,
        down: 10,
        tolerance: 20
    },
    "hold-bell": {
        baseline: 60,
        rpm: 120,
        up: 10,
        peak: 10,
        down: 10,
        tolerance: 20
    },
    recovery: {
        baseline: 60,
        rpm: 180,
        duration: 10,
        peak: 10,
        recovery: 10,
        tolerance: 20
    }
};

const profiles = {
    hold: "Hold",
    bell: "Bell",
    "hold-bell": "Hold + Bell",
    recovery: "Recovery"
};

const labels = {
    rpm: "Cílová intenzita",
    baseline: "Základní intenzita",
    duration: "Délka / Baseline",
    up: "Ramp-up",
    peak: "Vrchol / Spike",
    down: "Ramp-down",
    recovery: "Recovery",
    tolerance: "Tolerance"
};

let profile = "bell";
let unit = "rpm";
const state = structuredClone(defaults);

const profilesElement = document.getElementById("profiles");
const controlsElement = document.getElementById("controls");
const errorElement = document.getElementById("error");

function isRate(key) {
    return key === "rpm" || key === "baseline";
}

function displayed(value, key) {
    if (isRate(key) && unit === "rps") {
        return Math.round(value / 60 * 100) / 100;
    }
    return value;
}

function stored(value, key) {
    if (isRate(key) && unit === "rps") {
        return value * 60;
    }
    return value;
}

function formatNumber(value) {
    return Number(value.toFixed(2)).toLocaleString("cs-CZ");
}

function configureTabs() {
    profilesElement.innerHTML = "";

    for (const [key, title] of Object.entries(profiles)) {
        const button = document.createElement("button");
        button.className = "tab" + (profile === key ? " active" : "");
        button.textContent = title;

        button.addEventListener("click", () => {
            profile = key;
            render();
        });

        profilesElement.append(button);
    }

    document.querySelectorAll(".unit").forEach(button => {
        button.classList.toggle(
            "active",
            button.dataset.unit === unit
        );
    });
}

function fieldLimits(key) {
    if (isRate(key)) {
        return unit === "rpm"
            ? {min: 1, max: 3000, sliderMax: 3000, step: 1}
            : {min: 0.01, max: 50, sliderMax: 16.67, step: 0.01};
    }

    if (key === "tolerance") {
        return {min: 0, max: 50, sliderMax: 50, step: 1};
    }

    return {
        min: 1,
        max: 3600,
        sliderMax: 300,
        step: 1
    };
}

function addControl(key, value) {
    const limits = fieldLimits(key);
    const wrapper = document.createElement("div");
    wrapper.className = "control";

    const header = document.createElement("div");
    header.className = "control-header";

    const label = document.createElement("label");
    label.textContent = labels[key];

    const suffix = document.createElement("span");
    suffix.textContent = isRate(key)
        ? unit === "rpm" ? "req/min" : "req/s"
        : key === "tolerance" ? "%" : "s";

    header.append(label, suffix);

    const body = document.createElement("div");
    body.className = "control-body";

    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = limits.min;
    slider.max = limits.sliderMax;
    slider.step = limits.step;
    slider.value = Math.min(displayed(value, key), limits.sliderMax);

    const number = document.createElement("input");
    number.type = "number";
    number.min = limits.min;
    number.max = limits.max;
    number.step = limits.step;
    number.value = displayed(value, key);
    number.setAttribute("aria-label", labels[key]);

    slider.addEventListener("input", () => {
        number.value = slider.value;
        updateValue(key, Number(slider.value));
    });

    number.addEventListener("input", () => {
        if (number.value === "" || !number.validity.valid) {
            errorElement.textContent = "Zkontroluj zadanou hodnotu.";
            return;
        }

        slider.value = Math.min(Number(number.value), limits.sliderMax);
        updateValue(key, Number(number.value));
    });

    body.append(slider, number);
    wrapper.append(header, body);
    controlsElement.append(wrapper);
}

function updateValue(key, value) {
    state[profile][key] = stored(value, key);
    updateChart();
}

function totalDuration(config) {
    if (profile === "hold") {
        return config.duration;
    }

    if (profile === "recovery") {
        return config.duration + config.peak + config.recovery;
    }

    return config.up + config.peak + config.down;
}

function targetRate(t, config) {
    if (profile === "hold") {
        return config.rpm;
    }

    if (profile === "recovery") {
        if (t < config.duration) {
            return config.baseline;
        }

        if (t < config.duration + config.peak) {
            return config.rpm;
        }

        return config.baseline;
    }

    const baseline = profile === "hold-bell"
        ? config.baseline : 0;

    const amplitude = config.rpm - baseline;

    if (t < config.up) {
        return baseline + amplitude * t / config.up;
    }

    if (t <= config.up + config.peak) {
        return config.rpm;
    }

    const remaining = totalDuration(config) - t;

    return baseline + amplitude * Math.max(0, remaining / config.down);
}

function validConfiguration(config) {
    const values = Object.entries(config);

    if (values.some(([, value]) => !Number.isFinite(value))) {
        return false;
    }

    if (config.rpm <= 0 || config.rpm > 3000) {
        return false;
    }

    if (
        config.baseline !== undefined &&
        (config.baseline <= 0 || config.baseline > 3000)
    ) {
        return false;
    }

    if (
        (profile === "hold-bell" || profile === "recovery") &&
        config.rpm <= config.baseline
    ) {
        return false;
    }

    return totalDuration(config) > 0;
}

function updateChart() {
    const config = state[profile];
    const svg = document.getElementById("chart");

    if (!validConfiguration(config)) {
        errorElement.textContent =
            "Neplatná konfigurace: maximum musí být vyšší než baseline.";
        svg.innerHTML = "";
        return;
    }

    errorElement.textContent = "";

    const duration = totalDuration(config);
    const maxRate = config.rpm;
    const multiplier = unit === "rpm" ? 1 : 1 / 60;

    const left = 54;
    const top = 14;
    const width = 625;
    const height = 195;
    const maxY = Math.max(maxRate * multiplier * 1.1, 1);

    const x = t => left + t / duration * width;
    const y = rate => top + height - rate * multiplier / maxY * height;

    let svgContent = "";

    for (let i = 0; i <= 4; i++) {
        const rate = maxY * i / 4;
        const py = top + height - i * height / 4;

        svgContent += `
            <line x1="${left}" y1="${py}" x2="${left + width}"
                  y2="${py}" stroke="#454545"
                  stroke-dasharray="3 4"/>
            <text x="${left - 8}" y="${py + 4}"
                  text-anchor="end" font-size="11"
                  fill="#aaa">${formatNumber(rate)}</text>
        `;
    }

    for (let i = 0; i <= 6; i++) {
        const t = duration * i / 6;

        svgContent += `
            <text x="${x(t)}" y="${top + height + 19}"
                  text-anchor="middle" font-size="11"
                  fill="#aaa">${formatNumber(t)}</text>
        `;
    }

    const points = [];
    const count = 180;

    for (let i = 0; i <= count; i++) {
        const t = duration * i / count;
        points.push(
            `${x(t).toFixed(2)},${y(targetRate(t, config)).toFixed(2)}`
        );
    }

    // Preserve vertical transitions at the Recovery phase boundaries.
    if (profile === "recovery") {
        const boundaries = [
            {time: config.duration, before: config.baseline, after: config.rpm},
            {
                time: config.duration + config.peak,
                before: config.rpm,
                after: config.baseline
            }
        ];

        const recoveryPoints = [
            [0, config.baseline],
            [boundaries[0].time, boundaries[0].before],
            [boundaries[0].time, boundaries[0].after],
            [boundaries[1].time, boundaries[1].before],
            [boundaries[1].time, boundaries[1].after],
            [duration, config.baseline]
        ];

        points.length = 0;

        for (const [t, rate] of recoveryPoints) {
            points.push(`${x(t).toFixed(2)},${y(rate).toFixed(2)}`);
        }
    }

    svgContent += `
        <polyline points="${points.join(" ")}"
                  fill="none"
                  stroke="#2196f3"
                  stroke-width="3"
                  stroke-linejoin="round"/>
        <text x="350" y="253"
              text-anchor="middle" font-size="12"
              fill="#bbb">Sekundy</text>
    `;

    svg.innerHTML = svgContent;

    document.getElementById("maximum").textContent =
        `${formatNumber(maxRate * multiplier)} ${unit === "rpm" ? "req/min" : "req/s"}`;

    document.getElementById("duration").textContent =
        `${formatNumber(duration)} s`;
}

function buildCommand() {
    const config = state[profile];
    const command = [
        "uv run --locked python performance/locust/run.py",
        profile
    ];

    const options = {
        rpm: "--rpm",
        baseline: "--baseline-rpm",
        duration: profile === "recovery" ? "--baseline" : "--duration",
        up: "--ramp-up",
        peak: profile === "recovery" ? "--spike" : "--peak",
        down: "--ramp-down",
        recovery: "--recovery",
        tolerance: "--tolerance-pct"
    };

    for (const [key, value] of Object.entries(config)) {
        command.push(options[key], String(Number(value.toFixed(4))));
    }

    return command.join(" ");
}

document.querySelectorAll(".unit").forEach(button => {
    button.addEventListener("click", () => {
        unit = button.dataset.unit;
        render();
    });
});


async function controlTest(action, payload = null) {
    const response = await fetch("/api/" + action, {
        method: action === "status" ? "GET" : "POST",
        headers: {"Content-Type": "application/json"},
        body: payload ? JSON.stringify(payload) : null
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Požadavek selhal");
    }

    return data;
}

const githubStatusElement = document.getElementById("github-status");
const githubLinkElement = document.getElementById("github-link");
const githubRunButton = document.getElementById("github-run");
let githubRequestId = null;
let githubPolling = false;
let githubDispatching = false;

async function refreshGithubStatus() {
    if (!githubRequestId || githubPolling) {
        return;
    }

    githubPolling = true;
    const requestId = githubRequestId;

    try {
        const response = await fetch(
            "/api/github/status?request_id=" + encodeURIComponent(requestId)
        );
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "GitHub status unavailable");
        }
        // A newly started run may not be visible in GitHub's API immediately.
        if (requestId !== githubRequestId) {
            return;
        }

        githubStatusElement.textContent =
            "GitHub: " + (data.conclusion || data.state);

        if (data.url) {
            const link = document.createElement("a");
            link.href = data.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "Otevřít GitHub Actions a reporty";
            githubLinkElement.replaceChildren(link);
        }

        if (data.state === "completed") {
            githubRequestId = null;
            githubRunButton.disabled = false;
        }
    } catch (error) {
        if (requestId === githubRequestId) {
            githubStatusElement.textContent =
                "GitHub status error: " + error.message;
        }
    } finally {
        githubPolling = false;
    }
}

setInterval(refreshGithubStatus, 5000);

const statusElement = document.getElementById("run-status");
const runButton = document.getElementById("run");
const stopButton = document.getElementById("stop");

async function refreshStatus() {
    try {
        const data = await controlTest("status");
        statusElement.textContent =
            data.state + (data.exit_code === null
                ? ""
                : " (exit " + data.exit_code + ")");

        runButton.disabled = data.state === "Running";
        stopButton.disabled = data.state !== "Running";
    } catch (error) {
        statusElement.textContent = error.message;
    }
}

runButton.addEventListener("click", async () => {
    if (!validConfiguration(state[profile])) {
        errorElement.textContent = "Neplatná konfigurace.";
        return;
    }

    try {
        const data = await controlTest("run", {
            profile: profile,
            settings: state[profile]
        });
        statusElement.textContent = data.state;
        await refreshStatus();
    } catch (error) {
        statusElement.textContent = "FAIL: " + error.message;
    }
});



githubRunButton.addEventListener("click", async () => {
    if (!validConfiguration(state[profile]) || githubDispatching || githubRequestId) {
        if (!validConfiguration(state[profile])) {
            errorElement.textContent = "Neplatná konfigurace.";
        }
        return;
    }

    githubDispatching = true;
    githubRunButton.disabled = true;
    githubStatusElement.textContent = "GitHub: Dispatching";
    githubLinkElement.replaceChildren();

    try {
        const data = await controlTest("github/run", {
            profile: profile,
            settings: state[profile]
        });
        githubRequestId = data.request_id;
        githubStatusElement.textContent =
            `GitHub: ${data.state} (${data.profile})`;
        await refreshGithubStatus();
    } catch (error) {
        githubStatusElement.textContent = "GitHub FAIL: " + error.message;
    } finally {
        githubDispatching = false;
        githubRunButton.disabled = Boolean(githubRequestId);
    }
});

stopButton.addEventListener("click", async () => {
    try {
        await controlTest("stop");
        await refreshStatus();
    } catch (error) {
        statusElement.textContent = "FAIL: " + error.message;
    }
});

setInterval(refreshStatus, 1000);

function render() {
    configureTabs();
    controlsElement.innerHTML = "";

    const config = state[profile];

    for (const [key, value] of Object.entries(config)) {
        addControl(key, value);
    }

    updateChart();
}

render();
refreshStatus();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Render the local interactive performance configurator."""
    return PAGE


class RunRequest(BaseModel):
    """Validated local performance test request."""

    profile: str
    settings: dict[str, float]


RUNNER_OPTIONS = {
    "hold": {
        "rpm": "--rpm",
        "duration": "--duration",
        "tolerance": "--tolerance-pct",
    },
    "bell": {
        "rpm": "--rpm",
        "up": "--ramp-up",
        "peak": "--peak",
        "down": "--ramp-down",
        "tolerance": "--tolerance-pct",
    },
    "hold-bell": {
        "baseline": "--baseline-rpm",
        "rpm": "--rpm",
        "up": "--ramp-up",
        "peak": "--peak",
        "down": "--ramp-down",
        "tolerance": "--tolerance-pct",
    },
    "recovery": {
        "baseline": "--baseline-rpm",
        "rpm": "--rpm",
        "duration": "--baseline",
        "peak": "--spike",
        "recovery": "--recovery",
        "tolerance": "--tolerance-pct",
    },
}

ROOT = Path(__file__).resolve().parents[2]
PROCESS: subprocess.Popen | None = None
LOG_FILE = None


def localhost_only(request: Request) -> None:
    """Reject remote clients and cross-origin browser requests."""
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Localhost only")

    origin = request.headers.get("origin")
    if origin and origin != "http://127.0.0.1:8501":
        raise HTTPException(403, "Invalid origin")


def make_command(data: RunRequest) -> list[str]:
    """Convert allowed profile settings to a safe argument list."""
    options = RUNNER_OPTIONS.get(data.profile)

    if options is None or set(data.settings) != set(options):
        raise HTTPException(422, "Invalid profile settings")

    values = data.settings
    whole_seconds = {"duration", "up", "peak", "down", "recovery"}

    for key, value in values.items():
        if not isinstance(value, (int, float)):
            raise HTTPException(422, "Invalid numeric value")
        if key in whole_seconds and not float(value).is_integer():
            raise HTTPException(422, "Phase durations must be integers")

    profile = Profile(data.profile)
    config = LoadConfig(
        profile=profile,
        target_rpm=values["rpm"],
        baseline_rpm=values.get("baseline", 60),
        duration_seconds=int(values.get("duration", 60)),
        ramp_up_seconds=int(values.get("up", 30)),
        peak_seconds=int(values.get("peak", 30)),
        ramp_down_seconds=int(values.get("down", 30)),
        recovery_seconds=int(values.get("recovery", 60)),
        tolerance_pct=values["tolerance"],
    )

    try:
        config.validate()
        if profile in {Profile.HOLD_BELL, Profile.RECOVERY}:
            if config.target_rpm <= config.baseline_rpm:
                raise ValueError("Target must exceed baseline")
        if profile == Profile.RECOVERY and not 10 <= config.duration_seconds <= 3600:
            raise ValueError("Baseline duration must be 10..3600")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    command = [
        sys.executable,
        str(ROOT / "performance/locust/run.py"),
        data.profile,
    ]

    for key, option in options.items():
        value = values[key]
        text = str(int(value)) if key in whole_seconds else str(value)
        command.extend([option, text])

    return command


@app.post("/api/run")
def start_test(data: RunRequest, request: Request) -> dict:
    """Start the configured Locust test as a local process."""
    global PROCESS, LOG_FILE

    localhost_only(request)

    if PROCESS is not None and PROCESS.poll() is None:
        raise HTTPException(409, "Test already running")

    command = make_command(data)

    reports = ROOT / "performance/reports"
    reports.mkdir(parents=True, exist_ok=True)

    LOG_FILE = (reports / "ui_run.log").open("w")

    try:
        PROCESS = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=LOG_FILE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        LOG_FILE.close()
        raise HTTPException(500, str(exc)) from exc

    LOG_FILE.close()

    return {"state": "Running", "pid": PROCESS.pid}


@app.post("/api/stop")
def stop_test(request: Request) -> dict:
    """Stop the currently running test process group."""
    localhost_only(request)

    if PROCESS is None or PROCESS.poll() is not None:
        raise HTTPException(409, "No test running")

    os.killpg(PROCESS.pid, signal.SIGTERM)
    return {"state": "Stopping"}


@app.get("/api/status")
def test_status(request: Request) -> dict:
    """Return the active or completed test status."""
    localhost_only(request)

    if PROCESS is None:
        return {"state": "Idle", "exit_code": None}

    code = PROCESS.poll()

    if code is None:
        return {"state": "Running", "exit_code": None}

    return {
        "state": "PASS" if code == 0 else "FAIL",
        "exit_code": code,
    }


@app.post("/api/github/run")
def start_github_test(data: RunRequest, request: Request) -> dict:
    """Dispatch a validated Locust profile to GitHub Actions."""
    import uuid

    localhost_only(request)
    make_command(data)

    settings = data.settings

    duration = (
        settings["duration"]
        if data.profile == "hold"
        else (
            settings["duration"] + settings["peak"] + settings["recovery"]
            if data.profile == "recovery"
            else settings["up"] + settings["peak"] + settings["down"]
        )
    )

    if duration > 300:
        raise HTTPException(422, "GitHub test maximum is 300 seconds")

    if data.profile == "recovery" and (
        settings["duration"] < 10 or settings["recovery"] < 10
    ):
        raise HTTPException(422, "Recovery phases require at least 10 seconds")

    if data.profile == "hold" and duration < 10:
        raise HTTPException(422, "Hold requires at least 10 seconds")

    request_id = uuid.uuid4().hex

    mapping = {
        "rpm": "rpm",
        "baseline": "baseline_rpm",
        "duration": "duration",
        "up": "ramp_up",
        "peak": "peak",
        "down": "ramp_down",
        "recovery": "recovery",
        "tolerance": "tolerance_pct",
    }

    command = [
        "gh", "workflow", "run", "performance-locust.yml",
        "--repo", "Necraatall/secure-backend-platform",
        "--ref", "main",
        "-f", f"profile={data.profile}",
        "-f", f"request_id={request_id}",
    ]

    integer_fields = {"duration", "up", "peak", "down", "recovery"}

    for key, value in settings.items():
        formatted = str(int(value)) if key in integer_fields else str(value)
        command.extend(["-f", f"{mapping[key]}={formatted}"])

    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(502, "GitHub dispatch unavailable") from exc

    if result.returncode != 0:
        raise HTTPException(
            502,
            f"GitHub dispatch failed: {result.stderr.strip()[:500]}",
        )

    return {
        "state": "Dispatched",
        "profile": data.profile,
        "request_id": request_id,
    }


@app.get("/api/github/status")
def github_test_status(request_id: str, request: Request) -> dict:
    """Find the GitHub Actions run belonging to a UI request."""
    import json
    import re

    localhost_only(request)

    if re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
        raise HTTPException(422, "Invalid request ID")

    endpoint = (
        "repos/Necraatall/secure-backend-platform/"
        "actions/runs?per_page=100"
    )

    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(502, "GitHub API unavailable") from exc

    if result.returncode != 0:
        raise HTTPException(502, "GitHub API request failed")

    try:
        runs = json.loads(result.stdout)["workflow_runs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(502, "Invalid GitHub API response") from exc

    for run in runs:
        title = run.get("display_title", "")
        if not title.endswith(f" {request_id}"):
            continue

        if run.get("path") != ".github/workflows/performance-locust.yml":
            continue

        run_id = run["id"]

        return {
            "state": run["status"],
            "conclusion": run.get("conclusion"),
            "run_id": run_id,
            "url": (
                "https://github.com/Necraatall/"
                f"secure-backend-platform/actions/runs/{run_id}"
            ),
        }

    return {
        "state": "pending_discovery",
        "conclusion": None,
        "run_id": None,
        "url": None,
    }
