"""Module containing the network infrastructure extension for the ECLYPSE framework."""

import networkx as nx
from collections import defaultdict, deque
from eclypse.graph import Infrastructure
from dataclasses import dataclass
from constants import (
    DEFAULT_BANDWIDTH_MBPS,
    DEFAULT_LENGTH_KM,
    DEFAULT_PROPAGATION_SPEED_KM_S,
    MIN_LENGTH_KM,
    MIN_PROPAGATION_SPEED,
    MBPS_TO_BPS,
    SEC_TO_MS,
    BYTES_TO_BITS
)

@dataclass(slots=True)
class HopInfo:
    """Represent detailed telemetry information for a single network hop.

    Attributes:
        hop (str): The edge identifier representing the hop (e.g., 'A->B').
        processing_ms (float): The processing delay in milliseconds.
        queue_ms (float): The queuing delay in milliseconds.
        transmission_ms (float): The transmission delay in milliseconds.
        propagation_ms (float): The propagation delay in milliseconds.
        queue_length (int): The number of packets in the queue at arrival time.
        arrival_at_next (float): The absolute arrival time at the next node in ms.
    """
    hop: str
    processing_ms: float
    queue_ms: float
    transmission_ms: float
    propagation_ms: float
    queue_length: int
    arrival_at_next: float


@dataclass(slots=True)
class Packet:
    """Represent a stateful network packet for hop-by-hop routing simulation.

    Attributes:
        id (int): The unique identifier of the packet.
        src (str): The source node identifier.
        dst (str): The destination node identifier.
        size (int): The size of the packet in bytes.
        step_created (int): The simulation step when the packet was created.
        current_node (str): The node where the packet is currently located.
        previous_node (str): The node the packet just left.
        hop_count (int): The number of hops the packet has traversed so far.
    """
    id: int
    src: str
    dst: str
    size: int
    step_created: int
    current_node: str = ""
    previous_node: str = "APP"
    hop_count: int = 0

