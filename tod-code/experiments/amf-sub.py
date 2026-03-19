#!/usr/bin/env python3
import os
import sys
import paho.mqtt.client as mqtt
from datetime import datetime

# --- Configuration ---
LOG_FILE = "mqtt_log.txt"
BROKER = os.environ.get('BROKERIP', '127.0.0.1')
PORT = int(os.environ.get('BROKERPORT', 1883))

if len(sys.argv) < 2:
    print("Usage: ./amf-sub.py <topic_suffix>")
    sys.exit(1)

TOPIC = f"set/{sys.argv[1]}"

def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    log_entry = f"[{timestamp}] Topic: {message.topic} | Payload: {payload}\n"
    
    # Append to file
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)
    
    # Also print to console so you can see it working
    print(log_entry.strip())

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected! Logging {TOPIC} to {LOG_FILE}...")
        client.subscribe(TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

# --- Main ---
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(BROKER, PORT)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nStopping logger...")
    client.disconnect()
