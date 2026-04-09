import pandas as pd
from eclypse.workflow.event import event


@event(event_type="application", activates_on="step")
class TrafficRoutingEvent:

    def __init__(self, tick_duration_s: float = 0.001):
        self.tick_duration_s = tick_duration_s
        self.network_results = []

    def __call__(self, app, placement, infra, **kwargs):

        if hasattr(app, "generated_packets") and app.generated_packets:
            print(f"[DEBUG ROUTER] Routing {len(app.generated_packets)} packets in progress...")
            current_time_s = app.current_tick * self.tick_duration_s

            for packet in app.generated_packets:
                src_service = packet.src
                dst_service = packet.dst

                try:
                    src_node = placement.service_placement(service_id=src_service)
                    dst_node = placement.service_placement(service_id=dst_service)
                except KeyError as e:
                    print(f"[DEBUG ROUTER] ERROR PLACEMENT: Impossible to map the service {e}")
                    continue

                packet.src = src_node
                packet.dst = dst_node

                result = infra.simulate_packet_routing(packet, current_time_s)

                if result.status == 'DELIVERED':
                    self.network_results.append({
                        "Tick": app.current_tick,
                        "Packet_ID": packet.id,
                        "App": app.id,
                        "Src": src_node,
                        "Dst": dst_node,
                        "Start_Time": current_time_s,
                        "End_Time": result.end_time,
                        "Total_Delay_ms": result.total_e2e_delay * 1000,
                        "Hops": result.hops
                    })
                else:
                    # We use getattr to safely access the 'reason' attribute, providing a default message if it's not present
                    reason = getattr(result, 'reason', 'No specific reason provided')
                    print(f"[DEBUG ROUTER] Packet {packet.id} dropped! Reason: {reason}")

        return {"status": "routing_completed"}

    def get_dataframe(self):
        return pd.DataFrame(self.network_results)