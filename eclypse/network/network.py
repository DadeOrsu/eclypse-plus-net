import networkx as nx
import random
from methodtools import lru_cache
from collections import defaultdict, deque
from eclypse.graph import Infrastructure
from network_application import Packet
from dataclasses import dataclass, field
from constants import (
    MIN_BANDWIDTH,
    MIN_LENGTH_KM,
    MIN_PROPAGATION_SPEED
)


@dataclass(slots=True)
class DelayMetrics:
    """Metrics for calculating delays in the network."""
    processing_delay: float
    queue_delay: float
    transmission_delay: float
    propagation_delay: float
    total_delay: float
    finish_time: float
    queue_length_packets: int


@dataclass(slots=True)
class HopInfo:
    """Detailed information about a single hop in the packet's path."""
    hop: str
    processing_ms: float
    queue_ms: float
    transmission_ms: float
    propagation_ms: float
    queue_length: int
    arrival_at_next: float


@dataclass(slots=True)
class RoutingResult:
    """Result of routing a packet through the network."""
    status: str
    reason: str = ""
    path: list[str] = field(default_factory=list)
    end_time: float = 0.0
    total_e2e_delay: float = 0.0
    hops: list[HopInfo] = field(default_factory=list)


class Network(Infrastructure):
    """Extension of the Infrastructure model of ECLYPSE.

    This class simulates a network of routers using queuing logic,
    with physical packet queuing.
    """
    def __init__(self, *args, **kwargs):
        """Initializes the Network infrastructure and sets up data structures for queuing and OSPF caching."""
        super().__init__(*args, **kwargs)
        self.link_next_free_time = defaultdict(float)
        self.link_queues = defaultdict(deque)

    def _invalidate_cache(self) -> None:
        """Centralized invalidation method.

        Overriding this allows us to automatically trigger OSPF re-routing whenever the topology
        changes.
        """
        # 1. Call the base class logic to clear framework-level caches
        super()._invalidate_cache()
        # 2. Automatically re-install routes (proactive approach)
        self.get_next_hop.cache_clear()
        # This is triggered by add_edge, remove_node, remove_edge, etc.
        self.logger.warning("[OSPF] Cache invalidated.")

    def add_edge(self, u_of_edge: str, v_of_edge: str, bandwidth_mbps: float = 100.0,
                 length_km: float = 1.0, propagation_speed_km_s: float = 200000.0,
                 processing_delay_s: float = 0.0001, **attr):
        """Overrides the default add_edge.

        It automatically calculates and injects queuing parameters (bandwidth in bps, latency,
        propagation, processing).
        """
        attr['parameters'] = bandwidth_mbps * 1_000_000
        attr['bandwidth_mbps'] = bandwidth_mbps
        attr['length_km'] = length_km
        attr['propagation_speed_km_s'] = propagation_speed_km_s
        attr['processing_delay_s'] = processing_delay_s
        attr['latency'] = (length_km / propagation_speed_km_s) * 1000.0
        super().add_edge(u_of_edge, v_of_edge, **attr)

    def delay(self, u: str, v: str, edge_data: dict, packet: Packet, current_time: float) -> DelayMetrics:
        """Calculates the delay components for a single packet traversing a specific link (u->v).

        Args:
            u (str): The source node ID of the link.
            v (str): The destination node ID of the link.
            edge_data (dict): The attributes of the edge (u, v) containing at least 'bandwidth_mbps'
                ,'length_km', 'propagation_speed_km_s', and 'processing_delay_s'.
            packet (Packet): The packet object containing at least 'size' attribute.
            current_time (float): The simulation time at which the packet arrives at node 'u'.

        Returns:
            DelayMetrics | None: A dataclass containing the following fields:

            - 'processing_delay': Time spent processing the packet at node 'u' (seconds).
            - 'queue_delay': Time spent waiting in the buffer (seconds).
            - 'transmission_delay': Time spent transmitting the packet bits (seconds).
            - 'propagation_delay': Time spent travelling the physical medium (seconds).
            - 'total_delay': Sum of all delay components (seconds).
            - 'finish_time': Simulation time when the packet fully arrives at node 'v'.
            - 'queue_length_packets': Number of packets in the queue at the time of arrival.

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

    @lru_cache(maxsize=10000)
    def get_next_hop(self, current_node: str, final_dest: str) -> str | None:
        """Calculate the next hop ONLY if needed.

        The @lru_cache decorator stores up to 10,000 frequent routes in memory.
        """
        # If the current node does not exist in the graph, or the destination is invalid, return None
        if current_node not in self.nodes or final_dest not in self.nodes:
            return None
        try:
            # Calculate the shortest path on demand using latency as the weight
            path = nx.shortest_path(self, source=current_node, target=final_dest, weight='latency')
            if len(path) > 1:
                return path[1]
        except nx.NetworkXNoPath:
            return None
        return None

    def packet_route(self, packet: Packet, start_time: float) -> RoutingResult:
        """Simulates the routing of a single packet from its source to its destination.

        Calculates all delay components and handles potential failures (like link
        or node failures).

        Args:
            packet (Packet): The packet to be routed, containing at least 'src', 'dst',
                and 'size' attributes.
            start_time (float): The simulation time at which the packet is generated
                at the source node.

        Returns:
            RoutingResult: A dataclass containing the routing status, path taken, end time,
            total end-to-end delay, and detailed hop information.

            The dataclass includes:
            - status: "DELIVERED" if the packet reaches its destination.
            - path: List of nodes representing the path taken by the packet until delivery or failure.
            - end_time: The simulation time at which the packet is delivered or dropped.
            - total_e2e_delay: Total end-to-end delay experienced by the packet (seconds).
            - hops: A list of HopInfo dataclasses detailing each hop's delay components and queue.
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
        """Removes a node.

        _invalidate_cache will handle the OSPF update.
        """
        super().remove_node(n)
        self.logger.warning(f"[FAILURE] Node {n} removed.")

    def remove_edge(self, u: str, v: str):
        """Removes an edge.

        _invalidate_cache will handle the OSPF update.
        """
        super().remove_edge(u, v)
        self.logger.warning(f"[FAILURE] Link {u} -> {v} removed.")
