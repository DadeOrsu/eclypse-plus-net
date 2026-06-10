import numpy as np
from eclypse.graph import Application
from network import Packet
from constants import(
    DEFAULT_AVG_PACKETS_PER_STEP,
    DEFAULT_PACKET_SIZE_BYTES
)


class NetworkAwareApplication(Application):
    """Extension of the standard ECLYPSE application class that incorporates.

    network traffic characteristics.
    """

    def __init__(self, *args, **kwargs):
        """Initializes the NetworkAwareApplication and sets up the state for packet generation."""
        super().__init__(*args, **kwargs)
        # Internal counter to give unique IDs to generated packets
        self._packet_counter = 0
        self.current_step = 0
        self.generated_packets = []

    def add_edge(self, u_of_edge: str, v_of_edge: str, packet_size_bytes: int = DEFAULT_PACKET_SIZE_BYTES,
                 avg_packets_per_step: float = DEFAULT_AVG_PACKETS_PER_STEP, **attr):
        """Overrides the default add_edge.

        It automatically validates and injects traffic parameters (packet size and expected rate)
        for the logical flow, configured for a stochastic Poisson distribution.
        """
        if packet_size_bytes <= 0:
            raise ValueError(f"Packet size must be > 0. Found: {packet_size_bytes}")
        if avg_packets_per_step < 0:
            raise ValueError(f"Packet rate must be >= 0. Found: {avg_packets_per_step}")
        attr['packet_size_bytes'] = packet_size_bytes
        attr['avg_packets_per_step'] = avg_packets_per_step
        super().add_edge(u_of_edge, v_of_edge, **attr)
        self.logger.info(f"Added flow {u_of_edge}->{v_of_edge}: ~{avg_packets_per_step} pkt/step (avg), size {packet_size_bytes}B")

    def generate_traffic_for_step(self, step: int) -> None:
        """Generate traffic based on the defined flows in the application graph.

        Reads the flow definitions stored in the edges and produces a list of packet dictionaries
        for the current simulation step using a Poisson distribution.

        Args:
            step (int): The current simulation step number.

        Returns:
            None
        """
        self.generated_packets = []

        # Iterate over all edges (flows) defined in the application
        for u, v, data in self.edges(data=True):

            # Retrieve the saved parameters (Lambda parameter for Poisson)
            lam_rate = data.get("avg_packets_per_step", DEFAULT_AVG_PACKETS_PER_STEP)  # Default if absent
            size = data.get("packet_size_bytes", DEFAULT_PACKET_SIZE_BYTES)  # Default if absent

            # Extraction of the number of packets to generate based on a Poisson distribution
            n_packets = np.random.poisson(lam=lam_rate) if lam_rate > 0 else 0

            # Generate N actual packets for this step based on the Poisson draw
            for _ in range(n_packets):
                self._packet_counter += 1

                packet = Packet(
                    id=self._packet_counter,
                    src=u,
                    dst=v,
                    size=size,
                    step_created=step
                )
                self.generated_packets.append(packet)