def ospf_path_algorithm(g: nx.Graph, source: str, target: str) -> list[str]:
    """Compute the shortest path using Dijkstra's algorithm based on OSPF cost.

    Args:
        g (nx.Graph): The network graph topology.
        source (str): The starting node identifier.
        target (str): The destination node identifier.

    Returns:
        list[str]: A list of node identifiers representing the shortest path.
    """
    return nx.dijkstra_path(g, source, target, weight='cost')

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
        # Assign the routing algorithm for standard execution
        kwargs['path_algorithm'] = ospf_path_algorithm
        super().__init__(*args, **kwargs)
        # The queues of packets waiting to be transmitted on a specific link
        self.link_queues = defaultdict(deque)
        # The registered time a packet traversed the link
        self.link_step_time = defaultdict(float)
        # The list of packets that are sitting in a specific node waiting
        self.router_buffers = defaultdict(list)
        # Hop telemetry tracking
        self.step_telemetry = []

    def add_edge(self, u_of_edge: str, v_of_edge: str,
                 bandwidth_mbps: float = DEFAULT_BANDWIDTH_MBPS,
                 length_km: float = DEFAULT_LENGTH_KM,
                 propagation_speed_km_s: float = DEFAULT_PROPAGATION_SPEED_KM_S,
                 **attr):
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
            **attr: Additional attributes to apply to the edge.
        """
        attr['bandwidth_mbps'] = bandwidth_mbps
        attr['length_km'] = length_km
        attr['propagation_speed_km_s'] = propagation_speed_km_s
        attr['cost'] = 1/(bandwidth_mbps * MBPS_TO_BPS)  # Cost for OSPF routing
        super().add_edge(u_of_edge, v_of_edge, **attr)

    def update_link_latencies(self):
            """Calculate and update the latency attribute for each link.

            The calculation evaluates the telemetry collected during the current step
            and updates the dynamic latency metric. If no telemetry is present, it
            estimates the latency based on default packet sizes and link properties.
            """
            link_delays = defaultdict(float)
            link_counts = defaultdict(int)

            # Calculate the total delay for each link based on the telemetry of the
            # current step
            for _, hop_info in self.step_telemetry:
                u, v = hop_info.hop.split("->")

                # The total delay for this hop is the sum of processing, queuing,
                # transmission and propagation delays
                total_hop_delay = (hop_info.processing_ms +
                                hop_info.queue_ms +
                                hop_info.transmission_ms +
                                hop_info.propagation_ms)

                link_delays[(u, v)] += total_hop_delay
                link_counts[(u, v)] += 1

            # Update the attribute 'latency' for each link based on the average delay
            # observed during this step
            for u, v, data in self.edges(data=True):
                # Check the direction u -> v for the link
                # if we have telemetry data for it calculate the average delay
                if (u, v) in link_counts:
                    avg_delay = link_delays[(u, v)] / link_counts[(u, v)]
                    self[u][v]['latency'] = avg_delay

                # If we don't have telemetry data for this link during this step,
                # we can optionally set a default latency
                else:
                    d_proc = self.processing_time(u, v) * SEC_TO_MS
                    speed = data.get("propagation_speed_km_s", MIN_PROPAGATION_SPEED)
                    length = data.get("length_km", MIN_LENGTH_KM)

                    d_prop = (length / speed) * SEC_TO_MS if speed > 0 else 0.0
                    # Estimate the transmission delay based on the bandwidth and a
                    # typical packet size (e.g., 1500 bytes)
                    R = data.get("bandwidth_mbps", DEFAULT_BANDWIDTH_MBPS) * MBPS_TO_BPS
                    d_transm = (
                        ((1500 * BYTES_TO_BITS) / R) * SEC_TO_MS
                        if R > 0
                        else 0.0
                    )

                    self[u][v]['latency'] = d_proc + d_prop + d_transm

    def forward_one_hop(self, packet: Packet, current_time: float) -> str | None:
        """Calculate the next hop for a packet and update its telemetry state.

        Resolves the next hop using OSPF routing, evaluates queuing, transmission,
        processing, and propagation delays using store-and-forward logic, and
        updates the packet's internal state.

        Args:
            packet (Packet): The packet object to be forwarded.
            current_time (float): The absolute simulation time in seconds.

        Returns:
            str | None: The identifier of the next node, or None if no route exists.
        """
        u = packet.current_node

        # Dynamic calculation of the next hop using OSPF path algorithm
        path = self.path(u, packet.dst, cost_attr='cost')
        if not path:
            self.logger.warning(
                f"Packet {packet.id} dropped: No routes for {packet.dst}"
                )
            return None

        v = path[0][1]
        edge_data = self.get_edge_data(u, v, default={})

        R = edge_data.get("bandwidth_mbps", DEFAULT_BANDWIDTH_MBPS) * MBPS_TO_BPS

        # Calculate the queuing delay based on the current queue length
        # and the link bandwidth
        queue = self.link_queues[(u, v)]

        # If there is a recorded time for the last packet processed on this link
        if (u, v) in self.link_step_time and current_time > self.link_step_time[(u, v)]:
            delta_t = current_time - self.link_step_time[(u, v)]
            bits_service_capacity = delta_t * R

            # Only clear the queue of packets that the link had time to transmit.
            while queue and bits_service_capacity > 0:
                front_packet_bits = queue[0].size * BYTES_TO_BITS
                if bits_service_capacity >= front_packet_bits:
                    bits_service_capacity -= front_packet_bits
                    queue.popleft()  # The packet has been fully transmitted, remove it
                else:
                    # The packet at the front has been transmitted only partially.
                    break

        # Update the last time we processed this link to the current time
        # So we can calculate the next delta_t
        self.link_step_time[(u, v)] = current_time

        d_proc = self.processing_time(u, v)

        # Calculate the queuing delay based on the packets actually left in the queue
        d_queue = 0.0
        if R > 0:
            for queued_packet in queue:
                d_queue += ((queued_packet.size * BYTES_TO_BITS) / R)

        d_transm = ((packet.size * BYTES_TO_BITS) / R) if R > 0 else 0.0

        length = edge_data.get("length_km", MIN_LENGTH_KM)
        speed = edge_data.get("propagation_speed_km_s", MIN_PROPAGATION_SPEED)
        d_prop = (
            (length / speed) if speed > 0 else 0.0
        )
        # Queue the current packet
        queue.append(packet)

        # Calculate the times for the telemetry
        hop_delay_ms = (d_proc + d_queue + d_transm + d_prop) * SEC_TO_MS
        arrival_time_ms = (current_time * SEC_TO_MS) + hop_delay_ms

        # Register the hop information for telemetry and later reporting
        hop_info = HopInfo(
            hop=f"{u}->{v}",
            processing_ms=d_proc * SEC_TO_MS,
            queue_ms=d_queue * SEC_TO_MS,
            transmission_ms=d_transm * SEC_TO_MS,
            propagation_ms=d_prop * SEC_TO_MS,
            queue_length=len(queue),
            arrival_at_next=arrival_time_ms
        )
        self.step_telemetry.append((packet, hop_info))

        # Advance the packet's state to the next hop
        packet.previous_node = u
        packet.current_node = v

        packet.hop_count += 1
        return v

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
