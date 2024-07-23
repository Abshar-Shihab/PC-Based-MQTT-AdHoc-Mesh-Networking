import paho.mqtt.client as mqtt
import threading
import time

# Configuration
BROKER_IP = ''  # Local broker IP (MY PC IP)
TOPIC_D = 'D'
TOPIC_S = 'S'
TOPIC_N = 'N'
TOPIC_K = 'A'


# Callback when a message is received
def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic {msg.topic}")
    for topic in [TOPIC_N,TOPIC_S]:
            client.publish(topic, msg.payload.decode())
            #print(f"Sent message to {topic}")

# Function to send messages
def send_messages():
    while True:
        message = input("Enter message to send: ")
        if message.lower() == 'exit':
            break

        for topic in [TOPIC_N, TOPIC_S]:
            client.publish(topic,"Danyal: "+ message)
            #print(f"Sent message to {topic}")


# Set up the MQTT client
client = mqtt.Client()
client.on_message = on_message

# Connect to the local MQTT broker
client.connect(BROKER_IP, 1883, 60)

# Subscribe to relevant topics with QoS level 0 (modify as needed)
client.subscribe((TOPIC_D, 2))

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
