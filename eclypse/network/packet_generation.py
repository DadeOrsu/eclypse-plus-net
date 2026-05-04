from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger


class PacketGenerationEvent(EclypseEvent):
    def __init__(self):
        # Il nuovo modo per sostituire @event(event_type="application", activates_on="step")
        super().__init__(
            name="packet_generation",
            event_type="application",
            triggers=[CascadeTrigger("step")]
        )

    # The framework injects automatically (app, placement, infra)
    def __call__(self, app, placement, infra, **kwargs):

        # The application takes care of the counting of the ticks, so we just need to call the traffic generation method
        if not hasattr(app, "current_tick"):
            app.current_tick = 0
        app.current_tick += 1

        if hasattr(app, "generate_traffic_for_tick"):
            app.generate_traffic_for_tick(app.current_tick)
            print(f"[DEBUG GEN] Tick {app.current_tick}: App '{app.id}' has generated {len(app.generated_packets)} packets.")

        return {"packets_generated": len(app.generated_packets) if hasattr(app, 'generated_packets') else 0}
