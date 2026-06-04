"""Module containing the traffic routing execution event for the ECLYPSE framework."""

import random
from collections import defaultdict
from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger
from network_application import NetworkAwareApplication
from network import Network
from constants import (
    DEFAULT_BANDWIDTH_MBPS,
    SEC_TO_MS
)

def build_probabilistic_queue(incoming_queues: dict[str, list], bandwidths: dict[str, float]) -> list:
    """It merges the input queues in a probabilistic manner based on bandwidth.

    Implement a probabilistic multiplexer: it extracts packets from the input
    queues by tossing a 'weighted coin' based on the bandwidth values.
    """
    merged_queue = []

    # We continue until there is at least one packet in any of the queues.
    while any(incoming_queues.values()):
        # Filter out sources that still have packages
        active_sources = [src for src, q in incoming_queues.items() if len(q) > 0]
        # Retrieve the associated weights (bandwidth)
        active_weights = [bandwidths[src] for src in active_sources]
        # Probabilistic extraction of the packet with P = Bandwidth / Sum(Bandwidths)
        chosen_source = random.choices(active_sources, weights=active_weights, k=1)[0]
        # Remove the packet from the original queue and insert it into the merged queue
        packet = incoming_queues[chosen_source].pop(0)
        merged_queue.append(packet)

    return merged_queue

class TrafficRoutingExecutionEvent(EclypseEvent):
    """Worker event that executes routing logic and updates application state.

    This event is called exactly once per step by the simulation engine. It is
    responsible for taking generated packets, resolving their source and
    destination placements, performing the heavy routing calculations, and
    moving the results to the completed packets basket.
    """
    def __init__(self, step_duration_s=0.001):
        """Initialize the traffic routing execution event.

        Args:
            step_duration_s (float): The duration of a single simulation step
                in seconds. Defaults to 0.001.
        """
        self.step_duration_s = step_duration_s
        super().__init__(
            name="traffic_routing_execution",
            event_type="application",
            triggers=[CascadeTrigger("step")]
        )

    def _group_by_contention_point(self, packets: list, placement, infra: Network) -> dict:
        """Group packets by their next-hop contention point (receiving router)."""
        contention_groups = defaultdict(lambda: defaultdict(list))

        for packet in packets:
            try:
                src_node = placement.service_placement(service_id=packet.src)
                dst_node = placement.service_placement(service_id=packet.dst)
            except KeyError as e:
                self.logger.debug(f"ERROR PLACEMENT: Unable to map {e}")
                continue

            packet.src = src_node
            packet.dst = dst_node

            if src_node == dst_node:
                continue

            path = infra.path(src_node, dst_node, cost_attr='cost')
            if path and len(path) > 0:
                first_edge = path[0]
                next_hop = first_edge[1]

                contention_groups[next_hop][src_node].append(packet)

        return contention_groups

    def _resolve_local_multiplexing(self, contention_groups: dict, infra: Network) -> list:
        """Apply independent probabilistic multiplexing to resolve local contention."""
        final_shuffled_list = []

        # Iterate over each contention point (next-hop) and its incoming queues
        for next_hop, incoming_queues in contention_groups.items():
            bws = {}
            # For each source node, we read the bandwidth.
            for src_node in incoming_queues:
                # Read the bandwidth of the link from src_node to next_hop
                edge_data = infra.get_edge_data(src_node, next_hop, default={})
                bws[src_node] = edge_data.get('bandwidth_mbps', DEFAULT_BANDWIDTH_MBPS)

            # Apply the probabilistic multiplexer to shuffle the packets based on bandwidth
            shuffled_group = build_probabilistic_queue(incoming_queues, bws)
            final_shuffled_list.extend(shuffled_group)

        return final_shuffled_list

    def _update_dynamic_latencies(self, completed_packets: list, infra: Network) -> None:
        """Update link latencies based on actual traffic, restoring defaults for idle links."""
        link_delays = defaultdict(list)

        for _, result in completed_packets:
            if result.status == "DELIVERED":
                for hop_info in result.hops:
                    u, v = hop_info.hop.split("->")
                    total_hop_delay = (hop_info.processing_ms +
                                       hop_info.queue_ms +
                                       hop_info.transmission_ms +
                                       hop_info.propagation_ms)
                    link_delays[(u, v)].append(total_hop_delay)

        # Update active links
        for (u, v), delays in link_delays.items():
            if infra.has_edge(u, v):
                avg_latency = sum(delays) / len(delays)
                infra[u][v]['latency'] = avg_latency

        # Restore base latency for inactive links
        for u, v, edge_data in infra.edges(data=True):
            if (u, v) not in link_delays:
                d_proc_ms = infra.processing_time(u, v) * SEC_TO_MS
                d_prop_ms = (edge_data.get('length_km', 0) / edge_data.get('propagation_speed_km_s', 1)) * SEC_TO_MS
                infra[u][v]['latency'] = d_proc_ms + d_prop_ms

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        """Execute the routing logic for packets generated in the current step."""
        app.completed_packets.clear()
        current_time_s = app.current_step * self.step_duration_s

        # Group packets by their next-hop contention point
        contention_groups = self._group_by_contention_point(app.generated_packets, placement, infra)

        # Independent probabilistic multiplexing for each contention point
        shuffled_packets = self._resolve_local_multiplexing(contention_groups, infra)

        if shuffled_packets:
            source_order = [p.src for p in shuffled_packets]
            self.logger.info(
                f"[STEP {app.current_step}] "
                f"Total packets: {len(shuffled_packets)} | "
                f"Extraction order: {source_order}"
            )

        # Physical routing E2E
        for packet in shuffled_packets:
            result = infra.packet_route(packet, current_time_s)
            app.completed_packets.append((packet, result))

        # Update latencies
        self._update_dynamic_latencies(app.completed_packets, infra)

        app.generated_packets.clear()
