console.log("Dashboard loaded");

const socket = new WebSocket("ws://localhost:3000");

// DOM references
const evIdEl = document.getElementById("ev-id");
const evPosEl = document.getElementById("ev-pos");
const evTimeEl = document.getElementById("ev-time");
const evLaneEl = document.getElementById("ev-lane");
const evEdgeEl = document.getElementById("ev-edge");
const evRsuEl = document.getElementById("ev-rsu");
const logEl = document.getElementById("status-log");

// Canvas
const canvas = document.getElementById("network-map");
const ctx = canvas.getContext("2d");

// Network data loaded from /network
let network = null;
let lastEV = null;
let evTrail = [];          // store EV positions
const MAX_TRAIL_LENGTH = 200;

// ---- Fetch network geometry once at load ----
fetch("/network")
    .then(res => res.json())
    .then(data => {
        network = data;
        drawMap();      // draw base map once (no EV yet)
    })
    .catch(err => {
        console.error("Failed to load network:", err);
    });

socket.onopen = () => console.log("[WS] connected");

socket.onmessage = (msg) => {
    const packet = JSON.parse(msg.data);
    if (packet.type === "ev_update") {
        lastEV = packet.data;

        // Save EV location to trail
        evTrail.push([lastEV.location[0], lastEV.location[1]]);

        // Limit history size
        if (evTrail.length > MAX_TRAIL_LENGTH) {
            evTrail.shift();
        }

        updateEVInfo(lastEV);
        addLog(lastEV);
        drawMap();
    }
};

function updateEVInfo(ev) {
    evIdEl.textContent = ev.ev_id || ev.evId || "ev_0";
    evPosEl.textContent = `(${ev.location[0].toFixed(2)}, ${ev.location[1].toFixed(2)})`;
    evTimeEl.textContent = ev.time.toFixed(2);
    evLaneEl.textContent = ev.lane || "-";
    evEdgeEl.textContent = ev.edge || "-";
    evRsuEl.textContent = ev.rsu || "-";
}

function addLog(ev) {
    const div = document.createElement("div");
    div.textContent =
        `t=${ev.time.toFixed(1)}s | EV at (${ev.location[0].toFixed(1)},` +
        `${ev.location[1].toFixed(1)}) lane=${ev.lane || "-"} rsu=${ev.rsu || "-"}`;
    logEl.prepend(div);
}

// ---- Coordinate transform: world (SUMO) -> canvas ----
function worldToScreen(x, y) {
    if (!network) return { x: 0, y: 0 };

    const { minX, maxX, minY, maxY } = network.bounds;

    const nx = (x - minX) / (maxX - minX || 1);
    const ny = (y - minY) / (maxY - minY || 1);

    const sx = nx * canvas.width;
    const sy = canvas.height - ny * canvas.height; // flip Y

    return { x: sx, y: sy };
}

// ---- Draw everything: lanes, TLs, RSUs, EV ----
function drawMap() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!network) {
        ctx.fillStyle = "#888";
        ctx.fillText("Loading network...", 20, 20);
        return;
    }

    // 1) Lanes (roads)
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#555";

    network.lanes.forEach(lane => {
        if (!lane.points || lane.points.length < 2) return;
        const first = worldToScreen(lane.points[0][0], lane.points[0][1]);
        ctx.beginPath();
        ctx.moveTo(first.x, first.y);

        for (let i = 1; i < lane.points.length; i++) {
            const p = worldToScreen(lane.points[i][0], lane.points[i][1]);
            ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
    });

    // 2) Traffic lights
    network.tls.forEach(tl => {
        const p = worldToScreen(tl.x, tl.y);
        ctx.fillStyle = "lime";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "#fff";
        ctx.font = "10px Arial";
        ctx.fillText(tl.id, p.x + 6, p.y - 6);
    });

    // 3) RSUs (blue)
    network.rsus.forEach(rsu => {
        const p = worldToScreen(rsu.x, rsu.y);
        ctx.fillStyle = "deepskyblue";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
    });

    // 4) Draw EV Trail History
    if (evTrail.length > 1) {
        ctx.lineWidth = 3;

        for (let i = 1; i < evTrail.length; i++) {
            const [x1, y1] = evTrail[i - 1];
            const [x2, y2] = evTrail[i];

            const p1 = worldToScreen(x1, y1);
            const p2 = worldToScreen(x2, y2);

            // Fade effect: older points are dimmer
            const alpha = i / evTrail.length;  // 0 → old … 1 → fresh
            ctx.strokeStyle = `rgba(255, 50, 50, ${alpha})`;

            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
        }
    }

    // 5) EV marker
    if (lastEV) {
        const p = worldToScreen(lastEV.location[0], lastEV.location[1]);
        ctx.fillStyle = "red";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
        ctx.fill();
    }
}
