import paho.mqtt.client as mqtt
import threading
import time
from collections import defaultdict
import json
import networkx as nx
import matplotlib.pyplot as plt

# Configuration
BROKER_IP = '172.16.2.130'  # Local broker IP
DISCOVERY_TOPIC = 'discovery'
NODE_NAME = 'K'  # Change this for each node ('D', 'S', 'N', 'K')
GATEWAY_NODE = 'N'  # Specify the gateway node here
NEIGHBORS = set()
latencies = defaultdict(dict)
MAX_CONNECTIONS = 2  # Maximum number of connections per node
connection_slots = defaultdict(lambda: MAX_CONNECTIONS)  # Track available connection slots for each node
accepted_connections = defaultdict(set)  # Track accepted connections for each node
connections_list = defaultdict(list)  # List to store connections for each node
next_hop = None
topology_algorithm = None
connection_list_file = "connections_list.json"

# Define a global layout for node positions
def get_fixed_layout(G):
    return nx.spring_layout(G, seed=42)  # Use a seed for reproducible positions


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


def display_network_graph(G, pos, shortest_path_edges=None):
    # Draw the network graph
    nx.draw(G, pos, with_labels=True, node_size=2000, font_size=10, font_color='white', font_weight='bold', arrows=True)

    # Draw edges with different colors for the shortest path
    edge_labels = nx.get_edge_attributes(G, 'label')
    edge_colors = []
    for u, v, d in G.edges(data=True):
        if shortest_path_edges and (u, v) in shortest_path_edges:
            edge_colors.append('green')  # Color for shortest path edges
        else:
            edge_colors.append('black')  # Color for normal edges

    nx.draw_networkx_edges(G, pos, edgelist=G.edges(), edge_color=edge_colors, arrows=True)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='green', font_size=8)

    # Display the graph
    plt.title("Network Graph")
    plt.show()


# Periodically broadcast connections
def broadcast_connections_periodically():
    while True:
        time.sleep(6)  # Wait before broadcasting connections

        # Ensure that latency measurements are completed

        time.sleep(5)  # Additional wait to ensure latencies are updated

        # Check if there are connections to broadcast
        if accepted_connections[NODE_NAME]:
            # Construct connection info with latency
            connections_info = [f"{node}:{latencies[NODE_NAME].get(node, 'N/A')}" for node in
                                accepted_connections[NODE_NAME]]
            client.publish(f"connections/{GATEWAY_NODE}", f"{NODE_NAME}:{','.join(connections_info)}")
        # print(f"Broadcasting connections with latency for node {NODE_NAME}")
        else:
            print(f"No connections to broadcast for node {NODE_NAME}")

        # Wait for additional time to allow all nodes to process the broadcast
        time.sleep(5)


# Function to add a connection to the local connections list
def add_local_connection(neighbor, latency):
    if neighbor not in accepted_connections[NODE_NAME]:
        accepted_connections[NODE_NAME].add(neighbor)
        accepted_connections[neighbor].add(NODE_NAME)
        latencies[NODE_NAME][neighbor] = latency
        latencies[neighbor][NODE_NAME] = latency
        if NODE_NAME not in connections_list:
            connections_list[NODE_NAME] = []
        if neighbor not in connections_list:
            connections_list[neighbor] = []
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


def handle_received_message(message):
    # Implement the logic for handling the received message
    print(f"Handling received message: {message}")

    # Example: You might want to print the message, log it, or perform some action
    # For instance, you can add logic to process or forward the message further
    # You can also log it to a file or database if needed
    with open('received_messages.log', 'a') as file:
        file.write(f"{time.ctime()}: {message}\n")

    # If needed, perform further processing of the message
    # e.g., updating a database, triggering an event, etc.


# Callback when a message is received
def on_message(client, userdata, msg):
    global NEIGHBORS, latencies, connection_slots, accepted_connections, connections_list
    topic_parts = msg.topic.split('/')

    payload = msg.payload.decode()

    if topic_parts[0] == 'message':
        source_node, actual_message = payload.split(':', 1)
        if topic_parts[1] == GATEWAY_NODE:
            print(f"Message received from {source_node}: {actual_message}")
            handle_received_message(actual_message)
        elif topic_parts[1] == NODE_NAME:
            forward_message_to_next_hop(actual_message, source_node)
        else:
            return

    if topic_parts[0] == 'disconnect' and topic_parts[1] == 'all':
        departed_node = payload
        handle_node_departure(departed_node)

    if topic_parts[0] == 'connections' and topic_parts[1] == GATEWAY_NODE:
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
        if NODE_NAME == GATEWAY_NODE:
            calculate_and_broadcast_next_hops()
            print('calculating hops')

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
                           f"{NODE_NAME}:{','.join([f'{n}:{latencies[NODE_NAME].get(n)}' for n in accepted_connections[NODE_NAME]])}")
    elif topic_parts[0] == 'ack_request' and topic_parts[1] == NODE_NAME:
        handle_connection_acknowledgment(msg.payload.decode())
    elif topic_parts[0] == 'connections_request' and topic_parts[1] == NODE_NAME:
        if accepted_connections[NODE_NAME]:
            connections_info = [f"{node}:{latencies[NODE_NAME].get(node)}" for node in
                                accepted_connections[NODE_NAME]]
            client.publish(f"connections/{NODE_NAME}", f"{NODE_NAME}:{','.join(connections_info)}")
            print(f"Broadcasting connections for {NODE_NAME}")
        else:
            print(f"No connections to broadcast for {NODE_NAME}")

    elif topic_parts[0] == 'next_hop' and topic_parts[1] == NODE_NAME:
        global next_hop
        next_hop = payload
        print(f"Received next hop information: {next_hop}")


