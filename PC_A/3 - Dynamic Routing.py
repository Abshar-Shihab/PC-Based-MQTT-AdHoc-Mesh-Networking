import paho.mqtt.client as mqtt
import threading
import time
import heapq
from collections import defaultdict

# Configuration
BROKER_IP = '172.16.2.100'  # Local broker IP
DISCOVERY_TOPIC = 'discovery'
NODE_NAME = 'K'  # Change this for each node ('D', 'S', 'N', 'K')
GATEWAY_NODE = 'D'  # Specify the gateway node here
NEIGHBORS = set()
latencies = defaultdict(dict)
MAX_CONNECTIONS = 2  # Maximum number of connections per node
connection_slots = defaultdict(lambda: MAX_CONNECTIONS)  # Track available connection slots for each node
accepted_connections = defaultdict(set)  # Track accepted connections for each node


# Periodically broadcast presence for neighbor discovery
def broadcast_presence():
    while True:
        # Broadcast presence without resetting connections
        if connection_slots[NODE_NAME] > 0:
            client.publish(DISCOVERY_TOPIC, NODE_NAME)
            print(f"Broadcasting presence: {NODE_NAME}")
        time.sleep(10)  # Broadcast every 10 seconds


# Function to broadcast a reset command to all nodes
def broadcast_reset():
    client.publish('reset', 'RESET_COMMAND')
    print("Broadcasting reset command to all nodes")


# Measure latency to a neighbor
def measure_latency(neighbor):
    start_time = time.time()
    client.publish(f"ping/{neighbor}", f"{NODE_NAME}:{start_time}")
    return start_time


def request_connection_acknowledgment(neighbor):
    client.publish(f"ack_request/{neighbor}", NODE_NAME)
    print(f"Requested acknowledgment from {neighbor}")


def handle_connection_acknowledgment(sender):
    if sender in NEIGHBORS:
        # Mutual acknowledgment, finalize connection
        accepted_connections[NODE_NAME].add(sender)
        accepted_connections[sender].add(NODE_NAME)
        print(f"Connection with {sender} is now finalized")
    else:
        print(f"Unexpected acknowledgment from {sender}")


# Callback when a message is received
def on_message(client, userdata, msg):
    global NEIGHBORS, latencies, connection_slots, accepted_connections
    topic_parts = msg.topic.split('/')

    if msg.topic == 'reset':
        print(f"Received reset command. Resetting connections...")
        reset_connections()
        return

    if topic_parts[0] == 'ping' and topic_parts[1] == NODE_NAME:
        client.publish(f"pong/{msg.payload.decode().split(':')[0]}",
                       f"{NODE_NAME}:{msg.payload.decode().split(':')[1]}")
        print(f"Responded to ping from {msg.payload.decode().split(':')[0]}")
    elif topic_parts[0] == 'pong' and topic_parts[1] == NODE_NAME:
        latency = time.time() - float(msg.payload.decode().split(":")[1])
        sender = msg.payload.decode().split(":")[0]
        latencies[NODE_NAME][sender] = latency
        latencies[sender][NODE_NAME] = latency
        print(f"Measured latency to {sender}: {latency:.4f} seconds")
    elif msg.topic == DISCOVERY_TOPIC and msg.payload.decode() != NODE_NAME:
        new_neighbor = msg.payload.decode()
        if len(NEIGHBORS) < MAX_CONNECTIONS and new_neighbor not in NEIGHBORS:
            if connection_slots[new_neighbor] > 0:
                NEIGHBORS.add(new_neighbor)
                connection_slots[new_neighbor] -= 1  # Decrease the connection slot count for the new neighbor
                connection_slots[NODE_NAME] -= 1  # Decrease the connection slot count for the current node
                accepted_connections[NODE_NAME].add(new_neighbor)  # Add to accepted connections
                accepted_connections[new_neighbor].add(NODE_NAME)  # Mutual connection
                print(f"Discovered neighbor: {new_neighbor}")
                # Measure latency with new neighbor
                measure_latency(new_neighbor)
            else:
                print(f"Neighbor {new_neighbor} has reached its connection limit.")
        else:
            print(f"Already connected to maximum neighbors or neighbor {new_neighbor} is already connected.")
    elif topic_parts[0] == 'disconnect' and topic_parts[1] == NODE_NAME:
        disconnected_node = msg.payload.decode()
        if disconnected_node in NEIGHBORS:
            NEIGHBORS.remove(disconnected_node)
            connection_slots[disconnected_node] += 1  # Restore connection slot for the disconnected node
            connection_slots[NODE_NAME] += 1  # Restore connection slot for the current node
            accepted_connections[disconnected_node].remove(NODE_NAME)  # Remove from accepted connections
            print(f"Disconnected from {disconnected_node}")
    elif topic_parts[0] == 'ack_request' and topic_parts[1] == NODE_NAME:
        handle_connection_acknowledgment(msg.payload.decode())
    elif msg.topic == 'disconnect/all':
        handle_gateway_disconnection(msg.payload.decode())
    else:
        payload = msg.payload.decode()
        if ':' in payload:
            sender, content = payload.split(':', 1)  # Split into sender and content
            if NODE_NAME == GATEWAY_NODE:
                print(f"Gateway received message from {sender}: {content}")
                # Reset connections after receiving a message
                reset_connections()
                # Broadcast reset command to other nodes
                broadcast_reset()
            else:
                print(f"Received message from {sender}: {content} on topic {msg.topic}")
                forward_message(client, sender, content)
        else:
            print(f"Received malformed message: {payload}")


