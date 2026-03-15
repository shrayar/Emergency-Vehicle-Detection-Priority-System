const express = require("express");
const http = require("http");
const WebSocket = require("ws");
const path = require("path");
const fs = require("fs");
const xml2js = require("xml2js");

const app = express();
app.use(express.json());

// serve static dashboard
app.use(express.static(path.join(__dirname, "public")));

const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

let lastEVStatus = null;
let cachedNetwork = null;

// ---------- EV UPDATE FROM TRACI ----------
app.post("/update", (req, res) => {
    lastEVStatus = req.body;

    wss.clients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                type: "ev_update",
                data: lastEVStatus
            }));
        }
    });

    res.status(200).json({ message: "OK" });
});

// ---------- NETWORK GEOMETRY FROM route.net.xml ----------
app.get("/network", (req, res) => {
    if (cachedNetwork) {
        return res.json(cachedNetwork);
    }

    const netPath = path.join(__dirname, "..", "sumo_new", "route.net.xml");

    fs.readFile(netPath, "utf8", (err, xmlData) => {
        if (err) {
            console.error("Error reading net file:", err);
            return res.status(500).json({ error: "Could not read net file" });
        }

        xml2js.parseString(xmlData, (err, json) => {
            if (err) {
                console.error("Error parsing net file:", err);
                return res.status(500).json({ error: "Could not parse net file" });
            }

            try {
                const net = json.net;
                const lanes = [];
                let minX = Infinity, maxX = -Infinity;
                let minY = Infinity, maxY = -Infinity;

                // 1) Lanes (polylines)
                const edges = net.edge || [];
                edges.forEach(edge => {
                    const attrs = edge.$ || {};
                    if (attrs.function === "internal") return; // skip internal edges

                    (edge.lane || []).forEach(lane => {
                        const lAttrs = lane.$ || {};
                        if (!lAttrs.shape) return;

                        const points = lAttrs.shape.split(" ").map(p => {
                            const [xs, ys] = p.split(",");
                            const x = parseFloat(xs);
                            const y = parseFloat(ys);

                            if (!Number.isNaN(x) && !Number.isNaN(y)) {
                                minX = Math.min(minX, x);
                                maxX = Math.max(maxX, x);
                                minY = Math.min(minY, y);
                                maxY = Math.max(maxY, y);
                            }

                            return [x, y];
                        });

                        lanes.push({
                            id: lAttrs.id,
                            points
                        });
                    });
                });

                // 2) Traffic light junctions (J1..J7)
                const TL_IDS = ["J1", "J4", "J5", "J6", "J7"];
                const tls = [];
                const rsus = [];

                const junctions = net.junction || [];
                junctions.forEach(j => {
                    const a = j.$ || {};
                    if (!TL_IDS.includes(a.id)) return;

                    const x = parseFloat(a.x);
                    const y = parseFloat(a.y);

                    tls.push({ id: a.id, x, y });
                    rsus.push({ id: "RSU_" + a.id, x, y });
                });

                const bounds = { minX, maxX, minY, maxY };
                cachedNetwork = { lanes, tls, rsus, bounds };
                res.json(cachedNetwork);
            } catch (e) {
                console.error("Error building network JSON:", e);
                res.status(500).json({ error: "Failed to build network" });
            }
        });
    });
});

// ---------- DASHBOARD WS ----------
wss.on("connection", ws => {
    console.log("[WS] Dashboard connected");
    if (lastEVStatus) {
        ws.send(JSON.stringify({
            type: "ev_update",
            data: lastEVStatus
        }));
    }
});

const PORT = 3000;
server.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});
