import networkx as nx
import random
import numpy as np
from collections import defaultdict, deque
from eclypse.graph import Infrastructure
from network_application import Packet
from typing import List
from dataclasses import dataclass, field
from constants import (
    MIN_BANDWIDTH,
    MIN_LENGTH_KM,
    MIN_PROPAGATION_SPEED
)


@dataclass(slots=True)
class DelayMetrics:
    processing_delay: float
    queue_delay: float
    transmission_delay: float
    propagation_delay: float
    total_delay: float
    finish_time: float
    queue_length_packets: int


@dataclass(slots=True)
class HopInfo:
    hop: str
    processing_ms: float
    queue_ms: float
    transmission_ms: float
    propagation_ms: float
    queue_length: int
    arrival_at_next: float


@dataclass(slots=True)
class RoutingResult:
    status: str
    reason: str = ""
    path: List[str] = field(default_factory=list)
    end_time: float = 0.0
    total_e2e_delay: float = 0.0
    hops: List[HopInfo] = field(default_factory=list) 


class Network(Infrastructure):
    """
    Extension of the Infrastructure model of ECLYPSE to simulate a network of
    routers using queuing logic, with physical packet queuing.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.link_next_free_time = defaultdict(float)
        self.link_queues = defaultdict(deque)
        self.node_to_idx = {}
        self.idx_to_node = {}
        self.routing_matrix = np.empty((0, 0), dtype=np.int32)

    def add_edge(self, u_of_edge: str, v_of_edge: str, bandwidth_mbps: float = 100.0, 
                 length_km: float = 1.0, propagation_speed_km_s: float = 200000.0, 
                 processing_delay_s: float = 0.0001, **attr):
        """
        Overrides the default add_edge to automatically calculate and inject
        queuing parameters (bandwidth in bps, latency, propagation, processing).
        """
        attr['parameters'] = bandwidth_mbps * 1_000_000
        attr['bandwidth_mbps'] = bandwidth_mbps
        attr['length_km'] = length_km
        attr['propagation_speed_km_s'] = propagation_speed_km_s
        attr['processing_delay_s'] = processing_delay_s
        attr['latency'] = (length_km / propagation_speed_km_s) * 1000.0
        super().add_edge(u_of_edge, v_of_edge, **attr)

    def delay(self, u: str, v: str, edge_data: dict, packet: dict, current_time: float) -> dict:
        """
        calculates the delay components for a single packet traversing a
        specific link (u->v).

        Args:
            u (str): The source node ID of the link.
            v (str): The destination node ID of the link.
            packet (dict): The packet dictionary containing at least 'size' key.
            current_time (float): The simulation time at which the packet arrives at node 'u'.
        Returns:
            DelayMetrics: A dataclass containing the following fields:
                - 'processing_delay': Time spent processing the packet at node 'u' (seconds).
                - 'queue_delay': Time spent waiting in the buffer (seconds).
                - 'transmission_delay': Time spent transmitting the packet bits (seconds).
                - 'propagation_delay': Time spent travelling the physical medium (seconds).
                - 'total_delay': Sum of all delay components (seconds).
                - 'finish_time': Simulation time when the packet fully arrives at node 'v'.
                - 'queue_length_packets': Number of packets in the queue at the time of arrival (before adding the current packet).
            Returns None if the edge (u, v) does not exist.

        """
        d_proc = edge_data.get("processing_delay_s", 0.0001)
        time_after_processing = current_time + d_proc

        queue = self.link_queues[(u, v)]

        # We discard packets that have already completed transmission.
        # queue[0][0] accesses the `service_finish_time` of the first packet in the queue.
        while queue and queue[0][0] <= time_after_processing:
            queue.popleft()

        current_queue_length = len(queue)
        # delay calculations using packet.size
        L = packet.size * 8
        R = edge_data.get("bandwidth_mbps", MIN_BANDWIDTH)
        R = R * 1_000_000
        d_trans_theoretical = L / R if R > 0 else 0.0
        d_trans = random.expovariate(1.0 / d_trans_theoretical) if d_trans_theoretical > 0 else 0.0

        last_free_time = self.link_next_free_time[(u, v)]
        service_start_time = max(time_after_processing, last_free_time)
        d_queue = service_start_time - time_after_processing

        service_finish_time = service_start_time + d_trans
        self.link_next_free_time[(u, v)] = service_finish_time

        # Insert the packet into the queue with its expected finish time
        queue.append((service_finish_time, packet))
        d = edge_data.get("length_km", MIN_LENGTH_KM)
        s = edge_data.get("propagation_speed_km_s", MIN_PROPAGATION_SPEED)
        d_prop = d / s if s > 0 else 0.0

        total_delay = d_proc + d_queue + d_trans + d_prop

        return DelayMetrics(
            processing_delay=d_proc,
            queue_delay=d_queue,
            transmission_delay=d_trans,
            propagation_delay=d_prop,
            total_delay=total_delay,
            finish_time=service_finish_time + d_prop,
            queue_length_packets=current_queue_length
        )

    def install_shortest_path_routes(self):
        """
        Installs routing tables using a highly optimized NumPy matrix.
        """
        nodes = list(self.nodes)
        n_nodes = len(nodes)
        # Create the conversion maps (String <-> Index)
        self.node_to_idx = {node: idx for idx, node in enumerate(nodes)}
        self.idx_to_node = {idx: node for idx, node in enumerate(nodes)}
        # Initialize the NxN matrix filled with -1 (no route)
        self.routing_matrix = np.full((n_nodes, n_nodes), -1, dtype=np.int32)
        # Calculate all shortest paths in a single pass! (Super fast)
        all_paths = dict(nx.all_pairs_dijkstra_path(self, weight='latency')) # fare grafo con rustworkx dopo test con tanti nodi
        # Populate the matrix
        for source, paths in all_paths.items():
            src_idx = self.node_to_idx[source]
            for dest, path in paths.items():
                if source == dest:
                    continue  # no hop needed for same-node routing
                dest_idx = self.node_to_idx[dest]
                next_hop_node = path[1]  # the next hop
                next_hop_idx = self.node_to_idx[next_hop_node]
                # store the index of the next hop in the matrix
                self.routing_matrix[src_idx, dest_idx] = next_hop_idx
        print(f"[OSPF] NumPy routing matrix ({n_nodes}x{n_nodes}) recalculated.")

    def get_next_hop(self, current_node: str, final_dest: str):
        # If the nodes are not in the mapping, it means they are not in the graph (maybe failed), so we return None
        if current_node not in self.node_to_idx or final_dest not in self.node_to_idx:
            return None
        src_idx = self.node_to_idx[current_node]
        dst_idx = self.node_to_idx[final_dest]
        next_hop_idx = self.routing_matrix[src_idx, dst_idx]
        # If the value is -1, it means there is no route from current_node to final_dest
        if next_hop_idx == -1:
            return None
        # Convert the integer index back to the textual node name
        return self.idx_to_node[next_hop_idx]

    def packet_route(self, packet: Packet, start_time: float):
        """
        Simulates the routing of a single packet from its source to its destination,
        calculating all delay components and handling potential failures (like link or node failures).

        Args:
            packet (Packet): The packet to be routed, containing at least 'src', 'dst', and 'size' attributes.
            start_time (float): The simulation time at which the packet is generated at the source node.
        Returns:
            RoutingResult: A dataclass containing the routing status, path taken, end time, total end-to-end delay, and detailed hop information.
            - status: "DELIVERED" if the packet reaches its destination.
            - path: List of nodes representing the path taken by the packet until delivery or failure.
            - end_time: The simulation time at which the packet is delivered or dropped.
            - total_e2e_delay: Total end-to-end delay experienced by the packet (seconds).
            - hops: A list of HopInfo dataclasses detailing each hop's delay components and queue
        """
        current_node = packet.src
        target = packet.dst
        current_t = start_time
        hop_details = []
        path_taken = [current_node]

        for _ in range(20):
            if current_node == target:
                break

            next_node = self.get_next_hop(current_node, target)
            edge_data = self.edges[current_node, next_node]
            stats = self.delay(current_node, next_node, edge_data, packet, current_t)

            if not stats:
                return {"status": "FAILED", "reason": f"Link fail {current_node}->{next_node}"}

            hop = HopInfo(
                hop=f"{current_node}->{next_node}",
                processing_ms=stats.processing_delay * 1000.0,
                queue_ms=stats.queue_delay * 1000.0,
                transmission_ms=stats.transmission_delay * 1000.0,
                propagation_ms=stats.propagation_delay * 1000.0,
                queue_length=stats.queue_length_packets,
                arrival_at_next=stats.finish_time
            )
            hop_details.append(hop)

            current_t = stats.finish_time
            current_node = next_node
            path_taken.append(current_node)

        return RoutingResult(
            status="DELIVERED",
            path=path_taken,
            end_time=current_t,
            total_e2e_delay=current_t - start_time,
            hops=hop_details
        )

    def remove_node(self, n: str):
        "simulates a node failure of a node and the consequent OSPF recalculation."
        super().remove_node(n)
        print(f"[FAILURE] Node {n} has failed and been removed from the network.")
        self.install_shortest_path_routes()

    def remove_edge(self, u: str, v: str):
        "simulates a link failure and the consequent OSPF recalculation."
        super().remove_edge(u, v)
        print(f"[FAILURE] Link {u} -> {v} has failed and been removed from the network.")
        self.install_shortest_path_routes()