def recompute_shortest_paths():
    path, G, pos = find_shortest_path_to_gateway()
    if path:
        print(f"Recomputed shortest path: {' -> '.join(path)}")
    else:
        print("No path found to the gateway after recomputing")


def handle_node_departure(departed_node):
    print(f"Handling departure of node: {departed_node}")

    # Check if the departed node is in the connections list
    if departed_node in connections_list:
        print(f"Node {departed_node} found in connections list. Removing...")
        # Remove the departed node from the connections list
        del connections_list[departed_node]
    else:
        print(f"Node {departed_node} not found in connections list.")

    # Iterate through all remaining nodes in the connections list
    for node, connections in list(connections_list.items()):
        # Update the connections for each node by removing any that involve the departed node
        updated_connections = [conn for conn in connections if conn[0] != departed_node]
        if len(updated_connections) != len(connections):
            print(f"Updating connections for node {node}.")
        connections_list[node] = updated_connections

    # Log the update
    print(f"Updated connections list after {departed_node} departure: {connections_list}")

    # Save the updated connections list to a file
    save_connections_to_file()

    # Recompute the shortest paths based on the updated connections list
    recompute_shortest_paths()

def save_connections_to_file():
    file_path = 'connections_list.json'
    with open(file_path, 'w') as file:
        json.dump(connections_list, file)
    print(f"Connections saved to {file_path}")


def load_connections_from_file():
    file_path = 'connections_list.json'
    try:
        with open(file_path, 'r') as file:
            connections = json.load(file)
        print(f"Connections loaded from {file_path}")
        # Ensure all nodes have an entry in connections_list
        for node in [NODE_NAME, *connections.keys()]:
            if node not in connections:
                connections[node] = []
        return connections
    except FileNotFoundError:
        print(f"{file_path} not found. Starting with an empty connections list.")
        return defaultdict(list)


# Connect to the MQTT broker
client = mqtt.Client()

client.connect(BROKER_IP, 1883, 60)
client.subscribe(DISCOVERY_TOPIC)
client.subscribe(f"connections/{NODE_NAME}")
client.subscribe(f"ping/{NODE_NAME}")
client.subscribe(f"pong/{NODE_NAME}")
client.subscribe(f"disconnect/{NODE_NAME}")
client.subscribe(f"ack_request/{NODE_NAME}")
client.subscribe(f"next_hop/{NODE_NAME}")
client.subscribe(f"message/{NODE_NAME}")
client.subscribe('disconnect/all')
client.subscribe(f"connections_request/{NODE_NAME}")

# Start the periodic presence broadcasting in a separate thread
presence_thread = threading.Thread(target=broadcast_presence)
presence_thread.daemon = True
presence_thread.start()

# Start the periodic connections broadcasting in a separate thread
connections_broadcast_thread = threading.Thread(target=broadcast_connections_periodically)
connections_broadcast_thread.daemon = True
connections_broadcast_thread.start()

# Load previously saved connections from file
# connections_list = load_connections_from_file()

# Start the MQTT client loop
client.loop_start()


def broadcast_departure():
    client.publish('disconnect/all', NODE_NAME)
    print(f"Broadcasting departure for node {NODE_NAME}")


# Function to find the shortest path to the gateway
def find_shortest_path_to_gateway():
    G = nx.Graph()
    G.add_node(NODE_NAME)
    print("Building graph with nodes:")
    for node, connections in connections_list.items():
        print(f"Node: {node}, Connections: {connections}")
        for neighbor, latency in connections:
            G.add_edge(node, neighbor, weight=latency, label=f"{latency:.4f}")

    pos = get_fixed_layout(G)

    print(f"Graph nodes: {list(G.nodes)}")
    print(f"Graph edges: {list(G.edges)}")

    if nx.has_path(G, NODE_NAME, GATEWAY_NODE):
        shortest_path = nx.shortest_path(G, source=NODE_NAME, target=GATEWAY_NODE, weight='weight')
        print(f"Shortest path to the gateway ({GATEWAY_NODE}): {' -> '.join(shortest_path)}")
        return shortest_path, G, pos
    else:
        print(f"No path found to the gateway ({GATEWAY_NODE}) from {NODE_NAME}")
        return None, G, pos