# Function to forward messages based on the shortest path using Dijkstra's algorithm
def forward_message(client, sender, message):
    path = dijkstra(latencies, NODE_NAME, GATEWAY_NODE)
    if path and len(path) > 1:
        next_hop = path[1]
        client.publish(next_hop, f"{NODE_NAME}:{message}")
        print(f"Sent message to {next_hop} (part of path to {GATEWAY_NODE})")
    else:
        # Forward to the closest neighbor if no path to gateway is found
        closest_neighbor = find_closest_neighbor()
        if closest_neighbor:
            client.publish(closest_neighbor, f"{NODE_NAME}:{message}")
            print(f"Sent message to closest neighbor {closest_neighbor} as fallback")
        else:
            print(f"No path to gateway from {NODE_NAME} and no fallback neighbor found.")


def find_closest_neighbor():
    min_latency = float('inf')
    closest_neighbor = None
    for neighbor in NEIGHBORS:
        latency = latencies[NODE_NAME].get(neighbor, float('inf'))
        if latency < min_latency:
            min_latency = latency
            closest_neighbor = neighbor
    return closest_neighbor


# Function to calculate the shortest path using Dijkstra's algorithm based on latency
def dijkstra(graph, start, end):
    queue = [(0, start, [])]
    seen = set()
    while queue:
        (cost, node, path) = heapq.heappop(queue)
        if node in seen:
            continue
        path = path + [node]
        seen.add(node)
        if node == end:
            return path
        for next_node, weight in graph.get(node, {}).items():
            if next_node not in seen:
                heapq.heappush(queue, (cost + weight, next_node, path))
    return None


# Set up the MQTT client
client = mqtt.Client()
client.on_message = on_message

# Connect to the local MQTT broker
client.connect(BROKER_IP, 1883, 60)

# Subscribe to discovery, latency, and node-specific topics
client.subscribe((DISCOVERY_TOPIC, 0))
client.subscribe((f"ping/{NODE_NAME}", 0))
client.subscribe((f"pong/{NODE_NAME}", 0))
client.subscribe((NODE_NAME, 0))
client.subscribe(('reset', 0))
client.subscribe((f"ack_request/{NODE_NAME}", 0))
if NODE_NAME == GATEWAY_NODE:
    client.subscribe((GATEWAY_NODE, 0))

# Start the loop to process incoming messages
client.loop_start()


# Function to reset connections and discovery pings
def reset_connections():
    global NEIGHBORS, latencies, connection_slots, accepted_connections
    # Inform neighbors about disconnection
    for neighbor in NEIGHBORS:
        client.publish(f"disconnect/{neighbor}", NODE_NAME)
        print(f"Notified {neighbor} about disconnection.")

    # If this is the gateway node, inform all nodes about its departure
    if NODE_NAME == GATEWAY_NODE:
        client.publish('disconnect/all', NODE_NAME)
        print(f"Gateway Node {NODE_NAME} has announced its departure.")

    # Reset connections
    NEIGHBORS = set()
    latencies = defaultdict(dict)
    # Reset connection slots for this node and all its neighbors
    connection_slots[NODE_NAME] = MAX_CONNECTIONS  # Reset connection slots for the current node
    for neighbor in accepted_connections[NODE_NAME]:
        connection_slots[neighbor] += 1  # Restore connection slots for neighbors
    accepted_connections[NODE_NAME] = set()  # Reset accepted connections for the current node
    client.publish(DISCOVERY_TOPIC, NODE_NAME)
    time.sleep(1)  # Allow some time for discovery messages


# Handle the disconnection announcement from the gateway
def handle_gateway_disconnection(node):
    if node in NEIGHBORS:
        NEIGHBORS.remove(node)
        connection_slots[node] += 1
        accepted_connections[node].remove(NODE_NAME)
        print(f"Removed {node} from connections due to gateway disconnection.")


