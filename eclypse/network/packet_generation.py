from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger
from network_application import NetworkAwareApplication
from network import Network

class PacketGenerationEvent(EclypseEvent):
    def __init__(self):
        super().__init__(
            name="packet_generation",
            event_type="application",
            triggers=[CascadeTrigger("step")]
        )

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        # The application takes care of the counting of the steps, so we just need to call the traffic generation method
        app.current_step += 1
        app.generate_traffic_for_step(app.current_step)
        print(f"[DEBUG GEN] step {app.current_step}: App '{app.id}' has generated {len(app.generated_packets)} packets.")
        return {"packets_generated": len(app.generated_packets) if hasattr(app, 'generated_packets') else 0}
