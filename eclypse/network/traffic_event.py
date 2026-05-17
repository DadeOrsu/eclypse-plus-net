"""Module containing the traffic routing execution event for the ECLYPSE framework."""

from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger
from network_application import NetworkAwareApplication
from network import Network


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

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        """Execute the routing logic for packets generated in the current step.

        Args:
            app (NetworkAwareApplication): The application instance containing the
                generated and completed packets.
            placement: The placement service used to resolve node locations.
            infra (Network): The network infrastructure used for packet routing.
            **kwargs: Additional keyword arguments provided by the framework.
        """
        # Clear the output basket from the previous step's results
        app.completed_packets.clear()

        current_time_s = app.current_step * self.step_duration_s

        # Iterate over the packets generated in the current step
        for packet in app.generated_packets:
            try:
                src_node = placement.service_placement(service_id=packet.src)
                dst_node = placement.service_placement(service_id=packet.dst)
            except KeyError as e:
                self.logger.debug(f"ERROR PLACEMENT: Unable to map {e}")
                continue

            packet.src = src_node
            packet.dst = dst_node

            result = infra.packet_route(packet, current_time_s)

            # Append the packet and its routing result to the completed packets basket
            app.completed_packets.append((packet, result))

        # Empty the generated packets basket for the next step
        app.generated_packets.clear()
