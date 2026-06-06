"""Module containing the traffic routing metric for the ECLYPSE framework."""

from eclypse.report.metrics.metric import application
from network_application import NetworkAwareApplication
from network import Network

@application(name="traffic_routing", activates_on="step")
class TrafficRoutingMetric:
    """Observer metric that extracts routing results from completed packets.

    This metric is called by the Reporter. It performs no complex calculations;
    it simply reads the completed packets processed during the current step and
    formats their delay and hop information for reporting.
    """
    def __init__(self, step_duration_s=0.001):
        """Initialize the traffic routing metric.

        Args:
            step_duration_s (float): The duration of a single simulation step in seconds.
                Defaults to 0.001.
        """
        self.step_duration_s = step_duration_s

    def __call__(self, app: NetworkAwareApplication, placement, infra: Network, **kwargs):
        """Extract and format metrics from the application's completed packets.

        Args:
            app (NetworkAwareApplication): The application instance containing the
                'completed_packets' attribute.
            placement: The placement service used in the simulation.
            infra (Network): The network infrastructure model.
            **kwargs: Additional keyword arguments provided by the framework.

        Returns:
            dict | None: A dictionary containing the flattened metrics for the current
                step, or None if no packets were completed.
        """
        step_results = {}

        if app.completed_packets:
            current_time_s = app.current_step * self.step_duration_s

            # Iterate over completed packets and extract relevant metrics
            for packet in app.completed_packets:
                prefix = f"pkt_{packet.id}"
                step_results[f"{prefix}_App"] = app.id
                step_results[f"{prefix}_Src"] = packet.src
                step_results[f"{prefix}_Dst"] = packet.dst

                start_time_s = packet.step_created * self.step_duration_s

                step_results[f"{prefix}_Start_Time"] = start_time_s
                step_results[f"{prefix}_End_Time"] = current_time_s

                step_results[f"{prefix}_Total_Delay_ms"] = packet.total_delay_ms

                # Components used for the stackplot breakdown
                step_results[f"{prefix}_processing_ms"] = packet.total_processing_ms
                step_results[f"{prefix}_queue_ms"] = packet.total_queue_ms
                step_results[f"{prefix}_transmission_ms"] = packet.total_transmission_ms
                step_results[f"{prefix}_propagation_ms"] = packet.total_propagation_ms

                # Also export the hop-by-hop details
                for i, hop_data in enumerate(packet.hop_history):
                    hop_prefix = f"{prefix}_Hop_{i+1}"
                    step_results[f"{hop_prefix}_hop"] = hop_data["hop"]
                    step_results[f"{hop_prefix}_processing_ms"] = hop_data["processing_ms"]
                    step_results[f"{hop_prefix}_queue_ms"] = hop_data["queue_ms"]
                    step_results[f"{hop_prefix}_transmission_ms"] = hop_data["transmission_ms"]
                    step_results[f"{hop_prefix}_propagation_ms"] = hop_data["propagation_ms"]
                    step_results[f"{hop_prefix}_queue_length"] = hop_data["queue_length"]

                    # Also export the arrival timestamp at the next node
                    step_results[f"{hop_prefix}_arrival_at_next"] = hop_data["arrival_at_next"]

        return step_results if step_results else None