# Callback to handle messages related to gateway disconnection
def on_message(client, userdata, msg):
    global NEIGHBORS, latencies, connection_slots, accepted_connections
    topic_parts = msg.topic.split('/')

    if msg.topic == 'reset':
        print(f"Received reset command. Resetting connections...")
        reset_connections()
        return

    if topic_parts[0] == 'ping' and topic_parts[1] == NODE_NAME:
        client.publish(f"pong/{msg.payload.decode().split(':')[0]}",
                       f"{NODE_NAME}:{msg.payload.decode().split(':')[1]}")
        print(f"Responded to ping from {msg.payload.decode().split(':')[0]}")
    elif topic_parts[0] == 'pong' and topic_parts[1] == NODE_NAME:
        latency = time.time() - float(msg.payload.decode().split(":")[1])
        sender = msg.payload.decode().split(":")[0]
        latencies[NODE_NAME][sender] = latency
        latencies[sender][NODE_NAME] = latency
        print(f"Measured latency to {sender}: {latency:.4f} seconds")
    elif msg.topic == DISCOVERY_TOPIC and msg.payload.decode() != NODE_NAME:
        new_neighbor = msg.payload.decode()
        if len(NEIGHBORS) < MAX_CONNECTIONS and new_neighbor not in NEIGHBORS:
            if connection_slots[new_neighbor] > 0:
                NEIGHBORS.add(new_neighbor)
                connection_slots[new_neighbor] -= 1  # Decrease the connection slot count for the new neighbor
                connection_slots[NODE_NAME] -= 1  # Decrease the connection slot count for the current node
                accepted_connections[NODE_NAME].add(new_neighbor)  # Add to accepted connections
                accepted_connections[new_neighbor].add(NODE_NAME)  # Mutual connection
                print(f"Discovered neighbor: {new_neighbor}")
                # Measure latency with new neighbor
                measure_latency(new_neighbor)
            else:
                print(f"Neighbor {new_neighbor} has reached its connection limit.")
        else:
            print(f"Already connected to maximum neighbors or neighbor {new_neighbor} is already connected.")
    elif topic_parts[0] == 'disconnect' and topic_parts[1] == NODE_NAME:
        disconnected_node = msg.payload.decode()
        if disconnected_node in NEIGHBORS:
            NEIGHBORS.remove(disconnected_node)
            connection_slots[disconnected_node] += 1  # Restore connection slot for the disconnected node
            accepted_connections[disconnected_node].remove(
                NODE_NAME)  # Remove from accepted connections of the disconnected node
            print(f"Disconnected from {disconnected_node}")
    elif topic_parts[0] == 'ack_request' and topic_parts[1] == NODE_NAME:
        handle_connection_acknowledgment(msg.payload.decode())
    elif msg.topic == 'disconnect/all':
        handle_gateway_disconnection(msg.payload.decode())
    else:
        payload = msg.payload.decode()
        if ':' in payload:
            sender, content = payload.split(':', 1)  # Split into sender and content
            if NODE_NAME == GATEWAY_NODE:
                print(f"Gateway received message from {sender}: {content}")
                # Reset connections after receiving a message
                reset_connections()
                # Broadcast reset command to other nodes
                broadcast_reset()
            else:
                print(f"Received message from {sender}: {content} on topic {msg.topic}")
                forward_message(client, sender, content)
        else:
            print(f"Received malformed message: {payload}")


# Function to send messages from the sender node
def send_messages():
    while True:
        message = input("Enter message to send (or 'show' to display connections, 'exit' to quit): ")
        if message.lower() == 'exit':
            # Broadcast reset command before exit
            reset_connections()
            break
        elif message.lower() == 'show':
            display_connections()
        else:
            # Check once if a path to the gateway exists
            print("Checking for a path to the gateway...")
            if path_exists_to_gateway():
                print("Path to the gateway found.")
                # Send the message once the path is established
                client.publish(GATEWAY_NODE, f"{NODE_NAME}:{message}")
                print(f"Sent message to Gateway: {message}")
            else:
                # Forward the message to the closest neighbor if no path to the gateway is found
                closest_neighbor = find_closest_neighbor()
                if closest_neighbor:
                    client.publish(closest_neighbor, f"{NODE_NAME}:{message}")
                    print(f"Sent message to closest neighbor {closest_neighbor} as fallback")
                else:
                    print(f"No path to gateway from {NODE_NAME} and no fallback neighbor found.")

            # Wait a short period before processing the next message
            time.sleep(2)
            print("Ready for the next message.")
            # Reset connections after sending the message
            reset_connections()
            print("Reset connections after sending the message.")

def display_connections():
    print(f"Current accepted connections for node {NODE_NAME}:")
    for node, connections in accepted_connections.items():
        print(f"{node}: {', '.join(connections)}")

def path_exists_to_gateway():
    path = dijkstra(latencies, NODE_NAME, GATEWAY_NODE)
    print(f"Path to gateway: {path}")
    return path is not None


# Start sending messages if this is the sender node
send_messages_thread = threading.Thread(target=send_messages)
send_messages_thread.start()

# Start the presence broadcast in a separate thread
broadcast_thread = threading.Thread(target=broadcast_presence)
broadcast_thread.start()

# Keep the script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
    send_messages_thread.join()
    broadcast_thread.join()
    print("Disconnected from MQTT broker.")
