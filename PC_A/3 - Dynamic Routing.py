import paho.mqtt.client as mqtt
import threading
import time
import heapq
from collections import defaultdict
import json
import networkx as nx
import matplotlib.pyplot as plt

# Configuration
BROKER_IP = '172.16.2.100'  # Local broker IP
DISCOVERY_TOPIC = 'discovery'
NODE_NAME = 'K'  # Change this for each node ('D', 'S', 'N', 'K')
GATEWAY_NODE = 'N'  # Specify the gateway node here
NEIGHBORS = set()
latencies = defaultdict(dict)
MAX_CONNECTIONS = 2  # Maximum number of connections per node
connection_slots = defaultdict(lambda: MAX_CONNECTIONS)  # Track available connection slots for each node
accepted_connections = defaultdict(set)  # Track accepted connections for each node
connections_list = defaultdict(list)  # List to store connections for each node
latency2 = 0


# Periodically broadcast presence for neighbor discovery
def broadcast_presence():
    while True:
        if connection_slots[NODE_NAME] > 0:
            client.publish(DISCOVERY_TOPIC, NODE_NAME)
            print(f"Broadcasting presence: {NODE_NAME}")
        time.sleep(10)  # Broadcast every 10 seconds


def load_connections_from_json(file_path):
    with open(file_path, 'r') as file:
        connections = json.load(file)
    return connections


def display_network_graph(connections_list):
    # Create a new directed graph
    G = nx.DiGraph()

    # Add nodes and edges with latencies as edge labels
    for node, connections in connections_list.items():
        G.add_node(node)
        for neighbor, latency in connections:
            if G.has_edge(neighbor, node):
                # Mark bidirectional edges
                G[neighbor][node]['bidirectional'] = True
            else:
                G.add_edge(node, neighbor, weight=latency, label=f"{latency:.2f} ms", bidirectional=False)

    # Set node colors
    node_colors = []
    for node in G.nodes():
        if node == GATEWAY_NODE:
            node_colors.append('red')  # Gateway node in red
        else:
            node_colors.append('blue')  # Other nodes in blue

    # Use a fixed seed for reproducible layout positions
    pos = nx.spring_layout(G, seed=42)  # Set a seed for reproducible positions

    # Draw the network graph
    nx.draw(G, pos, with_labels=True, node_color=node_colors, node_size=2000, font_size=10, font_color='white',
            font_weight='bold', arrowsize=20)

    # Draw edges with different arrows for bidirectional connections
    edge_labels = nx.get_edge_attributes(G, 'label')
    edge_colors = []
    for u, v, d in G.edges(data=True):
        if d.get('bidirectional', False):
            edge_colors.append('orange')  # Color for bidirectional edges
        else:
            edge_colors.append('black')  # Color for normal edges

    nx.draw_networkx_edges(G, pos, edgelist=G.edges(), edge_color=edge_colors, arrows=True)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='green', font_size=8)

    # Display the graph
    plt.title("Network Graph")
    plt.show()


# Load connections from JSON file


# Periodically broadcast connections
def broadcast_connections_periodically():
    while True:
        time.sleep(600)  # Wait before broadcasting connections

        # Ensure that latency measurements are completed
        print("Waiting for latency updates...")
        time.sleep(5)  # Additional wait to ensure latencies are updated

        # Construct connection info with latency
        connections_info = [f"{node}:{latencies[NODE_NAME].get(node, 'N/A')}" for node in
                            accepted_connections[NODE_NAME]]
        client.publish(f"connections/{NODE_NAME}", f"{NODE_NAME}:{','.join(connections_info)}")
        print(f"Broadcasting connections with latency for node {NODE_NAME}")

        # Wait for additional time to allow all nodes to process the broadcast
        time.sleep(5)


# Function to add a connection to the local connections list
def add_local_connection(neighbor, latency):
    if neighbor not in accepted_connections[NODE_NAME]:
        accepted_connections[NODE_NAME].add(neighbor)
        accepted_connections[neighbor].add(NODE_NAME)
        latencies[NODE_NAME][neighbor] = latency
        latencies[neighbor][NODE_NAME] = latency
        connections_list[NODE_NAME].append((neighbor, latency))
        connections_list[neighbor].append((NODE_NAME, latency))
        print(f"Added connection with {neighbor} with latency {latency}")
    else:
        print(f"Connection with {neighbor} already exists")


