import paho.mqtt.client as mqtt

# Configuration
PC1_IP = '172.16.2.97' #my_ip
TOPIC = 'test_topic'

# Callback when a message is received
def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic {msg.topic}")

# Set up the MQTT client for pc1
client = mqtt.Client()
client.on_message = on_message

# Connect to pc1 (the broker)
client.connect(PC1_IP, 1883, 60)

# Subscribe to the topic
client.subscribe(TOPIC)

# Start the loop to process incoming messages
client.loop_start()

# Keep the script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
