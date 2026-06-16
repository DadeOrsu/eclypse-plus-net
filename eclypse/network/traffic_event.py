"""Module containing the traffic routing execution event for the ECLYPSE framework."""

import random
from collections import defaultdict
from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger
from network_application import NetworkAwareApplication
from network import Network
from constants import (
    DEFAULT_BANDWIDTH_MBPS
)


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

    def _inject_generated_packets(self, app: NetworkAwareApplication,
                                  placement, infra: Network) -> None:
        """Helper to inject new packets into the network."""
        for packet in app.generated_packets:
            try:
                src_node = placement.service_placement(service_id=packet.src)
                dst_node = placement.service_placement(service_id=packet.dst)
            except KeyError:
                continue

            packet.src = src_node
            packet.dst = dst_node
            packet.current_node = src_node

            infra.router_buffers[src_node].append(packet)

        app.generated_packets.clear()

    def _prepare_incoming_queues(self, router: str, buffer: list,
                                 infra: Network) -> tuple[dict, dict]:
        """Helper to separate incoming packets by source and determine link bandwidths."""
        incoming_queues = defaultdict(list)
        for pkt in buffer:
            incoming_queues[pkt.previous_node].append(pkt)

        bws = {}
        for prev_node in incoming_queues:
            if prev_node == "APP":
                bws[prev_node] = DEFAULT_BANDWIDTH_MBPS * 10
            else:
                edge_data = infra.get_edge_data(prev_node, router, default={})
                bws[prev_node] = edge_data.get('bandwidth_mbps', DEFAULT_BANDWIDTH_MBPS)

        return incoming_queues, bws

    def _build_probabilistic_queue(self, incoming_queues: dict[str, list],
                                   bandwidths: dict[str, float]) -> list:
        """It merges the input queues in a probabilistic manner based on bandwidth.

        Implement a probabilistic multiplexer: it extracts packets from the input
        queues by tossing a 'weighted coin' based on the bandwidth values.
        """
        merged_queue = []

        # Continue until there is at least one packet in any of the queues.
        while any(incoming_queues.values()):
            # Filter out sources that still have packages
            active_sources = [src for src, q in incoming_queues.items() if len(q) > 0]
            # Retrieve the associated weights (bandwidth)
            active_weights = [bandwidths[src] for src in active_sources]
            # Probabilistic extraction of the packet with P = Bandwidth/Sum(Bandwidths)
            chosen_source = random.choices(active_sources,
                                        weights=active_weights,
                                        k=1)[0]
            # Remove packet from the chosen queue and insert it into the merged queue
            packet = incoming_queues[chosen_source].pop(0)
            merged_queue.append(packet)

        return merged_queue


    def _forward_shuffled_packets(self, shuffled_packets: list, current_time_s: float,
                                  infra: Network, next_step_buffers: dict) -> None:
        """Helper to route packets sequentially and distribute them to their next destination."""
        for pkt in shuffled_packets:
            next_node = infra.forward_one_hop(pkt, current_time_s)

            if next_node is not None:
                if next_node == pkt.dst:
                    pass # The packet has reached its destination
                else:
                    next_step_buffers[next_node].append(pkt)

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        """Execute the routing logic for packets generated in the current step."""
        infra.step_telemetry.clear()
        current_time_s = app.current_step * self.step_duration_s

        next_step_buffers = defaultdict(list)

        # Inject new traffic
        self._inject_generated_packets(app, placement, infra)

        # Process existing router buffers
        active_routers = list(infra.router_buffers.keys())

        for router in active_routers:
            buffer = infra.router_buffers[router]
            if not buffer:
                continue

            incoming_queues, bws = self._prepare_incoming_queues(router, buffer, infra)
            shuffled_packets = self._build_probabilistic_queue(incoming_queues, bws)

            if len(shuffled_packets) > 1:
                order_log = ", ".join([f"{p.id} ({p.previous_node})" for p in shuffled_packets])
                infra.logger.info(f"{router} order: [{order_log}]")

            self._forward_shuffled_packets(shuffled_packets, current_time_s, app, infra, next_step_buffers)

            infra.router_buffers[router].clear()

        # Move the landed packets to the new routers for the next round
        for router, pkts in next_step_buffers.items():
            infra.router_buffers[router].extend(pkts)

        # Update latencies based on telemetry
        infra.update_link_latencies()
