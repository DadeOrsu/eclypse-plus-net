import pandas as pd
from network_application import NetworkAwareApplication
from network import Network
from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger


class TrafficRoutingEvent(EclypseEvent):
    def __init__(self, tick_duration_s=0.001):
        super().__init__(
            name="traffic_routing",
            event_type="application",
            triggers=[CascadeTrigger("step")]
        )
        self.tick_duration_s = tick_duration_s
        self.network_results = []

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs): #tipare app e infra
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
            # no simulate nel nome
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
                    "Hops": result.hops # ridonante
                })
            else:
                # We use getattr to safely access the 'reason' attribute, providing a default message if it's not present
                reason = getattr(result, 'reason', 'No specific reason provided')
                print(f"[DEBUG ROUTER] Packet {packet.id} dropped! Reason: {reason}")

        return {"status": "routing_completed"}

    def get_dataframe(self):
        return pd.DataFrame(self.network_results)
    

    # trasformare in una metrica