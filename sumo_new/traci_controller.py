import os, sys
# 1) MAKE SURE THIS PATH IS EXACT
sys.path.append(r"D:\Program Files (x86)\sumo\sumo-1.24.0\tools")

import traci
import traci.constants as tc
import math
import requests
import time

SUMO_CMD = [
    "sumo-gui",
    "-c", "sumo.sumocfg",
    "--start"
]

BACKEND_URL = "http://localhost:3000/update"

EMERGENCY_VEHICLE_TYPE = "emergency"   # from car3.rou.xml
TRAFFIC_LIGHTS = ["J1", "J4", "J5", "J6", "J7"]

# RSUs mapped to junctions (one per TL)
RSUS = {
    "RSU_J1": "J1",
    "RSU_J4": "J4",
    "RSU_J5": "J5",
    "RSU_J6": "J6",
    "RSU_J7": "J7",
}

last_highlighted_lane = None


def get_emergency_vehicles():
    """Return list of IDs of vehicles whose type is 'emergency'."""
    evs = []
    for vid in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(vid) == EMERGENCY_VEHICLE_TYPE:
            evs.append(vid)
    return evs


def follow_ev_camera(ev_id):
    """Center camera on EV."""
    try:
        traci.gui.trackVehicle("View #0", ev_id)
    except Exception as e:
        print("[CAM] track error:", e)


def smooth_zoom(ev_id):
    """Zoom based on EV speed (no rotation)."""
    try:
        speed = traci.vehicle.getSpeed(ev_id)
        if speed < 5:
            zoom = 400
        elif speed < 10:
            zoom = 600
        else:
            zoom = 900
        traci.gui.setZoom("View #0", zoom)
    except Exception:
        pass


def highlight_ev_lane(ev_id):
    try:
        # set EV color to bright red (lane highlight optional)
        traci.vehicle.setColor(ev_id, (255, 0, 0, 255))
    except Exception as e:
        print("[LANE] color error:", e)


def clear_lane_for_ev(ev_id):
    """Slow down other vehicles on same edge as EV."""
    try:
        ev_edge = traci.vehicle.getRoadID(ev_id)
        vehicles = traci.vehicle.getIDList()

        for vid in vehicles:
            if vid == ev_id:
                continue
            if traci.vehicle.getRoadID(vid) == ev_edge:
                traci.vehicle.slowDown(vid, 2.0, 5)
    except Exception as e:
        print("[CLEAR] error:", e)


def adjust_tls_for_emergency():
    """
    For each TL, if an emergency vehicle is on a controlled lane,
    give that lane green and others red.
    """
    for tl_id in TRAFFIC_LIGHTS:
        try:
            controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
            controlled_links = traci.trafficlight.getControlledLinks(tl_id)
            if not controlled_lanes or not controlled_links:
                continue

            emergency_lane = None
            for lane_id in controlled_lanes:
                if lane_id.startswith(":"):
                    continue
                vehs = traci.lane.getLastStepVehicleIDs(lane_id)
                for vid in vehs:
                    if traci.vehicle.getTypeID(vid) == EMERGENCY_VEHICLE_TYPE:
                        emergency_lane = lane_id
                        break
                if emergency_lane:
                    break

            if not emergency_lane:
                continue

            state_list = list(traci.trafficlight.getRedYellowGreenState(tl_id))

            for i, links in enumerate(controlled_links):
                incoming_lane = links[0][0] if links and links[0] else None
                if incoming_lane == emergency_lane:
                    state_list[i] = 'G'
                else:
                    state_list[i] = 'r'

            new_state = ''.join(state_list)
            traci.trafficlight.setRedYellowGreenState(tl_id, new_state)
            print(f"[TL] {tl_id}: EV on {emergency_lane}, state -> {new_state}")
        except Exception as e:
            print("[TL] error:", e)


def get_active_rsu_for_ev(ev_id):
    """Return ID of closest RSU to EV based on junction positions."""
    try:
        ex, ey = traci.vehicle.getPosition(ev_id)
        best_rsu = None
        best_dist = float("inf")
        for rsu_id, junc_id in RSUS.items():
            jx, jy = traci.junction.getPosition(junc_id)
            d = math.hypot(ex - jx, ey - jy)
            if d < best_dist:
                best_dist = d
                best_rsu = rsu_id
        return best_rsu
    except Exception:
        return None


def draw_rsu_markers():
    """Draw RSUs as blue POIs at each TL."""
    try:
        for rsu_id, junc_id in RSUS.items():
            x, y = traci.junction.getPosition(junc_id)
            poi_id = f"POI_{rsu_id}"
            traci.poi.add(poi_id, x, y, (0, 0, 255, 255))
    except Exception as e:
        print("[RSU] marker error:", e)


def send_backend_update(ev_id, rsu_id):
    """Send EV+RSU state to backend for dashboard."""
    try:
        pos = traci.vehicle.getPosition(ev_id)
        lane_id = traci.vehicle.getLaneID(ev_id)
        edge_id = traci.vehicle.getRoadID(ev_id)
        sim_time = traci.simulation.getTime()

        data = {
            "ev_id": ev_id,
            "location": pos,
            "time": sim_time,
            "lane": lane_id,
            "edge": edge_id,
            "rsu": rsu_id
        }
        requests.post(BACKEND_URL, json=data, timeout=0.2)
    except Exception:
        pass


def main():
    traci.start(SUMO_CMD)
    print("[SIM] SUMO started")

    draw_rsu_markers()

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        time.sleep(0.02)  
        emergency_vehicles = get_emergency_vehicles()

        if emergency_vehicles:
            for ev_id in emergency_vehicles:
                follow_ev_camera(ev_id)
                smooth_zoom(ev_id)
                highlight_ev_lane(ev_id)
                clear_lane_for_ev(ev_id)

                rsu_id = get_active_rsu_for_ev(ev_id)
                send_backend_update(ev_id, rsu_id)

            adjust_tls_for_emergency()

    traci.close()
    print("[SIM] End")


if __name__ == "__main__":
    main()