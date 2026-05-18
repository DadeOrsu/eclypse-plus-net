"""Module containing the network infrastructure extension for the ECLYPSE framework."""

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
    """Represent the delay metrics for a network packet traversing a link."""
    processing_delay: float
    queue_delay: float
    transmission_delay: float
    propagation_delay: float
    total_delay: float
    finish_time: float
    queue_length_packets: int


@dataclass(slots=True)
class HopInfo:
    """Represent detailed information about a single hop in a packet's path."""
    hop: str
    processing_ms: float
    queue_ms: float
    transmission_ms: float
    propagation_ms: float
    queue_length: int
    arrival_at_next: float


@dataclass(slots=True)
class RoutingResult:
    """Represent the result of routing a packet through the network."""
    status: str
    reason: str = ""
    path: list[str] = field(default_factory=list)
    end_time: float = 0.0
    total_e2e_delay: float = 0.0
    hops: list[HopInfo] = field(default_factory=list)


class Network(Infrastructure):
    """Extend the Infrastructure model of ECLYPSE to simulate physical queuing.

    This class simulates a network of routers using a queuing logic,
    managing physical packet delays and an on-demand LRU cache for OSPF routing.
    """
    def __init__(self, *args, **kwargs):
        """Initialize the Network infrastructure.

        Sets up the underlying ECLYPSE infrastructure and initializes the
        data structures required for tracking link queues and free times.

        Args:
            *args: Variable length argument list passed to the base class.
            **kwargs: Arbitrary keyword arguments passed to the base class.
        """
        super().__init__(*args, **kwargs)
        self.link_next_free_time = defaultdict(float)
        self.link_queues = defaultdict(deque)

    def _invalidate_cache(self) -> None:
        """Invalidate the network routing cache centrally.

        Overriding this method allows the network to automatically trigger
        OSPF re-routing (by flushing the LRU cache) whenever the topology
        changes due to node or edge additions/removals.
        """
        # Call the base class logic to clear framework-level caches
        super()._invalidate_cache()
        # Automatically re-install routes (proactive approach)
        self.get_next_hop.cache_clear()
        # This is triggered by add_edge, remove_node, remove_edge, etc.
        self.logger.warning("[OSPF] Cache invalidated.")

    def add_edge(self, u_of_edge: str, v_of_edge: str, bandwidth_mbps: float = 100.0,
                 length_km: float = 1.0, propagation_speed_km_s: float = 200000.0,
                 processing_delay_s: float = 0.0001, **attr):
        """Add an edge to the network with queuing parameters.

        Automatically calculates and injects physical queuing parameters
        such as bandwidth in bps and latency before passing the data to
        the underlying graph infrastructure.

        Args:
            u_of_edge (str): The source node ID of the edge.
            v_of_edge (str): The destination node ID of the edge.
            bandwidth_mbps (float): The link bandwidth in Mbps. Defaults to 100.0.
            length_km (float): The length of the physical link in km. Defaults to 1.0.
            propagation_speed_km_s (float): The signal propagation speed in km/s.
                Defaults to 200000.0.
            processing_delay_s (float): The node processing delay in seconds.
                Defaults to 0.0001.
            **attr: Additional attributes to apply to the edge.
        """
        attr['bandwidth_mbps'] = bandwidth_mbps
        attr['length_km'] = length_km
        attr['propagation_speed_km_s'] = propagation_speed_km_s
        attr['processing_delay_s'] = processing_delay_s
        attr['latency'] = (length_km / propagation_speed_km_s) * 1000.0
        super().add_edge(u_of_edge, v_of_edge, **attr)

    def delay(self, u: str, v: str, edge_data: dict, packet: Packet, current_time: float) -> DelayMetrics:
        """Calculate the delay components for a packet traversing a specific link.

        Args:
            u (str): The source node ID of the link.
            v (str): The destination node ID of the link.
            edge_data (dict): The attributes of the edge containing bandwidth, length,
                speed, and processing delay specifications.
            packet (Packet): The packet being transmitted.
            current_time (float): The simulation time at which the packet arrives at node 'u'.

        Returns:
            DelayMetrics | None: A dataclass containing the calculated processing, queuing,
                transmission, and propagation delays, as well as the queue length. Returns
                None if the delay calculation cannot be performed.
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
        """Retrieve the next hop for a packet on-demand.

        Utilizes an LRU cache to store up to 10,000 frequent routes, computing
        the shortest path via Dijkstra's algorithm only upon a cache miss.

        Args:
            current_node (str): The ID of the node where the packet currently resides.
            final_dest (str): The ID of the packet's final destination node.

        Returns:
            str | None: The ID of the next hop node, or None if no valid path exists.
        """
        # If the current node does not exist in the graph or the destination is invalid returns None
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
        """Simulate the physical routing of a single packet through the network.

        Calculates end-to-end traversal, aggregating delay components at each hop,
        and manages link or node failures encountered along the calculated path.

        Args:
            packet (Packet): The packet to be routed.
            start_time (float): The simulation time when the packet is generated.

        Returns:
            RoutingResult: The aggregated result of the packet's journey, including
                delivery status, path taken, total delay, and hop-by-hop metrics.
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
        """Remove a node from the network and trigger an OSPF cache update.

        Args:
            n (str): The ID of the node to remove.
        """
        super().remove_node(n)
        self.logger.warning(f"[FAILURE] Node {n} removed.")

    def remove_edge(self, u: str, v: str):
        """Remove an edge from the network and trigger an OSPF cache update.

        Args:
            u (str): The source node ID of the edge.
            v (str): The destination node ID of the edge.
        """
        super().remove_edge(u, v)
        self.logger.warning(f"[FAILURE] Link {u} -> {v} removed.")
