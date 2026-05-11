from eclypse.report.metrics.metric import application
from network_application import NetworkAwareApplication
from network import Network

@application(name="traffic_routing", activates_on="step")
class TrafficRoutingMetric:
    def __init__(self, tick_duration_s=0.001):
        self.tick_duration_s = tick_duration_s

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        step_results = {}
        generated_packets = getattr(app, "generated_packets", [])

        if generated_packets:
            current_time_s = app.current_tick * self.tick_duration_s

            for packet in generated_packets:
                # Since the routing is executed only once per packet, we check if it has already been routed to avoid re-simulating it in subsequent ticks.
                if getattr(packet, "routed", False):
                    result = packet.routing_result
                    src_node = packet.src
                    dst_node = packet.dst
                else:
                    # Do the mapping of logical service names to physical nodes only once per packet, and handle potential KeyErrors gracefully.
                    try:
                        src_node = placement.service_placement(service_id=packet.src)
                        dst_node = placement.service_placement(service_id=packet.dst)
                    except KeyError as e:
                        print(f"[DEBUG ROUTER] ERROR PLACEMENT: Impossible to map {e}")
                        continue

                    # Update the packet with the resolved physical nodes for routing
                    packet.src = src_node
                    packet.dst = dst_node
                    
                    # Start the packet routing simulation and store the result in the packet for future reference
                    result = infra.simulate_packet_routing(packet, current_time_s)
                    
                    # Print debug information about the routing result and mark the packet as routed to avoid re-processing in future ticks
                    print(f"[DEBUG ROUTER] Routing of the packet {packet.id} executed.")
                    packet.routed = True
                    packet.routing_result = result

                if result.status == 'DELIVERED':
                    prefix = f"pkt_{packet.id}"
                    step_results[f"{prefix}_App"] = app.id
                    step_results[f"{prefix}_Src"] = src_node
                    step_results[f"{prefix}_Dst"] = dst_node
                    step_results[f"{prefix}_Start_Time"] = current_time_s
                    step_results[f"{prefix}_End_Time"] = result.end_time
                    step_results[f"{prefix}_Total_Delay_ms"] = result.total_e2e_delay * 1000
                    # Add the detailed hop information
                    for i, h in enumerate(result.hops):
                        hop_prefix = f"{prefix}_Hop_{i+1}"
                        step_results[f"{hop_prefix}_hop"] = h.hop
                        step_results[f"{hop_prefix}_processing_ms"] = h.processing_ms
                        step_results[f"{hop_prefix}_queue_ms"] = h.queue_ms
                        step_results[f"{hop_prefix}_transmission_ms"] = h.transmission_ms
                        step_results[f"{hop_prefix}_propagation_ms"] = h.propagation_ms
                        step_results[f"{hop_prefix}_queue_length"] = h.queue_length
                        step_results[f"{hop_prefix}_arrival_at_next"] = h.arrival_at_next

                else:
                    if not getattr(packet, "drop_logged", False):
                        reason = getattr(result, 'reason', 'No reason')
                        print(f"[DEBUG ROUTER] Packet {packet.id} dropped! Reason: {reason}")
                        packet.drop_logged = True

        return step_results if step_results else None