# Function to handle new connections and update lists
def handle_new_connection(neighbor, latency):
    if len(NEIGHBORS) < MAX_CONNECTIONS and neighbor not in NEIGHBORS:
        if connection_slots[neighbor] > 0:
            NEIGHBORS.add(neighbor)
            connection_slots[neighbor] -= 1
            connection_slots[NODE_NAME] -= 1
            add_local_connection(neighbor, latency)
            # Request connection list from newly connected node
            client.publish(f"connections_request/{neighbor}", NODE_NAME)
            client.publish(f"connections/{NODE_NAME}",
                           f"{NODE_NAME}:{','.join([f'{n}:{latencies[NODE_NAME].get(n, 'N/A')}' for n in accepted_connections[NODE_NAME]])}")
        else:
            print(f"Neighbor {neighbor} has reached its connection limit.")
    else:
        print(f"Already connected to maximum neighbors or neighbor {neighbor} is already connected.")


# Function to broadcast a reset command to all nodes
def broadcast_reset():
    client.publish('reset', 'RESET_COMMAND')
    print("Broadcasting reset command to all nodes")


# Measure latency to a neighbor
def measure_latency(neighbor):
    start_time = time.time()
    client.publish(f"ping/{neighbor}", f"{NODE_NAME}:{start_time}")
    print(f"Measuring latency to {neighbor}.")
    return start_time


def request_connection_acknowledgment(neighbor):
    client.publish(f"ack_request/{neighbor}", NODE_NAME)
    print(f"Requested acknowledgment from {neighbor}")


def handle_connection_acknowledgment(sender):
    if sender in NEIGHBORS:
        accepted_connections[NODE_NAME].add(sender)
        accepted_connections[sender].add(NODE_NAME)
        print(f"Connection with {sender} is now finalized")
        # Request connection list from newly connected node
        client.publish(f"connections_request/{sender}", NODE_NAME)
    else:
        print(f"Unexpected acknowledgment from {sender}")


