"""Module extending the ECLYPSE application model with network capabilities."""

import numpy as np
from eclypse.graph import Application
from network import Packet
from constants import(
    DEFAULT_AVG_PACKETS_PER_STEP,
    DEFAULT_PACKET_SIZE_BYTES
)


class NetworkAwareApplication(Application):
    """Extension of the standard ECLYPSE application class.

    Incorporates network traffic characteristics and stochastic
    packet generation logic.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the NetworkAwareApplication.

        Sets up the internal state required for packet generation tracking,
        including sequential IDs and packet buffers.

        Args:
            *args: Variable length argument list passed to the parent class.
            **kwargs: Arbitrary keyword arguments passed to the parent class.
        """
        super().__init__(*args, **kwargs)
        # Internal counter to give unique IDs to generated packets
        self._packet_counter = 0
        self.current_step = 0
        self.generated_packets = []

    def add_edge(self, u_of_edge: str,
                 v_of_edge: str,
                 packet_size_bytes: int = DEFAULT_PACKET_SIZE_BYTES,
                 avg_packets_per_step: float = DEFAULT_AVG_PACKETS_PER_STEP,
                 **attr):
        """Add a logical flow edge to the application graph.

        Overrides the default add_edge method to automatically validate and inject
        traffic parameters (packet size and expected rate) required for the
        stochastic Poisson distribution generation.

        Args:
            u_of_edge (str): The source service ID of the logical flow.
            v_of_edge (str): The destination service ID of the logical flow.
            packet_size_bytes (int, optional): The fixed size in bytes for packets
                generated on this flow. Defaults to DEFAULT_PACKET_SIZE_BYTES.
            avg_packets_per_step (float, optional): The expected average number of
                packets generated per step (Lambda). Defaults to \
                DEFAULT_AVG_PACKETS_PER_STEP.
            **attr: Additional attributes to assign to the edge.

        Raises:
            ValueError: If packet_size_bytes is less than or equal to 0, or if
                avg_packets_per_step is less than 0.
        """
        if packet_size_bytes <= 0:
            raise ValueError(f"Packet size must be > 0. Found: {packet_size_bytes}")
        if avg_packets_per_step < 0:
            raise ValueError(f"Packet rate must be >= 0. Found: {avg_packets_per_step}")
        attr['packet_size_bytes'] = packet_size_bytes
        attr['avg_packets_per_step'] = avg_packets_per_step
        super().add_edge(u_of_edge, v_of_edge, **attr)

        self.logger.info(
            "Added flow %s->%s: ~%s pkt/step (avg), size %sB",
            u_of_edge,
            v_of_edge,
            avg_packets_per_step,
            packet_size_bytes
        )

    def generate_traffic_for_step(self, step: int) -> None:
        """Generate traffic based on the defined flows in the application graph.

        Reads the flow definitions stored in the edges and produces a list of packet
        objects for the current simulation step, drawing the quantity from a
        Poisson distribution.

        Args:
            step (int): The current simulation step number to stamp on packets.
        """
        self.generated_packets = []

        # Iterate over all edges (flows) defined in the application
        for u, v, data in self.edges(data=True):

            # Retrieve the saved parameters (Lambda parameter for Poisson)
            lam_rate = data.get("avg_packets_per_step", DEFAULT_AVG_PACKETS_PER_STEP)
            size = data.get("packet_size_bytes", DEFAULT_PACKET_SIZE_BYTES)

            # Number of packets to generate based on a Poisson distribution
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
