import os
import sys
import time
import csv
import random
from pathlib import Path
import socketio

# =========================
# --- SUMO Configuration ---
# =========================

SUMO_HOME = os.environ.get("SUMO_HOME")
if not SUMO_HOME:
    raise EnvironmentError(
        'SUMO_HOME not set. Example:\n'
        '  setx SUMO_HOME "C:\\Program Files (x86)\\Eclipse\\Sumo"\n'
        'Then open a NEW terminal.'
    )

TOOLS_DIR = os.path.join(SUMO_HOME, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.append(TOOLS_DIR)

import traci
import sumolib

SUMO_BINARY = "sumo-gui"  # use GUI for visualization
CFG = "config.sumocfg"
NET_FILE = "network.net.xml"
ROUTE_FILE = "routes.rou.xml"
OUTPUT_CSV = "ev_baseline.csv"

EV_ID = "EV_1"
EV_TYPE = "emergency"
EV_ROUTE = "route0"
EV_DEPART_TIME = 60.0
KEEP_ALIVE_BUFFER = 3600.0
MAX_SIM_TIME = 3 * 3600.0

# ===============================
# --- Helper Functions ---
# ===============================

def pick_far_edges(net):
    """Pick two far apart edges for emergency route."""
    edges = [e for e in net.getEdges() if e.getSpeed() > 0]
    if len(edges) < 2:
        raise RuntimeError("Not enough usable edges in network.")
    a, b = random.sample(edges, 2)
    return a.getID(), b.getID()

def choose_base_vtype():
    """Pick an existing vehicle type from loaded simulation."""
    vtypes = traci.vehicletype.getIDList()
    if vtypes:
        return vtypes[0]
    return "DEFAULT_VEHTYPE"

# ==================================
# --- Main SUMO + RSU Integration ---
# ==================================

def main():
    print("🚦 Starting SUMO simulation...")
    if traci.isLoaded():
        traci.close()

    sumo_cmd = [SUMO_BINARY, "-c", CFG, "--start"]
    traci.start(sumo_cmd)
    print("✅ Connected to SUMO simulation")

    # --- RSU (Node.js) SocketIO connection ---
    sio = socketio.Client()

    @sio.event
    def connect():
        print("✅ Connected to RSU server")

    @sio.event
    def disconnect():
        print("❌ Disconnected from RSU server")

    @sio.event
    def rsu_decision(data):
        print("📡 RSU Decision received:", data)
        tls_id = data.get("tls_id", "A1")
        action = data.get("action", "ack")

        if action.startswith("extend_green"):
            extra_time = 5 if "5s" in action else 10
            try:
                current_phase = traci.trafficlight.getPhase(tls_id)
                remaining = traci.trafficlight.getNextSwitch(tls_id) - traci.simulation.getTime()
                traci.trafficlight.setPhaseDuration(tls_id, remaining + extra_time)
                print(f"Extended green at {tls_id} by {extra_time}s")
            except Exception as e:
                print("Error applying RSU decision:", e)

    try:
        sio.connect("http://localhost:3000")
    except Exception as e:
        print("⚠️ Could not connect to RSU server:", e)

    # --- Main simulation loop ---
    ev_added = False
    ev_departed = False
    ev_depart_time = None
    ev_arrival_time = None
    net = sumolib.net.readNet(NET_FILE)
    src_edge_id, dst_edge_id = pick_far_edges(net)

    must_run_until = EV_DEPART_TIME + KEEP_ALIVE_BUFFER

    try:
        while True:
            traci.simulationStep()
            sim_time = traci.simulation.getTime()
            time.sleep(0.15)
            # Add EV only once
            if sim_time >= EV_DEPART_TIME and not ev_added:
                try:
                    if EV_ID not in traci.vehicle.getIDList():
                        traci.vehicle.add(EV_ID, EV_ROUTE, typeID=EV_TYPE)
                        traci.vehicle.setColor(EV_ID, (255, 0, 0))
                        traci.gui.trackVehicle("View #0", EV_ID)
                        traci.gui.setZoom("View #0", 300)
                        print(f"🚨 {EV_ID} added to SUMO simulation")
                        ev_added = True
                        ev_departed = True
                        ev_depart_time = sim_time
                        triggered_tls = set()
                except Exception as e:
                    print("Error adding EV:", e)

            # --- Emit RSU updates dynamically for multiple intersections ---
            if ev_departed and EV_ID in traci.vehicle.getIDList():
                try:
                    ev_pos = traci.vehicle.getPosition(EV_ID)
                    ev_edge = traci.vehicle.getRoadID(EV_ID)
                    ev_speed = traci.vehicle.getSpeed(EV_ID)

                    # Check each intersection in network
                    for tls_id in traci.trafficlight.getIDList():
                        lanes = traci.trafficlight.getControlledLanes(tls_id)
                        for lane in lanes:
                            edge_id = lane.split("_")[0]
                            if edge_id == ev_edge and tls_id not in triggered_tls:
                                print(f"📡 EV approaching RSU {tls_id}")

                                # Send live EV update to RSU server
                                sio.emit("ev_update", {
                                    "ev_id": EV_ID,
                                    "tls_id": tls_id,
                                    "position": {"x": ev_pos[0], "y": ev_pos[1]},
                                    "speed": ev_speed,
                                    "distance": 50,
                                    "eta_seconds": 10,
                                    "timestamp": time.strftime("%I:%M:%S %p")
                                })
                                print(f"✅ Sent EV update to RSU server: {tls_id}")

                                triggered_tls.add(tls_id)

                                # Optional: extend green light locally too
                                try:
                                    traci.trafficlight.setPhaseDuration(tls_id, 10)
                                    print(f"🟢 Extended green light for {tls_id}")
                                except Exception as e:
                                    print(f"⚠️ Failed to extend green for {tls_id}:", e)
                except Exception as e:
                    print("⚠️ Error while checking RSUs:", e)

                    # --- Stop simulation when EV arrives ---
            if ev_departed and EV_ID in traci.simulation.getArrivedIDList():
                ev_arrival_time = sim_time
                print(f"🏁 {EV_ID} arrived at destination in {sim_time:.2f}s")

    finally:
        traci.close(False)
        sio.disconnect()

        # --- Log EV travel data ---
        if ev_depart_time and ev_arrival_time:
            tt = ev_arrival_time - ev_depart_time
        else:
            tt = None

        with open(OUTPUT_CSV, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ev_id", "depart_time_s", "arrival_time_s", "travel_time_s", "src_edge", "dst_edge"])
            w.writerow([EV_ID, ev_depart_time, ev_arrival_time, tt, src_edge_id, dst_edge_id])

        print(f"[Baseline] Wrote EV travel time to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
