#!/usr/bin/env python3
# Author : Hassaan Siddiqui
# IoT Case study - ToD Application
# Timestamp difference calculator

########### Usage ###############
# ./script_name ms_name
################################

import sys, time, json, random, os, datetime
import paho.mqtt.client as mqtt


broker_address = os.environ.get('BROKERIP') #--- env variable
#port = 1883
port = int(os.environ.get('BROKERPORT')) #--- env variable
ms = sys.argv[1]
pub_topic = 'set/'+ms
sub_topic = 'set/'+ms
print("pub_topic = ", pub_topic)
print("sub_topic = ", sub_topic)
speed = "0"
t0 = 1.01

def on_connect(client, userdata, flags, rc):
    if rc==0:
        print("Connection successful.\n")
        #client.publish(pub_topic, "Subscriber successfully connected to broker.")
        client.subscribe(sub_topic)
    else:
        print("Connection failed with return code = ",rc)

def on_message(client, userdata, message):
    t1 = float(message.payload.decode("utf-8"))
    global t0
    dt = round((t1 - t0) * 1000)
    t0 = t1
    #time=datetime.datetime.now()
    #print(dt)
    print("Message sent time = ", t1)
    #print(t1)
    print("Message received time = ", t0)
    print(dt)
    if dt > 110:
        ts = datetime.datetime.now()
        print(ts,": Time difference between received messages = ", dt, "msec")
        #print(dt)
        #print(time)
        #print("---------------------------------\n")
    #client.publish(pub_topic, speed)
    #print("message topic=",message.topic)
    #print("message qos=",message.qos)
    #print("message retain flag=",message.retain,'\n')

#client = mqtt.Client(client_id=userID, clean_session=True, userdata=None, protocol=mqtt.MQTTv311, transport="tcp")
client = mqtt.Client()
client.on_connect=on_connect
client.on_message = on_message
#client.tls_set()
#client.username_pw_set(userName, password=password)

try:
        print("Connecting to Broker: ",broker_address," at port: ",port)
        client.connect(broker_address,port)
        time.sleep(1)
except:
        print("ERROR: Cannot connect to broker.")
else:
        client.loop_start()  #Start network connection daemon
        client.subscribe(sub_topic)
        while True:
            time.sleep(1)
        #time.sleep(400)
        #client.disconnect()
