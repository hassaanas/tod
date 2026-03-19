#!/usr/bin/env python3
# Author : Hassaan Siddiqui
# IoT Case study - ToD Application
# speed-rds-timestamp.py
# For timestamp experiments

######### Usage ######
# ./script_name ms_name

import sys, datetime, time, json, random, os
import paho.mqtt.client as mqtt

dt=datetime.datetime.now()
print("\n-----------------------------------------")
print("Starting script pub-timestamp.py at ",dt)
print("-----------------------------------------\n")
#broker_address = "10.152.183.84"
broker_address = os.environ.get('BROKERIP') #--- env variable
port = int(os.environ.get('BROKERPORT')) #--- env variable
#port = 1883
ms=sys.argv[1]
pub_topic = 'set/'+ms
sub_topic = 'get/'+ms
print("pub_topic = ",pub_topic)
print("sub_topic = ",sub_topic)
#speed_array = ["10","20","50","100","0","10","0"]

def on_connect(client, userdata, flags, rc):
    if rc==0:
        print("Connection successful.\n")
    else:
        print("Connection failed with return code = ",rc)

def on_message(client, userdata, message):
    current_speed = str(message.payload.decode("utf-8"))
    #print("Response received.\nChanging speed to" ,current_speed,"km/h\n-------------------\n")
    #client.publish(pub_topic, speed)
    #print("message topic=",message.topic)
    #print("message qos=",message.qos)
    #print("message retain flag=",message.retain,'\n')

def on_disconnect(client, userdata, rc):
    print("Client Got Disconnected. RC = ",rc)
    if rc != 0:
        print('Unexpected broker disconnection. Will auto-reconnect')
        time.sleep(2.3)
        client.connect(broker_address,port)
    else:
        print('rc value:' + str(rc))

client = mqtt.Client()
client.on_connect=on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

try:
        print("Connecting to Broker: ",broker_address," at port: ",port)
        client.connect(broker_address,port)
        time.sleep(0.3)
except:
        print("ERROR: Cannot connect to broker.")
else:
        client.loop_start()  #Start network connection daemon
        client.subscribe(sub_topic)
        print("Publishing timestamps at 100 msec interval to",pub_topic,"\n\n")
        while True:
            #timestamp = str(datetime.datetime.now())
            timestamp = time.time()
            client.publish(pub_topic,timestamp)
            time.sleep(0.1)
