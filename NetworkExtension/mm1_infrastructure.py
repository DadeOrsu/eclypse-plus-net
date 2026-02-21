import networkx as nx
import random
from collections import defaultdict
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

    def add_physical_link(self, u: str, v: str, bandwidth_mbps: float, length_km: float, propagation_speed_km_s: float = 200000.0, **kwargs):
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
            **kwargs: Additional edge attributes (e.g., 'cost', 'reliability').
        """
        bandwidth_bps = bandwidth_mbps * 1_000_000
        propagation_delay_s = length_km / propagation_speed_km_s
        propagation_delay_ms = propagation_delay_s * 1000.0

        self.add_edge(
            u, v,
            bandwidth=bandwidth_bps,
            propagation_delay_s=propagation_delay_s,
            latency=propagation_delay_ms,
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
                - 'queue_delay': Time spent waiting in the buffer (seconds).
                - 'service_time': Time spent transmitting the packet bits (seconds).
                - 'propagation_delay': Time spent travelling the physical medium (seconds).
                - 'total_delay': Sum of all delay components (seconds).
                - 'finish_time': Simulation time when the packet fully arrives at node 'v'.
            Returns None if the edge (u, v) does not exist.

        """
        bandwidth_bps = edge_data.get("bandwidth", 10_000_000)
        propagation_delay_s = edge_data.get("propagation_delay_s", 0.0)

        packet_bits = packet_size_bytes * 8
        avg_service_time = packet_bits / bandwidth_bps
        actual_service_time = random.expovariate(1.0/avg_service_time) if avg_service_time > 0 else 0.0

        last_free_time = self.link_next_free_time[(u, v)]
        service_start_time = max(current_time, last_free_time)
        queuing_delay = service_start_time - current_time

        service_finish_time = service_start_time + actual_service_time
        self.link_next_free_time[(u, v)] = service_finish_time

        total_delay = (service_finish_time - current_time) + propagation_delay_s

        return {
            "queue_delay": queuing_delay,
            "service_time": actual_service_time,
            "propagation_delay": propagation_delay_s,
            "total_delay": total_delay,
            "finish_time": service_finish_time + propagation_delay_s
        }

    def install_shortest_path_routes(self):
        """
        installs routing tables for each node in the network using shortest path logic based on latency.
        """
        nodes = list(self.nodes)
        print("--- Configuration of Routing Tables (OSPF simulation) ---")

        for source in nodes:
            for dest in nodes:
                if source == dest:
                    continue
                try:
                    # Calculate the shortest path based on latency and store the next hop in the routing table.
                    path = nx.shortest_path(self, source, dest, weight='latency')
                    next_hop = path[1]
                    self.routing_tables[source][dest] = next_hop
                except nx.NetworkXNoPath:
                    pass  # No path exists
        print("Routing tables installed on all nodes.")

    def get_next_hop(self, current_node: str, final_dest: str):
        return self.routing_tables[current_node].get(final_dest)

    def simulate_packet_routing(self, source: str, target: str, packet_size_bytes: int, start_time: float):
        current_node = source
        current_t = start_time
        hop_details = []
        path_taken = [source]

        for _ in range(20):
            if current_node == target:
                break

            next_node = self.get_next_hop(current_node, target)

            if not next_node:
                return {"status": "DROPPED", "reason": f"No route from {current_node} to {target}", "path": path_taken}

            edge_data = self.edges[current_node, next_node]
            stats = self.calculate_mm1_delay(current_node, next_node, edge_data, packet_size_bytes, current_t)

            if not stats:
                return {"status": "FAILED", "reason": f"Link fail {current_node}->{next_node}"}

            hop_details.append({
                "hop": f"{current_node}->{next_node}",
                "queue": stats['queue_delay'],
                "arrival_at_next": stats['finish_time']
            })

            # Update for next hop
            current_t = stats['finish_time']
            current_node = next_node
            path_taken.append(current_node)

        end_to_end_delay = current_t - start_time

        return {
            "status": "DELIVERED",
            "path": path_taken,
            "end_time": current_t,
            "total_e2e_delay": end_to_end_delay,
            "hops": hop_details
        }
