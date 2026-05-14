from eclypse.graph import Application
from dataclasses import dataclass


@dataclass(slots=True)
class Packet:
    """
    Data class to represent a network packet with its attributes.
    """
    id: int
    src: str
    dst: str
    size: int
    step_created: int


class NetworkAwareApplication(Application):
    """
    Extension of the standard ECLYPSE application class that incorporates
    network traffic characteristics.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Internal counter to give unique IDs to generated packets
        self._packet_counter = 0
        self.current_step = 0
        self.generated_packets = []
        self.completed_packets = []

    def add_edge(self, u_of_edge: str, v_of_edge: str, packet_size_bytes: int = 1500,
                 packets_per_step: int = 1, **attr):
        """
        Overrides the default add_edge to automatically validate and inject
        traffic parameters (packet size, rate, and throughput) for the logical flow.
        """
        if packet_size_bytes <= 0:
            raise ValueError(f"Packet size must be > 0. Found: {packet_size_bytes}")
        if packets_per_step < 0:
            raise ValueError(f"Packet rate must be >= 0. Found: {packets_per_step}")
        throughput_per_step = packet_size_bytes * packets_per_step
        attr['packet_size_bytes'] = packet_size_bytes
        attr['packets_per_step'] = packets_per_step
        attr['required_throughput_per_step'] = throughput_per_step
        super().add_edge(u_of_edge, v_of_edge, **attr)
        self.logger.info(f"Added edge flow {u_of_edge}->{v_of_edge}: {packets_per_step} pkt/step, size {packet_size_bytes}B")

    def generate_traffic_for_step(self, step: int) -> list:
        """
        Reads the flow definitions stored in the edges and produces a list of
        packet dictionaries for the current simulation step.

        Args:
            step (int): The current simulation step number.

        Returns:
            list: A list of dictionaries, where each dict represents a packet
                  ready to be routed.
        """
        self.generated_packets = []

        # Iterate over all edges (flows) defined in the application
        # self.edges(data=True) returns (source, target, attributes)
        for u, v, data in self.edges(data=True):

            # Retrieve the saved parameters with add_flow
            rate = data.get("packets_per_step", 0)
            size = data.get("packet_size_bytes", 1500)  # Default 1500 if absent

            # We generate N packets for this step
            for _ in range(rate):
                self._packet_counter += 1

                packet = Packet(
                    id=self._packet_counter,
                    src=u,
                    dst=v,
                    size=size,
                    step_created=step
                )
                self.generated_packets.append(packet)