# Function to forward a message
def forward_message_to_next_hop(message, source):
    global next_hop
    hop = next_hop
    # Include the source node information in the message
    full_message = f"{source}:{message}"
    client.publish(f"message/{hop}", full_message)
    print(f"Forwarded message to {hop}")
def calculate_shortest_paths_dijkstra(connections_list, start_node):
    # Build the graph from connections_list
    G = nx.Graph()
    for node, connections in connections_list.items():
        for neighbor, latency in connections:
            G.add_edge(node, neighbor, weight=latency, label=f'{latency:.2f}')
    # Calculate shortest paths
    shortest_paths = nx.single_source_dijkstra_path(G, start_node, weight='weight')
    shortest_path_edges = set()
    for target_node, path in shortest_paths.items():
        for i in range(len(path) - 1):
            shortest_path_edges.add((path[i], path[i + 1]))
    return shortest_paths, shortest_path_edges

def calculate_shortest_paths_bellman_ford(connections_list, start_node):
    # Build the graph from connections_list
    G = nx.DiGraph()
    for node, connections in connections_list.items():
        for neighbor, latency in connections:
            G.add_edge(node, neighbor, weight=latency, label=f'{latency:.2f}')
    # Calculate shortest paths
    shortest_paths = nx.single_source_bellman_ford_path(G, start_node, weight='weight')
    shortest_path_edges = set()
    for target_node, path in shortest_paths.items():
        for i in range(len(path) - 1):
            shortest_path_edges.add((path[i], path[i + 1]))
    return shortest_paths, shortest_path_edges


def calculate_and_broadcast_next_hops():
    global next_hop, topology_algorithm
    if not connections_list:
        print("No connections available for calculating shortest paths.")
        return
    if topology_algorithm == 'dijkstra':
        shortest_paths, shortest_path_edges = calculate_shortest_paths_dijkstra(connections_list, GATEWAY_NODE)
    elif topology_algorithm == 'bellman_ford':
        shortest_paths, shortest_path_edges = calculate_shortest_paths_bellman_ford(connections_list, GATEWAY_NODE)
    else:
        print(f"Unknown topology algorithm: {topology_algorithm}")
        return

    if NODE_NAME in shortest_paths:
        path = shortest_paths[NODE_NAME]
        if len(path) > 1:
            next_hop = path[1]
            print(f"Next hop for {NODE_NAME} is {next_hop}")

    # Build the graph from connections_list
    G = nx.Graph()
    for node, connections in connections_list.items():
        for neighbor, latency in connections:
            G.add_edge(node, neighbor, weight=latency, label=f'{latency:.2f}')

    # Display the network graph
    pos = get_fixed_layout(G)
    # display_network_graph(G, pos, shortest_path_edges)


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
    save_connections_to_file()
    # Broadcast presence to allow reconnection
    client.publish(DISCOVERY_TOPIC, NODE_NAME)
    print("Reset connections and broadcasting presence.")

    # Allow time for all nodes to reset and reconnect
    time.sleep(1)


# Interactive loop to send messages or visualize the network
def leave_network():
    broadcast_departure()
    client.loop_stop()


# def forward_message(message):
#     global next_hop
#     path, G, pos = find_shortest_path_to_gateway()
#     if path:
#         forward_message_to_next_hop(next_hop, message)
#     else:
#         print(f"Cannot forward message, no path to gateway ({GATEWAY_NODE}) found.")
def select_topology_algorithm():
    global topology_algorithm
    print("Select the topology algorithm:")
    print("1. Dijkstra")
    print("2. Bellman-Ford")
    choice = input("Enter your choice (1 or 2): ")
    if choice == '1':
        topology_algorithm = 'dijkstra'
    elif choice == '2':
        topology_algorithm = 'bellman_ford'
    else:
        print("Invalid choice. Using Dijkstra as the default algorithm.")
        topology_algorithm = 'dijkstra'


try:
    # Select the topology algorithm at the start
    if NODE_NAME == GATEWAY_NODE:
        select_topology_algorithm()
    while True:
        client.on_message = on_message
        user_input = input("Enter a command (send <message> / show / leave /  reset): ")
        if user_input.startswith("send "):
            message = user_input[5:]
            forward_message_to_next_hop(message, NODE_NAME)
            print("Message forwarded to ", next_hop)
        elif user_input == "show":
            print(accepted_connections)
            print(latencies)
            print(connection_slots)
            print(connections_list)
            print(next_hop)
            _, G, pos = find_shortest_path_to_gateway()
            display_network_graph(G, pos)
        elif user_input == "leave":
            leave_network()
            with open(connection_list_file, 'w') as f:
                json.dump({}, f)
            break
        elif user_input == "reset" and NODE_NAME == GATEWAY_NODE:
            reset_connections()
        elif user_input == "exit":
            with open(connection_list_file, 'w') as f:
                json.dump({}, f)
            break
except KeyboardInterrupt:
    leave_network()
    with open(connection_list_file, 'w') as f:
        f.truncate()
    print("Interrupted by user")


# Clean up
client.loop_stop()
