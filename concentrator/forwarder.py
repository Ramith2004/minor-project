# concentrator/forwarder.py
import json
import paho.mqtt.client as mqtt
import requests

BROKER = "localhost"
TOPIC = "grid/readings"
BACKEND_URL = "http://127.0.0.1:5000/submitReading"

def on_connect(client, userdata, flags, rc):
    print("Connected to broker with code:", rc)
    client.subscribe(TOPIC)
    print("Subscribed to topic:", TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print("Received reading:", payload)

        # Send to backend
        res = requests.post(BACKEND_URL, json=payload)
        print("Forwarded to backend:", res.status_code)

    except Exception as e:
        print("Error processing message:", e)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, 1883, 60)
client.loop_forever()
