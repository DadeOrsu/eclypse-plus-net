from eclypse.report.metrics.metric import application
from network_application import NetworkAwareApplication
from network import Network

@application(name="traffic_routing", activates_on="step")
class TrafficRoutingMetric:
    """
    This is the OBSERVER. It is called by the Reporter.
    It performs no complex calculations; it simply reads the completed packets.
    """
    def __init__(self, step_duration_s=0.001):
        self.step_duration_s = step_duration_s

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        step_results = {}

        # We fetch the "output basket" filled by the Execution Event
        if app.completed_packets:
            current_time_s = app.current_step * self.step_duration_s

            for packet, result in app.completed_packets:
                if result.status == 'DELIVERED':
                    prefix = f"pkt_{packet.id}"
                    step_results[f"{prefix}_App"] = app.id
                    step_results[f"{prefix}_Src"] = packet.src
                    step_results[f"{prefix}_Dst"] = packet.dst
                    step_results[f"{prefix}_Start_Time"] = current_time_s
                    step_results[f"{prefix}_End_Time"] = result.end_time
                    step_results[f"{prefix}_Total_Delay_ms"] = result.total_e2e_delay * 1000

                    # Flat saving of Hops data
                    for i, h in enumerate(result.hops):
                        hop_prefix = f"{prefix}_Hop_{i+1}"
                        step_results[f"{hop_prefix}_hop"] = h.hop

                        # Direct attribute access via strong typing
                        step_results[f"{hop_prefix}_processing_ms"] = h.processing_ms
                        step_results[f"{hop_prefix}_queue_ms"] = h.queue_ms
                        step_results[f"{hop_prefix}_transmission_ms"] = h.transmission_ms
                        step_results[f"{hop_prefix}_propagation_ms"] = h.propagation_ms
                        step_results[f"{hop_prefix}_queue_length"] = h.queue_length
                        step_results[f"{hop_prefix}_arrival_at_next"] = h.arrival_at_next

        return step_results if step_results else None