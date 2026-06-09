"""Module containing the network infrastructure extension for the ECLYPSE framework."""

import networkx as nx
from collections import defaultdict, deque
from eclypse.graph import Infrastructure
from dataclasses import dataclass, field
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
    """Represent detailed information about a single hop in a packet's path."""
    hop: str
    processing_ms: float
    queue_ms: float
    transmission_ms: float
    propagation_ms: float
    queue_length: int
    arrival_at_next: float


@dataclass(slots=True)
class Packet:
    """Data class to represent a stateful network packet for Hop-by-Hop routing."""
    id: int
    src: str
    dst: str
    size: int
    step_created: int
    current_node: str = ""
    previous_node: str = "APP"
    hop_count: int = 0

    # additional fields used for stackplot breakdown and final E2E delay calculation

    total_delay_ms: float = 0.0
    total_processing_ms: float = 0.0
    total_queue_ms: float = 0.0
    total_transmission_ms: float = 0.0
    total_propagation_ms: float = 0.0

    hop_history: list[HopInfo] = field(default_factory=list)

def ospf_path_algorithm(g: nx.Graph, source: str, target: str) -> list[str]:
    """Custom path algorithm for ECLYPSE to strictly use OSPF 'cost'."""
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
        kwargs['path_algorithm'] = ospf_path_algorithm
        super().__init__(*args, **kwargs)
        self.link_queues = defaultdict(deque)

        self.link_step_time = defaultdict(float)
        self.router_buffers = defaultdict(list)

        self.step_telemetry = []

    def add_edge(self, u_of_edge: str, v_of_edge: str, bandwidth_mbps: float = DEFAULT_BANDWIDTH_MBPS,
                 length_km: float = DEFAULT_LENGTH_KM, propagation_speed_km_s: float = DEFAULT_PROPAGATION_SPEED_KM_S,
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
        attr['cost'] = 1/(bandwidth_mbps * MBPS_TO_BPS)  # Cost for OSPF routing (inverse of bandwidth)
        super().add_edge(u_of_edge, v_of_edge, **attr)

    def forward_one_hop(self, packet: Packet, current_time: float) -> str | None:
        """Calcola il ritardo sul singolo hop e registra la telemetria nello step_telemetry."""
        u = packet.current_node

        # 1. Calcolo dinamico del next hop
        path = self.path(u, packet.dst, cost_attr='cost')
        if not path:
            self.logger.warning(f"Packet {packet.id} droppato: Nessuna rotta per {packet.dst}")
            return None

        v = path[0][1]
        edge_data = self.get_edge_data(u, v, default={})

        # 2. Reset coda M/D/1
        if current_time > self.link_step_time[(u, v)]:
            self.link_queues[(u, v)].clear()
            self.link_step_time[(u, v)] = current_time

        d_proc = self.processing_time(u, v)
        R = edge_data.get("bandwidth_mbps", DEFAULT_BANDWIDTH_MBPS) * MBPS_TO_BPS

        # 3. Calcolo ritardo di accodamento
        queue = self.link_queues[(u, v)]
        d_queue = 0.0
        if R > 0:
            for queued_packet in queue:
                d_queue += ((queued_packet.size * BYTES_TO_BITS) / R)

        d_transm = ((packet.size * BYTES_TO_BITS) / R) if R > 0 else 0.0
        d_prop = (edge_data.get("length_km", MIN_LENGTH_KM) /
                  edge_data.get("propagation_speed_km_s", MIN_PROPAGATION_SPEED)) if edge_data.get("propagation_speed_km_s", MIN_PROPAGATION_SPEED) > 0 else 0.0

        queue.append(packet)

        # 4. Calcolo tempi per la telemetria
        hop_delay_ms = (d_proc + d_queue + d_transm + d_prop) * SEC_TO_MS
        arrival_time_ms = (current_time * SEC_TO_MS) + hop_delay_ms

        # 5. Registrazione nel registro temporaneo della rete (NON nel pacchetto)
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

        # 6. Avanzamento stato minimale
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
