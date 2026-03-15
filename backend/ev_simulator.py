# ev_simulator.py
import socketio
import time
import random

sio = socketio.Client()

@sio.event
def connect():
    print("Connected to RSU")

@sio.event
def disconnect():
    print("Disconnected from RSU")

@sio.event
def rsu_response(data):
    print("RSU Response:", data)

def simulate_ev():
    while True:
        eta = random.randint(10, 45)
        message = {
            "ev_id": "EV_1",
            "eta": eta,
            "position": {"lat": 34.00477, "lon": -118.19741},
            "next_tls": "tls_1"
        }
        print("Sending:", message)
        sio.emit("ev_priority", message)
        time.sleep(5)

if __name__ == "__main__":
    sio.connect("http://localhost:3000")
    simulate_ev()
