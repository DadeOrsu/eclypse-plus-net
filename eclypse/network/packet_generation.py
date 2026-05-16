from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger
from network_application import NetworkAwareApplication
from network import Network

class PacketGenerationEvent(EclypseEvent):
    """Event that generates network packets to be routed."""
    def __init__(self):
        """Initializes the PacketGenerationEvent with a cascade trigger on simulation steps."""
        super().__init__(
            name="packet_generation",
            event_type="application",
            triggers=[CascadeTrigger("step")]
        )

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        """Generates packets for the current simulation step based on the defined flows in the application graph."""
        app.current_step += 1
        app.generate_traffic_for_step(app.current_step)
        self.logger.debug(f"step {app.current_step}: App '{app.id}' has generated {len(app.generated_packets)} packets.")
        return {"packets_generated": len(app.generated_packets) if hasattr(app, 'generated_packets') else 0}
