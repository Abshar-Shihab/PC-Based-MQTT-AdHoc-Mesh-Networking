import paho.mqtt.client as mqtt
import threading
import time

# Configuration
BROKER_IP = '172.16.2.97'  # Local broker IP(my ip)
TOPIC_D = 'D'
TOPIC_S = 'S'
TOPIC_N = 'N'
TOPIC_K = 'A'

# Static Routing Table (Define the shortest routes)
routing_table = {

    TOPIC_S: TOPIC_N, # who i am connected to


    # Add other entries as needed
}


# Callback when a message is received
def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic {msg.topic}")
    forward_topic = routing_table.get(msg.topic)
    if forward_topic:
        client.publish(forward_topic, "soban: " + msg.payload.decode())


# Function to send messages
def send_messages():
    while True:
        message = input("Enter message to send: ")
        if message.lower() == 'exit':
            break

        for topic in [TOPIC_S]:
            client.publish(topic, message)


# Set up the MQTT client
client = mqtt.Client()
client.on_message = on_message

# Connect to the local MQTT broker
client.connect(BROKER_IP, 1883, 60)

# Subscribe to relevant topics with QoS level 0 (modify as needed)
client.subscribe((TOPIC_S, 0))

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
    sender_thread.join()
    print("Disconnected from MQTT broker.")
