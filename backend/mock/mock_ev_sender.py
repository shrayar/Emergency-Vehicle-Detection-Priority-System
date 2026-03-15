# mock_ev_sender.py - sends EV_PRIORITY_REQ to RSU server for testing
import time, sys, json, requests, random
import socketio

SERVER_HTTP = "http://localhost:3000"
SOCKET_IO = "http://localhost:3000"

# sample EV message generator
def gen_ev(ev_id="EV_1", eta=20.0):
    return {
        "type": "EV_PRIORITY_REQ",
        "ev_id": ev_id,
        "timestamp": time.time(),
        "position": {"lat": 34.0 + random.random()*0.01, "lon": -118.2 + random.random()*0.01},
        "current_edge": "edgeX",
        "next_tls": "tls_1",
        "eta_seconds": eta,
        "speed": 12.5,
        "urgency": "CODE3"
    }

def send_http(msg, server=SERVER_HTTP):
    url = server + "/api/ev_priority"
    r = requests.post(url, json=msg)
    print("HTTP send => status:", r.status_code, "response:", r.json())

def send_socketio(msg, server=SOCKET_IO):
    sio = socketio.Client()
    sio.connect(server)
    print("Socket connected:", sio.sid)
    sio.emit('ev_priority', msg)
    # receive response event if server emits back; add handlers if you want
    time.sleep(1)
    sio.disconnect()

if __name__ == "__main__":
    # Usage: python mock_ev_sender.py [http|socket] [eta_seconds]
    method = sys.argv[1] if len(sys.argv) > 1 else "http"
    eta = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0

    msg = gen_ev(eta=eta)
    print("Sending EV message:", json.dumps(msg, indent=2))
    if method == "http":
        send_http(msg)
    else:
        send_socketio(msg)
