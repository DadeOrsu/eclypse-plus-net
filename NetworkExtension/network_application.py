from eclypse.graph import Application


class NetworkAwareApplication(Application):
    """
    Extension of the standard ECLYPSE application class that incorporates
    network traffic characteristics.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Internal counter to give unique IDs to generated packets
        self._packet_counter = 0

    def add_flow(self, source: str, target: str, packet_size_bytes: int,
                 packets_per_tick: int, **kwargs):
        """
        Adds a directed logical link (flow) between two services.
        Stores traffic parameters in the graph edge.
        """
        if packet_size_bytes <= 0:
            raise ValueError(f"Packet size must be > 0. Found: {packet_size_bytes}")
        if packets_per_tick < 0:
            raise ValueError(f"Packet rate must be >= 0. Found: {packets_per_tick}")

        throughput_per_tick = packet_size_bytes * packets_per_tick

        # We save the data in the graph (NetworkX edge attributes)
        self.add_edge(
            source,
            target,
            packet_size_bytes=packet_size_bytes,
            packets_per_tick=packets_per_tick,
            required_throughput_per_tick=throughput_per_tick,
            **kwargs
        )
        print(f"Add edge flow {source}->{target}: {packets_per_tick} pkt/tick, size {packet_size_bytes}B")

    def generate_traffic_for_tick(self, tick: int) -> list:
        """
        Reads the flow definitions stored in the edges and produces a list of
        packet dictionaries for the current simulation tick.

        Args:
            tick (int): The current simulation tick number.

        Returns:
            list: A list of dictionaries, where each dict represents a packet
                  ready to be routed.
        """
        generated_packets = []

        # Iterate over all edges (flows) defined in the application
        # self.edges(data=True) returns (source, target, attributes)
        for u, v, data in self.edges(data=True):

            # Retrieve the saved parameters with add_flow
            rate = data.get("packets_per_tick", 0)
            size = data.get("packet_size_bytes", 1500)  # Default 1500 if absent

            # We generate N packets for this tick
            for _ in range(rate):
                self._packet_counter += 1

                packet = {
                    "id": self._packet_counter,
                    "src": u,   # Source (es. "Sensor")
                    "dst": v,   # Destination (es. "Cloud")
                    "size": size,
                    "tick_created": tick
                }
                generated_packets.append(packet)

        return generated_packets
