import networkx as nx
import random
from collections import defaultdict, deque
from eclypse.graph import Infrastructure


class MM1Infrastructure(Infrastructure):
    """
    Extension of the Infrastructure model of ECLYPSE to simulate a network of
    routers using M/M/1 queuing logic.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This dictionary will track the next free time for each link (u, v) to simulate M/M/1 queues.
        self.link_next_free_time = defaultdict(float)
        # dictionary to store routing tables for each node: routing_tables[node][destination] = next_hop
        self.routing_tables = defaultdict(dict)
        # This dictionary will store the queue of packets for each link (u, v).
        self.link_queues = defaultdict(deque)

    def add_physical_link(self, u: str, v: str, bandwidth_mbps: float, length_km: float,
                          propagation_speed_km_s: float = 200000.0,
                          processing_delay_s: float = 0.0001, **kwargs):
        """
        Adds a network link between two nodes with defined physical properties.
        This method converts high-level physical parameters (like Mbps and km)
        into simulation-ready units (bps and seconds) and stores them as edge
        attributes.
        Args:
            u (str): The source node ID.
            v (str): The destination node ID.
            bandwidth_mbps (float): The link bandwidth (transmission speed) in Megabits per second.
            length_km (float): The physical length of the cable in Kilometers.
            propagation_speed_km_s (float, optional): The speed of signal propagation in km/s. 
                Defaults to 200,000.0 km/s (typical for fiber optics).
            processing_delay_s (float, optional): The fixed processing delay at the router in seconds.
                Defaults to 0.0001 seconds (100 microseconds).
            **kwargs: Additional edge attributes (e.g., 'cost', 'reliability').
        """
        bandwidth_bps = bandwidth_mbps * 1_000_000
        self.add_edge(
            u, v,
            bandwidth=bandwidth_bps,
            length_km=length_km,
            propagation_speed_km_s=propagation_speed_km_s,
            processing_delay_s=processing_delay_s,
            latency=(length_km / propagation_speed_km_s) * 1000.0,
            **kwargs
        )

    def calculate_mm1_delay(self, u: str, v: str, edge_data: dict, packet_size_bytes: int, current_time: float) -> dict:
        """
        calculates the delay components for a single packet traversing a
        specific link (u->v) based on M/M/1 queuing delay.

        Args:
            u (str): The source node ID of the link.
            v (str): The destination node ID of the link.
            packet_size_bytes (int): The size of the packet in bytes.
            current_time (float): The simulation time at which the packet arrives at node 'u'.
        Returns:
            dict: A dictionary containing delay statistics:
                - 'processing_delay': Time spent processing the packet at node 'u' (seconds).
                - 'queue_delay': Time spent waiting in the buffer (seconds).
                - 'transmission_delay': Time spent transmitting the packet bits (seconds).
                - 'propagation_delay': Time spent travelling the physical medium (seconds).
                - 'total_delay': Sum of all delay components (seconds).
                - 'finish_time': Simulation time when the packet fully arrives at node 'v'.
            Returns None if the edge (u, v) does not exist.

        """
        # Processing delay (d_proc)
        d_proc = edge_data.get("processing_delay_s", 0.0001)
        time_after_processing = current_time + d_proc

        # Management of the queue of the link (u, v)
        queue = self.link_queues[(u, v)]

        # We remove from the queue all packets that have already finished their transmission
        # before the arrival of our packet (time_after_processing)
        while queue and queue[0] <= time_after_processing:
            queue.popleft()

        # We measure the number of packets currently in the queue (before adding our packet)
        current_queue_length = len(queue)
        # ----------------------------------

        # 2. Transmission delay (d_trans = L / R)
        L = packet_size_bytes * 8
        R = edge_data.get("bandwidth", 10_000_000)
        d_trans_theoretical = L / R if R > 0 else 0.0
        d_trans = random.expovariate(1.0 / d_trans_theoretical) if d_trans_theoretical > 0 else 0.0

        # 3. Queuing delay (d_queue)
        last_free_time = self.link_next_free_time[(u, v)]
        service_start_time = max(time_after_processing, last_free_time)
        d_queue = service_start_time - time_after_processing

        # Update the state of the link (u, v)
        service_finish_time = service_start_time + d_trans
        self.link_next_free_time[(u, v)] = service_finish_time

        # Insertion in the queue
        # Add the packet to the queue (represented by its finish time) to simulate the M/M/1 queue
        queue.append(service_finish_time)
        # ------------------------------

        # 4. Propagation delay (d_prop = d / s)
        d = edge_data.get("length_km", 0.0)
        s = edge_data.get("propagation_speed_km_s", 200000.0)
        d_prop = d / s if s > 0 else 0.0

        total_delay = d_proc + d_queue + d_trans + d_prop

        return {
            "processing_delay": d_proc,
            "queue_delay": d_queue,
            "transmission_delay": d_trans,
            "propagation_delay": d_prop,
            "total_delay": total_delay,
            "finish_time": service_finish_time + d_prop,
            "queue_length_packets": current_queue_length
        }

    def install_shortest_path_routes(self):
        """
        installs routing tables for each node in the network using shortest path logic based on latency.
        """
        nodes = list(self.nodes)
        print("--- Configuration of Routing Tables (OSPF simulation) ---")
        for source in nodes:
            for dest in nodes:
                if source == dest: continue
                try:
                    path = nx.shortest_path(self, source, dest, weight='latency')
                    self.routing_tables[source][dest] = path[1]
                except nx.NetworkXNoPath:
                    pass
        print("Routing tables installed on all nodes.")

    def get_next_hop(self, current_node: str, final_dest: str):
        return self.routing_tables[current_node].get(final_dest)

    def simulate_packet_routing(self, source: str, target: str, packet_size_bytes: int, start_time: float):
        current_node = source
        current_t = start_time
        hop_details = []
        path_taken = [source]

        for _ in range(20):
            if current_node == target: break

            next_node = self.get_next_hop(current_node, target)
            if not next_node:
                return {"status": "DROPPED", "reason": f"No route from {current_node} to {target}", "path": path_taken}

            edge_data = self.edges[current_node, next_node]
            stats = self.calculate_mm1_delay(current_node, next_node, edge_data, packet_size_bytes, current_t)

            if not stats:
                return {"status": "FAILED", "reason": f"Link fail {current_node}->{next_node}"}

            hop_details.append({
                "hop": f"{current_node}->{next_node}",
                "processing_ms": stats['processing_delay'] * 1000.0,
                "queue_ms": stats['queue_delay'] * 1000.0,
                "transmission_ms": stats['transmission_delay'] * 1000.0,
                "propagation_ms": stats['propagation_delay'] * 1000.0,
                "queue_length": stats['queue_length_packets'],
                "arrival_at_next": stats['finish_time']
            })

            current_t = stats['finish_time']
            current_node = next_node
            path_taken.append(current_node)

        return {
            "status": "DELIVERED",
            "path": path_taken,
            "end_time": current_t,
            "total_e2e_delay": current_t - start_time,
            "hops": hop_details
        }
