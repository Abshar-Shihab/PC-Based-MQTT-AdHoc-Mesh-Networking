import paho.mqtt.client as mqtt
import threading
import time

# Configuration
PC2_IP = '172.16.2.112' #my ip
PC1_IP = '172.16.2.149' #PC_S ip address
TOPIC = 'test_topic'
FORWARD_TOPIC = 'forwarded_test_topic'

# Callback when a message is received
def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic {msg.topic}")
    if msg.topic == TOPIC:
        # Forward message to pc1
        forwarder.publish(FORWARD_TOPIC, msg.payload)

# Function to send messages
def send_messages():
    while True:
        message = input("Enter message to send from pc2: ")
        if message.lower() == 'exit':
            break
        client.publish(TOPIC, message)
        forwarder.publish(FORWARD_TOPIC, message)

# Set up the MQTT client for pc2
client = mqtt.Client()
client.on_message = on_message

# Connect to pc2 (itself) and subscribe to the topic
client.connect(PC2_IP, 1883, 60)
client.subscribe(TOPIC)

# Create another client to forward messages to pc1
forwarder = mqtt.Client()
forwarder.connect(PC1_IP, 1883, 60)

# Start the loop to process incoming messages
client.loop_start()

# Start a separate thread to handle sending messages
sender_thread = threading.Thread(target=send_messages)
sender_thread.start()

# Keep the script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
    forwarder.disconnect()
    sender_thread.join()
