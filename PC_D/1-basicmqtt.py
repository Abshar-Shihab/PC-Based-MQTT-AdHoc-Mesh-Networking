import paho.mqtt.client as mqtt

# Configuration
PC2_IP = '' #PC_A ip addr
TOPIC = 'test_topic'
MESSAGE = 'Hi i am Danyal'

# Set up the MQTT client
client = mqtt.Client()
client.connect(PC2_IP, 1883, 60)

# Publish a message
client.publish(TOPIC, MESSAGE)

# Disconnect
client.disconnect()