# Callback when a message is received
def on_message(client, userdata, msg):
    global NEIGHBORS, latencies, connection_slots, accepted_connections, connections_list
    topic_parts = msg.topic.split('/')

    if msg.payload.decode().startswith(NODE_NAME + ":"):
        print(f"Ignoring loopback message: {msg.payload.decode()}")
        return

    payload = msg.payload.decode()

    if topic_parts[0] == 'connections' and topic_parts[1] == NODE_NAME:
        node, connections_info = payload.split(':', 1)
        connections_list[node] = []
        for info in connections_info.split(','):
            if ':' in info:
                parts = info.split(':')
                if len(parts) == 2:
                    neighbor, latency = parts
                    try:
                        latency = float(latency)
                        connections_list[node].append((neighbor, latency))
                        latencies[node][neighbor] = latency
                        latencies[neighbor][node] = latency
                    except ValueError:
                        print(f"Warning: Invalid latency value: {latency}")
                else:
                    print(f"Warning: Info string does not contain exactly two parts separated by ':': {info}")
            else:
                print(f"Warning: Info string does not contain ':': {info}")
        print(f"Received connections list with latency from {node}: {connections_list[node]}")
        save_connections_to_file()

    elif topic_parts[0] == 'ping' and topic_parts[1] == NODE_NAME:
        client.publish(f"pong/{msg.payload.decode().split(':')[0]}",
                       f"{NODE_NAME}:{msg.payload.decode().split(':')[1]}")
        print(f"Responded to ping from {msg.payload.decode().split(':')[0]}")
    elif topic_parts[0] == 'pong' and topic_parts[1] == NODE_NAME:
        latency = time.time() - float(msg.payload.decode().split(":")[1])
        sender = msg.payload.decode().split(":")[0]
        latencies[NODE_NAME][sender] = latency
        latencies[sender][NODE_NAME] = latency
        print(f"Measured latency to {sender}: {latency:.4f} seconds")
        handle_new_connection(sender, latency)
    elif msg.topic == DISCOVERY_TOPIC and msg.payload.decode() != NODE_NAME:
        new_neighbor = msg.payload.decode()
        if new_neighbor not in accepted_connections[NODE_NAME]:
            start_time = measure_latency(new_neighbor)

    elif topic_parts[0] == 'disconnect' and topic_parts[1] == NODE_NAME:
        disconnected_node = msg.payload.decode()
        if disconnected_node in NEIGHBORS:
            NEIGHBORS.remove(disconnected_node)
            connection_slots[disconnected_node] += 1
            accepted_connections[disconnected_node].remove(NODE_NAME)
            print(f"Disconnected from {disconnected_node}")
            client.publish(f"connections/{NODE_NAME}",
                           f"{NODE_NAME}:{','.join([f'{n}:{latencies[NODE_NAME].get(n, 'N/A')}' for n in accepted_connections[NODE_NAME]])}")
    elif topic_parts[0] == 'ack_request' and topic_parts[1] == NODE_NAME:
        handle_connection_acknowledgment(msg.payload.decode())
    elif msg.topic == 'disconnect/all':
        handle_gateway_disconnection(msg.payload.decode())
    elif topic_parts[0] == 'connections_request' and topic_parts[1] == NODE_NAME:
        connections_info = [f"{node}:{latencies[NODE_NAME].get(node, 'N/A')}" for node in
                            accepted_connections[NODE_NAME]]
        client.publish(f"connections/{msg.payload.decode()}", f"{NODE_NAME}:{','.join(connections_info)}")
    elif msg.topic == 'reset':
        reset_connections()
    else:
        if ':' in payload:
            parts = payload.split(':', 2)
            sender = parts[0]
            message = parts[1]
            path_info = parts[2] if len(parts) > 2 else "NoPath"
            if NODE_NAME == GATEWAY_NODE:
                print(f"Gateway received message from {sender}: {message} with path {path_info}")
                reset_connections()
                broadcast_reset()
            else:
                print(f"Received message from {sender}: {message} with path {path_info} on topic {msg.topic}")
                forward_message(client, sender, message)
        else:
            print(f"Received malformed message: {payload}")




# Function to forward messages based on the shortest path using Dijkstra's algorithm
def forward_message(client, sender, message):
    if GATEWAY_NODE in accepted_connections[NODE_NAME]:
        # Path is empty when sending directly to the gateway
        client.publish(GATEWAY_NODE, f"{NODE_NAME}:{message}:Path:")
        print(f"Directly sent message to Gateway {GATEWAY_NODE} with path info")
    else:
        path = dijkstra(latencies, NODE_NAME, GATEWAY_NODE)
        if path and len(path) > 0:
            next_hop = path[1]
            path_info = "->".join(path)
            client.publish(next_hop, f"{NODE_NAME}:{message}:Path:{path_info}")
            print(f"Sent message to {next_hop} (part of path to {GATEWAY_NODE}) with path info")
            # Request connection list from next hop
            client.publish(f"connections_request/{next_hop}", NODE_NAME)
        else:
            # Forward to the closest neighbor if no path to gateway is found
            closest_neighbor = find_closest_neighbor()
            if closest_neighbor:
                client.publish(closest_neighbor, f"{NODE_NAME}:{message}:Path:NoPath")
                print(f"Sent message to closest neighbor {closest_neighbor} as fallback with path info")
                # Request connection list from closest neighbor
                client.publish(f"connections_request/{closest_neighbor}", NODE_NAME)
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


# Save connections list to a file
def save_connections_to_file():
    with open('connections_list.json', 'w') as f:
        json.dump(connections_list, f, indent=4)
    print("Saved connections list with latency to 'connections_list.json'")


# Set up the MQTT client
client = mqtt.Client()
client.on_message = on_message

# Connect to the local MQTT broker
client.connect(BROKER_IP, 1883, 60)

# Subscribe to discovery, latency, and node-specific topics
client.subscribe((DISCOVERY_TOPIC, 1))
client.subscribe((f"ping/{NODE_NAME}", 1))
client.subscribe((f"pong/{NODE_NAME}", 1))
client.subscribe((NODE_NAME, 1))
client.subscribe(('reset', 0))
client.subscribe((f"ack_request/{NODE_NAME}", 1))
client.subscribe((f"connections/{NODE_NAME}", 1))
client.subscribe((f"connections_request/{NODE_NAME}", 1))
if NODE_NAME == GATEWAY_NODE:
    client.subscribe((GATEWAY_NODE, 0))

