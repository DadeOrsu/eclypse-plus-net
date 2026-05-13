from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger
from network_application import NetworkAwareApplication
from network import Network


class TrafficRoutingExecutionEvent(EclypseEvent):
    """
    This is the WORKER. It is called exactly once per step by the engine.
    It executes the heavy routing logic and updates the application state.
    """
    def __init__(self, step_duration_s=0.001):
        self.step_duration_s = step_duration_s
        super().__init__(
            name="traffic_routing_execution",
            event_type="application",
            triggers=[CascadeTrigger("step")]
        )

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        # 1. Clear the output basket from the previous step's results
        app.completed_packets.clear()

        current_time_s = app.current_step * self.step_duration_s

        # 2. Iterate over the packets generated in the current step
        for packet in app.generated_packets:
            try:
                src_node = placement.service_placement(service_id=packet.src)
                dst_node = placement.service_placement(service_id=packet.dst)
            except KeyError as e:
                print(f"[DEBUG ROUTER] ERROR PLACEMENT: Unable to map {e}")
                continue

            packet.src = src_node
            packet.dst = dst_node

            # HEAVY PHYSICAL EXECUTION (happens strictly ONCE!)
            result = infra.simulate_packet_routing(packet, current_time_s)

            # Put the result in the output basket
            app.completed_packets.append((packet, result))

        # 3. Empty the input basket (packets have been processed)
        app.generated_packets.clear()