# Start the loop to process incoming messages
client.loop_start()


# Function to reset connections and discovery pings
def reset_connections():
    global NEIGHBORS, latencies, connection_slots, accepted_connections, connections_list
    for neighbor in NEIGHBORS:
        client.publish(f"disconnect/{neighbor}", NODE_NAME)
        print(f"Notified {neighbor} about disconnection.")

    client.publish('disconnect/all', NODE_NAME)
    print(f"Gateway Node {NODE_NAME} has announced its departure.")

    # Reset local connection lists
    NEIGHBORS = set()
    latencies = defaultdict(dict)
    connection_slots[NODE_NAME] = MAX_CONNECTIONS
    for neighbor in accepted_connections[NODE_NAME]:
        connection_slots[neighbor] += 1
    accepted_connections[NODE_NAME] = set()
    connections_list = defaultdict(list)  # Reset connections list

    # Broadcast presence to allow reconnection
    client.publish(DISCOVERY_TOPIC, NODE_NAME)
    print("Reset connections and broadcasting presence.")

    # Allow time for all nodes to reset and reconnect
    time.sleep(1)


# Handle the disconnection announcement from the gateway
def handle_gateway_disconnection(node):
    if node in NEIGHBORS:
        NEIGHBORS.remove(node)
        connection_slots[node] += 1
        accepted_connections[node].remove(NODE_NAME)
        print(f"Removed {node} from connections due to gateway disconnection.")
        # Broadcast connections after removal
        client.publish(f"connections/{NODE_NAME}", f"{NODE_NAME}:{','.join(accepted_connections[NODE_NAME])}")


# Function to send messages from the sender node
def send_messages():
    # Broadcast reset command on startup
    broadcast_reset()
    time.sleep(2)  # Allow time for nodes to reset their connections

    while True:
        message = input("Enter message to send (or 'show' to display connections, 'exit' to quit): ")
        if message.lower() == 'exit':
            break
        elif message.lower() == 'show':
            connections_list2 = load_connections_from_json('connections_list.json')

            display_connections()
            display_network_graph(connections_list2)
        else:
            # Broadcast presence to initiate connection process
            broadcast_presence_once()
            time.sleep(2)  # Allow time for nodes to connect and measure latency

            # Wait for latency updates before checking path
            print("Waiting for latency updates...")
            time.sleep(5)  # Allow additional time for latency updates

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

            time.sleep(2)
            print("Ready for the next message.")
            # Reset connections after sending the message
            reset_connections()
            print("Reset connections after sending the message.")


def broadcast_presence_once():
    if connection_slots[NODE_NAME] > 0:
        client.publish(DISCOVERY_TOPIC, NODE_NAME)
        print(f"Broadcasting presence: {NODE_NAME}")


def display_connections():
    print(f"Current accepted connections for node {NODE_NAME}:")
    for node, connections in accepted_connections.items():
        print(f"{node}: {', '.join(connections)}")


def path_exists_to_gateway():
    # Reconstruct the entire connection graph
    full_graph = defaultdict(dict)
    for node, connections in connections_list.items():
        for neighbor in connections:
            if neighbor in latencies[node]:
                full_graph[node][neighbor] = latencies[node][neighbor]

    path = dijkstra(full_graph, NODE_NAME, GATEWAY_NODE)
    print(f"Path to gateway: {path}")
    return path is not None


# Start sending messages if this is the sender node
send_messages_thread = threading.Thread(target=send_messages)
send_messages_thread.start()

# Start the presence broadcast in a separate thread
broadcast_thread = threading.Thread(target=broadcast_presence)
broadcast_thread.start()

# Start the periodic connections broadcasting in a separate thread
connections_broadcast_thread = threading.Thread(target=broadcast_connections_periodically)
connections_broadcast_thread.start()

# Keep the script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
    send_messages_thread.join()
    broadcast_thread.join()
    connections_broadcast_thread.join()
    print("Disconnected from MQTT broker.")
